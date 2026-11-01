"""The test catalog: the types and attributes the test cases use."""

import json
from pathlib import Path

import esf
from esf import AttributeRecord, EsfError, Kind, MutaplasmidRecord, TypeRecord, fold

from .catalog import SdeCatalog
from .runner import discover, load


def _by_name(entries: list[dict]) -> dict[str, int]:
    """Map each folded name to its entry: published first, then the lowest ID (§4.2)."""
    index = {}
    for e in sorted(entries, key=lambda e: (not e["published"], e["id"])):
        index.setdefault(fold(e["name"]), e["id"])
    return index


class JsonCatalog:
    """A Catalog read from a test catalog file."""

    def __init__(self, path: Path):
        with open(path) as f:
            data = json.load(f)
        self._types = {
            t["id"]: TypeRecord(
                t["id"],
                t["name"],
                Kind(t["kind"]),
                t["active"],
                t["capacity"],
                t["volume"],
                t.get("squadron_size"),
            )
            for t in data["types"]
        }
        self._attributes = {
            a["id"]: AttributeRecord(a["id"], a["name"]) for a in data["attributes"]
        }
        self._type_names = _by_name(data["types"])
        self._attribute_names = _by_name(data["attributes"])
        self._modes = {m["hull"]: tuple(self._types[t] for t in m["modes"]) for m in data["modes"]}
        self._mutaplasmids: dict[int, tuple[MutaplasmidRecord, ...]] = {}
        for m in data["mutaplasmids"]:
            record = MutaplasmidRecord(self._types[m["mutaplasmid"]], tuple(map(tuple, m["rolls"])))
            self._mutaplasmids[m["base"]] = self._mutaplasmids.get(m["base"], ()) + (record,)

    def type(self, folded: str) -> TypeRecord | None:
        type_id = self._type_names.get(folded)
        return None if type_id is None else self._types[type_id]

    def type_by_id(self, type_id: int) -> TypeRecord | None:
        return self._types.get(type_id)

    def attribute(self, folded: str) -> AttributeRecord | None:
        attribute_id = self._attribute_names.get(folded)
        return None if attribute_id is None else self._attributes[attribute_id]

    def attribute_by_id(self, attribute_id: int) -> AttributeRecord | None:
        return self._attributes.get(attribute_id)

    def modes(self, hull_id: int) -> tuple[TypeRecord, ...]:
        return self._modes.get(hull_id, ())

    def mutaplasmids(self, type_id: int) -> tuple[MutaplasmidRecord, ...]:
        return self._mutaplasmids.get(type_id, ())


class _Recorder(SdeCatalog):
    """An SdeCatalog that remembers every record it returns, and every entry sharing a name."""

    def __init__(self, sde):
        super().__init__(sde)
        self.types: set[int] = set()
        self.attributes: set[int] = set()
        self.modes_of: dict[int, tuple[TypeRecord, ...]] = {}
        self.mutaplasmids_of: dict[int, tuple[MutaplasmidRecord, ...]] = {}
        self._all_type_names = _all_names(sde.types.values())
        self._all_attribute_names = _all_names(sde.attributes.values())

    def type(self, folded: str) -> TypeRecord | None:
        for type_id in self._all_type_names.get(folded, ()):
            self.type_by_id(type_id)
        return super().type(folded)

    def type_by_id(self, type_id: int) -> TypeRecord | None:
        record = super().type_by_id(type_id)
        if record is not None:
            self.types.add(record.id)
        return record

    def attribute(self, folded: str) -> AttributeRecord | None:
        for attribute_id in self._all_attribute_names.get(folded, ()):
            self.attribute_by_id(attribute_id)
        return super().attribute(folded)

    def attribute_by_id(self, attribute_id: int) -> AttributeRecord | None:
        record = super().attribute_by_id(attribute_id)
        if record is not None:
            self.attributes.add(record.id)
        return record

    def modes(self, hull_id: int) -> tuple[TypeRecord, ...]:
        modes = super().modes(hull_id)
        for m in modes:
            self.type(fold(m.name))
        self.modes_of[hull_id] = modes
        return modes

    def mutaplasmids(self, type_id: int) -> tuple[MutaplasmidRecord, ...]:
        mutaplasmids = super().mutaplasmids(type_id)
        for m in mutaplasmids:
            self.type(fold(m.type.name))
            for attribute_id, _ in m.rolls:
                self.attribute_by_id(attribute_id)
        self.mutaplasmids_of[type_id] = mutaplasmids
        return mutaplasmids


def _all_names(entries) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for e in entries:
        index.setdefault(fold(e.name), []).append(e.id)
    return index


def _documents(tests: Path):
    for case in discover(tests):
        yield load(case.input_path)
        if case.valid:
            yield (case.path / "canonical.esf").read_bytes()
            yield load(case.path / "canonical.b64")


def _dump(data: dict) -> str:
    """JSON with one entry of each top-level list per line."""
    out = []
    for key, value in data.items():
        if isinstance(value, list):
            items = "".join(f"\n    {json.dumps(v, ensure_ascii=False)}," for v in value)
            value = f"[{items.rstrip(',')}\n  ]"
        else:
            value = json.dumps(value)
        out.append(f"  {json.dumps(key)}: {value}")
    return "{\n" + ",\n".join(out) + "\n}\n"


def build(sde, tests: Path) -> str:
    """The test catalog for the test cases in `tests`, as JSON."""
    recorder = _Recorder(sde)
    for data in _documents(tests):
        try:
            fits = esf.read(data, recorder)
        except EsfError:
            continue
        esf.to_text(fits)
        esf.to_binary(fits)

    types = []
    for type_id in sorted(recorder.types):
        t = recorder.type_by_id(type_id)
        entry = {
            "id": t.id,
            "name": t.name,
            "published": sde.types[t.id].published,
            "kind": str(t.kind),
            "active": t.active,
            "capacity": t.capacity,
            "volume": t.volume,
        }
        if t.squadron_size is not None:
            entry["squadron_size"] = t.squadron_size
        types.append(entry)
    return _dump(
        {
            "build": sde.build,
            "types": types,
            "attributes": [
                {"id": a.id, "name": a.name, "published": a.published}
                for a in (sde.attributes[i] for i in sorted(recorder.attributes))
            ],
            "modes": [
                {"hull": hull, "modes": [m.id for m in modes]}
                for hull, modes in sorted(recorder.modes_of.items())
                if modes
            ],
            "mutaplasmids": [
                {"base": base, "mutaplasmid": m.type.id, "rolls": [list(r) for r in m.rolls]}
                for base, found in sorted(recorder.mutaplasmids_of.items())
                for m in found
            ],
        }
    )


def same(a: str, b: str) -> bool:
    """Whether two test catalogs hold the same data, whatever their SDE build."""
    a_data, b_data = json.loads(a), json.loads(b)
    a_data.pop("build")
    b_data.pop("build")
    return a_data == b_data
