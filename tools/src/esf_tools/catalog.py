"""An esf/1 Catalog backed by the SDE."""

from esf_format import AttributeRecord, Kind, MutaplasmidRecord, TypeRecord, fold

from .sde import SDE, SQUADRON_SIZE

CONTAINER_GROUPS = (
    "Cargo Container",
    "Secure Cargo Container",
    "Audit Log Secure Container",
    "Freight Container",
)
SLOT_EFFECTS = {
    "hiPower": Kind.HIGH,
    "medPower": Kind.MID,
    "loPower": Kind.LOW,
    "rigSlot": Kind.RIG,
    "serviceSlot": Kind.SVC,
}
CATEGORY_KINDS = {
    "Ship": Kind.HULL,
    "Structure": Kind.HULL,
    "Subsystem": Kind.SUB,
    "Drone": Kind.DRONE,
    "Fighter": Kind.FIGHTER,
    "Charge": Kind.CHARGE,
}
EFFECT_CATEGORY_ACTIVE = 1
EFFECT_CATEGORY_TARGET = 2
EFFECT_CATEGORY_ONLINE = 4


def _index(entries) -> dict[str, int]:
    """Map each folded name to its entry: published first, then the lowest ID (§4.2)."""
    index = {}
    for e in sorted(entries, key=lambda e: (not e.published, e.id), reverse=True):
        index[fold(e.name)] = e.id
    return index


class SdeCatalog:
    def __init__(self, sde: SDE):
        self._sde = sde
        self._types: dict[int, TypeRecord] = {}
        self._attributes: dict[int, AttributeRecord] = {}
        self._mutaplasmids: dict[int, tuple[MutaplasmidRecord, ...]] = {}

        self._type_names = _index(sde.types.values())
        self._attribute_names = _index(sde.attributes.values())

        groups = {g.name: g.id for g in sde.groups.values()}
        self._booster = groups["Booster"]
        self._ship_modifiers = groups["Ship Modifiers"]
        self._containers = {groups[name] for name in CONTAINER_GROUPS}

        effects = {e.name: e.id for e in sde.effects.values()}
        self._slot_effects = {effects[name]: kind for name, kind in SLOT_EFFECTS.items()}
        self._effect_categories = {e.id: e.category_id for e in sde.effects.values()}
        self._effect_categories[effects["online"]] = EFFECT_CATEGORY_ONLINE
        self._squadron_size = next(a.id for a in sde.attributes.values() if a.name == SQUADRON_SIZE)

        modes: dict[int, list[int]] = {}
        hulls = {
            t.name: t.id
            for t in sorted(sde.types.values(), key=lambda t: (not t.published, t.id), reverse=True)
            if self._category(t) == "Ship"
        }
        for t in sde.types.values():
            if t.group_id != self._ship_modifiers:
                continue
            words = t.name.split(" ")
            for n in range(len(words) - 1, 0, -1):
                hull = hulls.get(" ".join(words[:n]))
                if hull is not None:
                    modes.setdefault(hull, []).append(t.id)
                    break
        self._modes = {hull: tuple(self._record(m) for m in ids) for hull, ids in modes.items()}

    def type(self, folded: str) -> TypeRecord | None:
        type_id = self._type_names.get(folded)
        return None if type_id is None else self.type_by_id(type_id)

    def type_by_id(self, type_id: int) -> TypeRecord | None:
        return self._record(type_id)

    def _record(self, type_id: int) -> TypeRecord | None:
        if type_id not in self._types:
            t = self._sde.types.get(type_id)
            if t is None:
                return None
            self._types[type_id] = TypeRecord(
                t.id,
                t.name,
                self._kind(t),
                self._active(t),
                t.capacity,
                t.volume,
                self._squadron(t),
            )
        return self._types[type_id]

    def attribute(self, folded: str) -> AttributeRecord | None:
        attribute_id = self._attribute_names.get(folded)
        return None if attribute_id is None else self.attribute_by_id(attribute_id)

    def attribute_by_id(self, attribute_id: int) -> AttributeRecord | None:
        if attribute_id not in self._attributes:
            a = self._sde.attributes.get(attribute_id)
            if a is None:
                return None
            self._attributes[attribute_id] = AttributeRecord(a.id, a.name)
        return self._attributes[attribute_id]

    def modes(self, hull_id: int) -> tuple[TypeRecord, ...]:
        return self._modes.get(hull_id, ())

    def mutaplasmids(self, type_id: int) -> tuple[MutaplasmidRecord, ...]:
        if type_id not in self._mutaplasmids:
            values = self._sde.type_attributes.get(type_id, {})
            self._mutaplasmids[type_id] = tuple(
                MutaplasmidRecord(
                    self.type_by_id(m.id),
                    tuple(
                        (a, values.get(a, self._sde.attributes[a].default)) for a in m.attributes
                    ),
                )
                for m in sorted(self._sde.mutaplasmids.values(), key=lambda m: m.id)
                if type_id in m.bases
            )
        return self._mutaplasmids[type_id]

    def _category(self, t) -> str:
        return self._sde.categories[self._sde.groups[t.group_id].category_id].name

    def _kind(self, t) -> Kind:
        if t.group_id == self._ship_modifiers:
            return Kind.MODE
        if t.group_id in self._containers:
            return Kind.CONTAINER
        category = self._category(t)
        if category in ("Module", "Structure Module"):
            for effect in self._sde.type_effects.get(t.id, ()):
                if effect in self._slot_effects:
                    return self._slot_effects[effect]
            return Kind.OTHER
        if category == "Implant":
            return Kind.BOOSTER if t.group_id == self._booster else Kind.IMPLANT
        return CATEGORY_KINDS.get(category, Kind.OTHER)

    def _active(self, t) -> bool:
        """Whether a type has an effect in the active or target category (§6.4)."""
        return any(
            self._effect_categories.get(e) in (EFFECT_CATEGORY_ACTIVE, EFFECT_CATEGORY_TARGET)
            for e in self._sde.type_effects.get(t.id, ())
        )

    def _squadron(self, t) -> int | None:
        value = self._sde.type_attributes.get(t.id, {}).get(self._squadron_size)
        return None if value is None else int(value)
