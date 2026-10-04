"""Canonical form (SPEC §8)."""

from dataclasses import dataclass, field
from decimal import Decimal

from .names import fold, shortest_unique
from .resolve import PLACES, Fit, Item, default_place, mode_name
from .sde import SDE, Attribute, Type
from .text import HOLDS, RACKS, SIGILS, is_count

GROUPS = (*RACKS, "drones", "fighters", "cargo", *HOLDS, "implants", "boosters")


@dataclass
class CanonLine:
    type: Type | None
    count: int | None = None
    fit_name: str | None = None
    charge: Type | None = None
    charge_count: int | None = None
    mutaplasmid: Type | None = None
    mutaplasmid_name: str | None = None
    overrides: list[tuple[Attribute, float]] = field(default_factory=list)
    state: str | None = None
    location: str | None = None

    def body(self) -> str:
        parts = [quote_type(self.type.name) if self.type else "-"]
        if self.fit_name is not None:
            parts.append(quote(self.fit_name))
        if self.charge is not None:
            count = "" if self.charge_count is None else f"{self.charge_count}x "
            parts.append(f":{count}{quote_type(self.charge.name)}")
        if self.mutaplasmid is not None:
            parts.append(f"+{self.mutaplasmid_name}")
        if self.overrides:
            pairs = ", ".join(f"{a.name} {number(v)}" for a, v in self.overrides)
            parts.append(f"{{{pairs}}}")
        if self.state is not None:
            parts.append(f"!{self.state}")
        if self.location is not None:
            parts.append(f"@{self.location}")
        return " ".join(parts)

    def text(self) -> str:
        if self.count is None:
            return self.body()
        return f"{self.count}x {self.body()}"


@dataclass
class CanonFit:
    hull: Type | None
    name: str | None
    mode: Type | None
    mode_text: str | None
    groups: list[list[CanonLine]]

    @property
    def lines(self) -> list[CanonLine]:
        return [line for group in self.groups for line in group]

    def text(self) -> str:
        hull = [quote_type(self.hull.name) if self.hull else "-"]
        if self.name is not None:
            hull.append(quote(self.name))
        if self.mode is not None:
            hull.append(f"/{self.mode_text}")
        out = f"%esf/1\n{' '.join(hull)}\n"
        for group in self.groups:
            out += "\n" + "".join(line.text() + "\n" for line in group)
        return out


def quote(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def needs_quotes(name: str) -> bool:
    words = name.split(" ")
    return (
        words[0][:1] in ("-", "%", "")
        or is_count(words[0])
        or any(w[:1] in SIGILS or w == "" for w in words)
    )


def quote_type(name: str) -> str:
    return quote(name) if needs_quotes(name) else name


def number(value: float) -> str:
    """The shortest decimal, without exponent, that reads back as the same float."""
    text = repr(value)
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    text = text.removesuffix(".0")
    return text


def _default_state(item: Item, sde: SDE) -> str | None:
    """The state token that canonical form leaves out; None means running."""
    if item.place in ("implants", "boosters") or item.type.id not in sde.active:
        return "on"
    return None


def _line(item: Item, fit: Fit, sde: SDE) -> CanonLine:
    line = item.line
    out = CanonLine(item.type)

    if item.reference is not None:
        out.fit_name = item.reference.name

    if item.charge is not None:
        out.charge = item.charge
        full = sde.full_load(item.type, item.charge)
        if line.charge_count is not None and line.charge_count != full:
            out.charge_count = line.charge_count

    overrides = {a.id: (a, v) for a, v in item.overrides}
    if item.mutaplasmid is not None:
        out.mutaplasmid = item.mutaplasmid
        others = [sde.types[m].name for m in sde.mutaplasmids_for(item.type.id)]
        others.remove(item.mutaplasmid.name)
        out.mutaplasmid_name = shortest_unique(item.mutaplasmid.name, others)
        for attr_id in sde.rollable(item.mutaplasmid.id):
            if attr_id not in overrides:
                attr = sde.attributes[attr_id]
                overrides[attr_id] = (attr, sde.base_value(item.type.id, attr_id))
    out.overrides = sorted(overrides.values(), key=lambda o: (fold(o[0].name), o[0].name))

    if line.state is not None and line.state != _default_state(item, sde):
        out.state = line.state

    if item.place != default_place(item.kind, fit.cargo_only) and item.place not in RACKS:
        out.location = item.place
    return out


def _sort_key(type_: Type, text: str):
    return (fold(type_.name), text.encode())


def _collapse(lines: list[tuple[bool, CanonLine]]) -> list[CanonLine]:
    """Merge adjacent identical repeatable lines into one count."""
    out: list[tuple[bool, CanonLine]] = []
    for repeatable, line in lines:
        if out and repeatable and out[-1][0] and out[-1][1].body() == line.body():
            prev = out[-1][1]
            prev.count = (prev.count or 1) + (line.count or 1)
            continue
        out.append((repeatable, line))
    for repeatable, line in out:
        if line.count == 1:
            line.count = None
    return [line for _, line in out]


def _rack(fit: Fit, rack: str, sde: SDE) -> list[CanonLine]:
    runs = list(fit.racks.get(rack, []))
    while runs and (runs[-1][2] is None or runs[-1][2].type is None):
        runs.pop()
    lines = []
    for _, length, item in runs:
        if item is None or item.type is None:
            line = CanonLine(None, location=rack)
        else:
            line = _line(item, fit, sde)
        line.count = length
        lines.append((True, line))
    return _collapse(lines)


def _sorted(items: list[Item], fit: Fit, sde: SDE) -> list[CanonLine]:
    lines = []
    for item in items:
        line = _line(item, fit, sde)
        repeatable = not item.stored
        count = item.line.count or 1
        if repeatable:
            line.count = count
            key = _sort_key(item.type, line.body())
        else:
            line.count = None if count == 1 else count
            key = _sort_key(item.type, line.text())
        lines.append((key, repeatable, line))
    lines.sort(key=lambda entry: entry[0])
    return _collapse([(repeatable, line) for _, repeatable, line in lines])


def _fighters(items: list[Item], fit: Fit, sde: SDE) -> list[CanonLine]:
    tubes = [i for i in items if i.place == "fighters"]
    lines = []
    for item in tubes:
        line = _line(item, fit, sde)
        count = item.line.count
        if count is not None and count != sde.squadron.get(item.type.id):
            line.count = count
        lines.append(line)
    return lines + _sorted([i for i in items if i.place == "bay"], fit, sde)


def canonical_fit(fit: Fit, sde: SDE) -> CanonFit:
    groups: dict[str, list[Item]] = {}
    for item in fit.items:
        if item.place in RACKS:
            continue
        group = item.place
        if group == "bay":
            group = PLACES[item.kind]
        groups.setdefault(group, []).append(item)

    chunks = []
    for group in GROUPS:
        if group in RACKS:
            chunk = _rack(fit, group, sde)
        elif group == "fighters":
            chunk = _fighters(groups.get(group, []), fit, sde)
        else:
            chunk = _sorted(groups.get(group, []), fit, sde)
        if chunk:
            chunks.append(chunk)

    mode_text = None
    if fit.mode is not None:
        others = [mode_name(fit.hull, sde.types[m]) for m in sde.modes[fit.hull.id]]
        own = mode_name(fit.hull, fit.mode)
        others.remove(own)
        mode_text = shortest_unique(own, others)

    return CanonFit(fit.hull, fit.name, fit.mode, mode_text, chunks)


def render(fits: list[CanonFit]) -> str:
    return "\n".join(fit.text() for fit in fits)
