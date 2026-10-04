"""What esf/1 reads from the SDE (SPEC §4.2, §5, §6)."""

from enum import StrEnum
from fractions import Fraction

from .names import fold

CONTAINER_GROUPS = (
    "Cargo Container",
    "Secure Cargo Container",
    "Audit Log Secure Container",
    "Freight Container",
)


class Kind(StrEnum):
    """What a type is, for placement (§5)."""

    HULL = "hull"
    MODIFIER = "modifier"
    SUB = "sub"
    HIGH = "high"
    MID = "mid"
    LOW = "low"
    RIG = "rig"
    SVC = "svc"
    DRONE = "drone"
    FIGHTER = "fighter"
    CHARGE = "charge"
    IMPLANT = "implant"
    BOOSTER = "booster"
    OTHER = "other"


SLOT_EFFECTS = {
    "hiPower": Kind.HIGH,
    "medPower": Kind.MID,
    "loPower": Kind.LOW,
    "rigSlot": Kind.RIG,
    "serviceSlot": Kind.SVC,
}
EFFECT_CATEGORY_ACTIVE = 1
EFFECT_CATEGORY_TARGET = 2
EFFECT_CATEGORY_ONLINE = 4
SQUADRON_SIZE = "fighterSquadronMaxSize"


def _best(candidates: list, published) -> int | None:
    """Pick among same-named entries: published first, then the lowest ID."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: (not published(c), c))


class Lookup:
    def __init__(self, sde):
        self.sde = sde
        self.types = sde.types
        self.attributes = sde.attributes

        groups = {g.name: g.id for g in sde.groups.values()}
        self._booster = groups["Booster"]
        self._ship_modifiers = groups["Ship Modifiers"]
        self._containers = {groups[name] for name in CONTAINER_GROUPS}

        self._types_by_name: dict[str, list[int]] = {}
        for t in sde.types.values():
            self._types_by_name.setdefault(fold(t.name), []).append(t.id)
        self._attributes_by_name: dict[str, list[int]] = {}
        for a in sde.attributes.values():
            self._attributes_by_name.setdefault(fold(a.name), []).append(a.id)

        effects = {e.name: e.id for e in sde.effects.values()}
        self._slot_effects = {effects[name]: rack for name, rack in SLOT_EFFECTS.items()}
        self._effect_categories = {e.id: e.category_id for e in sde.effects.values()}
        self._effect_categories[effects["online"]] = EFFECT_CATEGORY_ONLINE

        squadron = [a.id for a in sde.attributes.values() if a.name == SQUADRON_SIZE]
        self._squadron_size = squadron[0]

        self._modes: dict[int, list[int]] = {}
        hulls = {}
        for t in sorted(sde.types.values(), key=lambda t: (not t.published, t.id), reverse=True):
            if self.category(t) == "Ship":
                hulls[t.name] = t.id
        for t in sde.types.values():
            if t.group_id != self._ship_modifiers:
                continue
            words = t.name.split(" ")
            for n in range(len(words) - 1, 0, -1):
                hull = hulls.get(" ".join(words[:n]))
                if hull is not None:
                    self._modes.setdefault(hull, []).append(t.id)
                    break

    def category(self, t) -> str:
        return self.sde.categories[self.sde.groups[t.group_id].category_id].name

    def type_by_name(self, name: str):
        candidates = self._types_by_name.get(fold(name), [])
        best = _best(candidates, lambda c: self.types[c].published)
        return None if best is None else self.types[best]

    def attribute_by_name(self, name: str):
        candidates = self._attributes_by_name.get(fold(name), [])
        best = _best(candidates, lambda c: self.attributes[c].published)
        return None if best is None else self.attributes[best]

    def classify(self, t) -> Kind:
        if t.group_id == self._ship_modifiers:
            return Kind.MODIFIER
        category = self.category(t)
        if category in ("Ship", "Structure") or t.group_id in self._containers:
            return Kind.HULL
        if category == "Subsystem":
            return Kind.SUB
        if category in ("Module", "Structure Module"):
            for effect in self.sde.type_effects.get(t.id, ()):
                if effect in self._slot_effects:
                    return self._slot_effects[effect]
            return Kind.OTHER
        if category == "Implant":
            return Kind.BOOSTER if t.group_id == self._booster else Kind.IMPLANT
        return {"Drone": Kind.DRONE, "Fighter": Kind.FIGHTER, "Charge": Kind.CHARGE}.get(
            category, Kind.OTHER
        )

    def is_container(self, t) -> bool:
        return t.group_id in self._containers

    def is_active(self, t) -> bool:
        """Whether a type has an effect in the active or target category (§6.4)."""
        return any(
            self._effect_categories.get(e) in (EFFECT_CATEGORY_ACTIVE, EFFECT_CATEGORY_TARGET)
            for e in self.sde.type_effects.get(t.id, ())
        )

    def modes(self, hull) -> list:
        return [self.types[m] for m in self._modes.get(hull.id, [])]

    def mutaplasmids(self, base) -> list:
        return [
            self.types[m.id]
            for m in sorted(self.sde.mutaplasmids.values(), key=lambda m: m.id)
            if base.id in m.bases
        ]

    def rollable(self, mutaplasmid) -> tuple[int, ...]:
        return self.sde.mutaplasmids[mutaplasmid.id].attributes

    def base_value(self, t, attribute_id: int) -> float:
        value = self.sde.type_attributes.get(t.id, {}).get(attribute_id)
        return self.attributes[attribute_id].default if value is None else value

    def squadron_size(self, t) -> int | None:
        value = self.sde.type_attributes.get(t.id, {}).get(self._squadron_size)
        return None if value is None else int(value)

    def full_load(self, item, charge) -> int | None:
        """How many charges fit in an item (§6.5)."""
        if item.capacity <= 0 or charge.volume <= 0:
            return None
        return int(Fraction(str(item.capacity)) / Fraction(str(charge.volume)))
