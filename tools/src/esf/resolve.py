"""Resolving names against the SDE, and the semantic rules (SPEC §4.2, §5, §6)."""

import bisect
import math
from dataclasses import dataclass, field

from . import sde as S
from .names import fold, is_word_prefix
from .sde import SDE, Attribute, Type
from .text import RACKS, STORED, EsfError, FitBlock, Line


@dataclass
class Item:
    line: Line
    type: Type | None
    kind: str
    place: str
    charge: Type | None = None
    mutaplasmid: Type | None = None
    overrides: list[tuple[Attribute, float]] = field(default_factory=list)
    reference: "Fit | None" = None

    @property
    def stored(self) -> bool:
        return self.place in STORED


@dataclass
class Fit:
    block: FitBlock
    hull: Type | None
    mode: Type | None
    cargo_only: bool
    items: list[Item] = field(default_factory=list)
    racks: dict[str, list[tuple[int, int, Item | None]]] = field(default_factory=dict)

    @property
    def name(self) -> str | None:
        return self.block.fit_name


def classify(t: Type, sde: SDE) -> str:
    """What a type is, for placement (SPEC §5)."""
    if t.group == S.GROUP_SHIP_MODIFIERS:
        return "modifier"
    if t.category in (S.CATEGORY_SHIP, S.CATEGORY_STRUCTURE) or t.group in S.GROUPS_CONTAINER:
        return "hull"
    if t.category == S.CATEGORY_SUBSYSTEM:
        return "sub"
    if t.category in (S.CATEGORY_MODULE, S.CATEGORY_STRUCTURE_MODULE):
        return sde.slots.get(t.id, "other")
    if t.category == S.CATEGORY_DRONE:
        return "drone"
    if t.category == S.CATEGORY_FIGHTER:
        return "fighter"
    if t.category == S.CATEGORY_CHARGE:
        return "charge"
    if t.category == S.CATEGORY_IMPLANT:
        return "booster" if t.group == S.GROUP_BOOSTER else "implant"
    return "other"


PLACES = {"drone": "drones", "fighter": "fighters", "implant": "implants", "booster": "boosters"}


def default_place(kind: str, cargo_only: bool) -> str:
    if cargo_only or kind in ("hull", "charge", "other"):
        return "cargo"
    return PLACES.get(kind, kind)


def mode_name(hull: Type, mode: Type) -> str:
    """A tactical mode's name without the hull's name."""
    return mode.name[len(hull.name) :].lstrip(" ")


def _lookup(sde: SDE, name: str, line: int) -> Type:
    t = sde.type_by_name(name)
    if t is None:
        raise EsfError(f"unknown type {name!r}", line)
    return t


def _pick(candidates: list[Type], given: str, what: str, line: int) -> Type:
    if not candidates:
        raise EsfError(f"no {what} matches {given!r}", line)
    if len(candidates) > 1:
        names = ", ".join(repr(c.name) for c in candidates)
        raise EsfError(f"{given!r} matches more than one {what}: {names}", line)
    return candidates[0]


def _resolve_hull(block: FitBlock, sde: SDE) -> Fit:
    if block.hull is None:
        return Fit(block, None, None, True)

    hull = _lookup(sde, block.hull, block.hull_line)
    if classify(hull, sde) != "hull":
        raise EsfError(f"{hull.name!r} is not a ship, structure or container", block.hull_line)

    mode = None
    if block.mode is not None:
        modes = [sde.types[m] for m in sde.modes.get(hull.id, [])]
        if not modes:
            raise EsfError(f"{hull.name!r} has no tactical modes", block.hull_line)
        matches = [
            m
            for m in modes
            if is_word_prefix(block.mode, m.name) or is_word_prefix(block.mode, mode_name(hull, m))
        ]
        mode = _pick(matches, block.mode, f"tactical mode of {hull.name!r}", block.hull_line)

    return Fit(block, hull, mode, hull.group in S.GROUPS_CONTAINER)


def _resolve_line(line: Line, fit: Fit, fits: list[Fit], sde: SDE) -> Item:
    n = line.number
    if line.count == 0:
        raise EsfError("a count must be at least 1", n)

    if line.kind == "empty":
        if fit.cargo_only:
            raise EsfError("a fit without a ship has no slots to keep empty", n)
        if line.index == 0:
            raise EsfError("slots are numbered from 1", n)
        return Item(line, None, "empty", line.location)

    t = _lookup(sde, line.name, n)
    kind = classify(t, sde)
    if kind == "modifier":
        raise EsfError("a tactical mode is only written on the hull line", n)

    item = Item(line, t, kind, default_place(kind, fit.cargo_only))

    if line.kind == "reference":
        if kind != "hull":
            raise EsfError(f"{t.name!r} cannot take a fit name", n)
        matches = [
            f
            for f in fits
            if f.hull is not None
            and f.hull.id == t.id
            and f.name is not None
            and fold(f.name) == fold(line.fit_name)
        ]
        if len(matches) != 1:
            what = "no fit" if not matches else "more than one fit"
            raise EsfError(f"{what} matches {t.name} {line.fit_name!r}", n)
        item.reference = matches[0]

    if line.index is not None:
        if fit.cargo_only:
            raise EsfError("a fit without a ship stores everything in cargo", n)
        if kind != line.location:
            raise EsfError(f"{t.name!r} does not go in the {line.location} rack", n)
        if line.index == 0:
            raise EsfError("slots are numbered from 1", n)
        item.place = line.location
    elif line.location is not None:
        if fit.cargo_only and line.location != "cargo":
            raise EsfError("a fit without a ship stores everything in cargo", n)
        if line.location == "bay" and kind not in ("drone", "fighter"):
            raise EsfError("@bay is only for drones and fighters", n)
        item.place = line.location

    if line.state is not None:
        if item.stored:
            raise EsfError("a stored item has no state", n)
        if item.place in ("implants", "boosters") and line.state != "off":
            raise EsfError("an implant or booster takes !off only", n)

    if line.charge is not None:
        item.charge = _lookup(sde, line.charge, n)
        if item.charge.category != S.CATEGORY_CHARGE:
            raise EsfError(f"{item.charge.name!r} is not a charge", n)

    if line.mutaplasmid is not None:
        candidates = [sde.types[m] for m in sde.mutaplasmids_for(t.id)]
        matches = [m for m in candidates if is_word_prefix(line.mutaplasmid, m.name)]
        item.mutaplasmid = _pick(matches, line.mutaplasmid, f"mutaplasmid for {t.name!r}", n)

    seen = set()
    for name, value in line.overrides:
        attr = sde.attribute_by_name(name)
        if attr is None:
            raise EsfError(f"unknown attribute {name!r}", n)
        if attr.id in seen:
            raise EsfError(f"attribute {attr.name!r} is overridden twice", n)
        seen.add(attr.id)
        number = float(value)
        if not math.isfinite(number):
            raise EsfError(f"value {value!r} is out of range", n)
        item.overrides.append((attr, number))

    return item


def _check_cycles(fits: list[Fit]):
    state: dict[int, int] = {}

    def visit(fit: Fit):
        state[id(fit)] = 1
        for item in fit.items:
            ref = item.reference
            if ref is None:
                continue
            if state.get(id(ref)) == 1:
                raise EsfError("a fit cannot contain itself", item.line.number)
            if id(ref) not in state:
                visit(ref)
        state[id(fit)] = 2

    for fit in fits:
        if id(fit) not in state:
            visit(fit)


def _layout(items: list[Item]) -> list[tuple[int, int, Item | None]]:
    """Assign slots in one rack (SPEC §6.3): runs of (first index, length, item)."""
    pinned: dict[int, Item] = {}
    for item in items:
        index = item.line.index
        if index is None:
            continue
        if index in pinned:
            raise EsfError(f"slot {index} is pinned twice", item.line.number)
        pinned[index] = item

    pins = sorted(pinned)
    runs = [(index, 1, item) for index, item in pinned.items()]
    pos = 1
    for item in items:
        if item.line.index is not None:
            continue
        remaining = item.line.count or 1
        while remaining:
            while pos in pinned:
                pos += 1
            at = bisect.bisect_left(pins, pos)
            room = pins[at] - pos if at < len(pins) else remaining
            take = min(remaining, room)
            runs.append((pos, take, item))
            pos += take
            remaining -= take
    runs.sort(key=lambda r: r[0])

    filled = []
    pos = 1
    for start, length, item in runs:
        if start > pos:
            filled.append((pos, start - pos, None))
        filled.append((start, length, item))
        pos = start + length
    return filled


def resolve(blocks: list[FitBlock], sde: SDE) -> list[Fit]:
    fits = [_resolve_hull(block, sde) for block in blocks]
    for fit in fits:
        fit.items = [_resolve_line(line, fit, fits, sde) for line in fit.block.lines]
    _check_cycles(fits)
    for fit in fits:
        for rack in RACKS:
            items = [i for i in fit.items if i.place == rack]
            if items:
                fit.racks[rack] = _layout(items)
    return fits
