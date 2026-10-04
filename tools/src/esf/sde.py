"""The subset of the EVE Online SDE that esf/1 needs."""

import json
import os
import re
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .names import fold

LATEST_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"

CATEGORY_SHIP = 6
CATEGORY_MODULE = 7
CATEGORY_CHARGE = 8
CATEGORY_DRONE = 18
CATEGORY_IMPLANT = 20
CATEGORY_SUBSYSTEM = 32
CATEGORY_STRUCTURE = 65
CATEGORY_STRUCTURE_MODULE = 66
CATEGORY_FIGHTER = 87

GROUP_BOOSTER = 303
GROUP_SHIP_MODIFIERS = 1306
GROUPS_CONTAINER = {12, 340, 448, 649}

EFFECT_SLOTS = {12: "high", 13: "mid", 11: "low", 2663: "rig", 6306: "svc"}
EFFECT_CATEGORIES_ACTIVE = {1, 2}
EFFECT_ONLINE = 16

ATTRIBUTE_SQUADRON_SIZE = 2215


@dataclass(frozen=True)
class Type:
    id: int
    name: str
    group: int
    category: int
    published: bool
    volume: float
    capacity: float


@dataclass(frozen=True)
class Attribute:
    id: int
    name: str
    published: bool
    default: float


def cache_path() -> Path:
    if path := os.environ.get("ESF_SDE"):
        return Path(path)
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "esf" / "sde.json"


def latest_build() -> tuple[int, str]:
    request = urllib.request.Request(LATEST_URL, method="HEAD")
    with urllib.request.urlopen(request) as response:
        url = response.geturl()
    match = re.search(r"-(\d+)-jsonl\.zip$", url)
    if not match:
        raise RuntimeError(f"cannot find the SDE build number in {url}")
    return int(match.group(1)), url


def fetch(force: bool = False) -> int:
    """Download the latest SDE into the cache, unless it is already there."""
    path = cache_path()
    build, url = latest_build()
    if not force and path.exists():
        with open(path) as f:
            if json.load(f)["build"] == build:
                return build

    print(f"Downloading SDE build {build} ...", file=sys.stderr)
    with tempfile.TemporaryFile() as archive:
        with urllib.request.urlopen(url) as response:
            while chunk := response.read(1 << 20):
                archive.write(chunk)
        archive.seek(0)
        with zipfile.ZipFile(archive) as zf:
            data = _extract(zf)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    tmp.replace(path)
    return build


def _rows(zf: zipfile.ZipFile, name: str):
    with zf.open(name) as f:
        for line in f:
            yield json.loads(line)


def _extract(zf: zipfile.ZipFile) -> dict:
    build = next(_rows(zf, "_sde.jsonl"))["buildNumber"]

    groups = {g["_key"]: g["categoryID"] for g in _rows(zf, "groups.jsonl")}
    effect_categories = {
        e["_key"]: e.get("effectCategoryID") for e in _rows(zf, "dogmaEffects.jsonl")
    }

    types = []
    for t in _rows(zf, "types.jsonl"):
        name = t["name"].get("en")
        if not name:
            continue
        types.append(
            [
                t["_key"],
                name,
                t["groupID"],
                int(bool(t.get("published"))),
                t.get("volume", 0.0),
                t.get("capacity", 0.0),
            ]
        )

    mutaplasmids = {}
    rollable = {}
    for d in _rows(zf, "dynamicItemAttributes.jsonl"):
        bases = sorted({b for m in d["inputOutputMapping"] for b in m["applicableTypes"]})
        attrs = sorted(a["_key"] for a in d["attributeIDs"])
        mutaplasmids[d["_key"]] = {"bases": bases, "attrs": attrs}
        for base in bases:
            rollable.setdefault(base, set()).update(attrs)

    slots = {}
    active = []
    squadron = {}
    base_values = {}
    for d in _rows(zf, "typeDogma.jsonl"):
        type_id = d["_key"]
        effects = [e["effectID"] for e in d.get("dogmaEffects", [])]
        for effect in effects:
            if effect in EFFECT_SLOTS:
                slots[type_id] = EFFECT_SLOTS[effect]
        if any(
            effect_categories.get(e) in EFFECT_CATEGORIES_ACTIVE
            for e in effects
            if e != EFFECT_ONLINE
        ):
            active.append(type_id)
        values = {a["attributeID"]: a["value"] for a in d.get("dogmaAttributes", [])}
        if ATTRIBUTE_SQUADRON_SIZE in values:
            squadron[type_id] = values[ATTRIBUTE_SQUADRON_SIZE]
        if type_id in rollable:
            base_values[type_id] = {a: values[a] for a in rollable[type_id] if a in values}

    attributes = [
        [a["_key"], a["name"], int(bool(a.get("published"))), a.get("defaultValue", 0.0)]
        for a in _rows(zf, "dogmaAttributes.jsonl")
    ]

    return {
        "build": build,
        "groups": groups,
        "types": types,
        "slots": slots,
        "active": active,
        "squadron": squadron,
        "attributes": attributes,
        "mutaplasmids": mutaplasmids,
        "base_values": base_values,
    }


def _best(candidates: list, published) -> int | None:
    """Pick among same-named entries: published first, then the lowest ID."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: (not published(c), c))


class SDE:
    def __init__(self, data: dict):
        self.build = data["build"]
        groups = {int(k): v for k, v in data["groups"].items()}

        self.types: dict[int, Type] = {}
        by_name: dict[str, list[int]] = {}
        for type_id, name, group, published, volume, capacity in data["types"]:
            self.types[type_id] = Type(
                type_id, name, group, groups.get(group, 0), bool(published), volume, capacity
            )
            by_name.setdefault(fold(name), []).append(type_id)
        self._type_by_name = by_name

        self.slots = {int(k): v for k, v in data["slots"].items()}
        self.active = set(data["active"])
        self.squadron = {int(k): v for k, v in data["squadron"].items()}

        self.attributes: dict[int, Attribute] = {}
        attr_by_name: dict[str, list[int]] = {}
        for attr_id, name, published, default in data["attributes"]:
            self.attributes[attr_id] = Attribute(attr_id, name, bool(published), default)
            attr_by_name.setdefault(fold(name), []).append(attr_id)
        self._attr_by_name = attr_by_name

        self.mutaplasmids = {
            int(k): (set(v["bases"]), v["attrs"]) for k, v in data["mutaplasmids"].items()
        }
        self.base_values = {
            int(k): {int(a): v for a, v in values.items()}
            for k, values in data["base_values"].items()
        }

        self.modes: dict[int, list[int]] = {}
        hulls = {t.name: t.id for t in self.types.values() if t.category == CATEGORY_SHIP}
        for t in self.types.values():
            if t.group != GROUP_SHIP_MODIFIERS:
                continue
            words = t.name.split(" ")
            for n in range(len(words) - 1, 0, -1):
                hull = hulls.get(" ".join(words[:n]))
                if hull is not None:
                    self.modes.setdefault(hull, []).append(t.id)
                    break

    @classmethod
    def load(cls) -> "SDE":
        path = cache_path()
        if not path.exists():
            fetch()
        with open(path) as f:
            return cls(json.load(f))

    def type_by_name(self, name: str) -> Type | None:
        candidates = self._type_by_name.get(fold(name), [])
        best = _best(candidates, lambda c: self.types[c].published)
        return None if best is None else self.types[best]

    def attribute_by_name(self, name: str) -> Attribute | None:
        candidates = self._attr_by_name.get(fold(name), [])
        best = _best(candidates, lambda c: self.attributes[c].published)
        return None if best is None else self.attributes[best]

    def mutaplasmids_for(self, base: int) -> list[int]:
        return sorted(m for m, (bases, _) in self.mutaplasmids.items() if base in bases)

    def rollable(self, mutaplasmid: int) -> list[int]:
        return self.mutaplasmids[mutaplasmid][1]

    def base_value(self, type_id: int, attr_id: int) -> float:
        value = self.base_values.get(type_id, {}).get(attr_id)
        return self.attributes[attr_id].default if value is None else value

    def full_load(self, item: Type, charge: Type) -> int | None:
        if item.capacity <= 0 or charge.volume <= 0:
            return None
        return int(Fraction(str(item.capacity)) / Fraction(str(charge.volume)))
