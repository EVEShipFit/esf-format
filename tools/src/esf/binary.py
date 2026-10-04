"""The binary form (SPEC §10)."""

import math

from google.protobuf.message import DecodeError
from google.protobuf.unknown_fields import UnknownFieldSet

from . import esf_pb2
from .canonical import CanonFit, number, quote, quote_type
from .lookup import Lookup
from .resolve import Fit
from .text import EsfError


def _state(name: str) -> int:
    return esf_pb2.State.Value(f"STATE_{name.upper()}")


def _location(name: str) -> int:
    return esf_pb2.Location.Value(f"LOCATION_{name.upper()}")


def encode(fits: list[CanonFit]) -> bytes:
    doc = esf_pb2.Document()
    for fit in fits:
        f = doc.fits.add(version=1)
        if fit.hull is not None:
            f.hull = fit.hull.id
        if fit.name is not None:
            f.name = fit.name
        if fit.mode is not None:
            f.tactical_mode = fit.mode.id
        for line in fit.lines:
            e = f.entries.add()
            if line.type is not None:
                e.type = line.type.id
            if line.count is not None:
                e.count = line.count
            if line.fit_name is not None:
                e.fit_name = line.fit_name
            if line.charge is not None:
                e.charge = line.charge.id
            if line.charge_count is not None:
                e.charge_count = line.charge_count
            if line.mutaplasmid is not None:
                e.mutaplasmid = line.mutaplasmid.id
            e.override_attributes.extend(a.id for a, _ in line.overrides)
            e.override_values.extend(v for _, v in line.overrides)
            if line.state is not None:
                e.state = _state(line.state)
            if line.location is not None:
                e.location = _location(line.location)
    return doc.SerializeToString(deterministic=True)


def _check_schema(message, what: str):
    if len(UnknownFieldSet(message)):
        raise EsfError(f"binary: {what} has a field that is not in the schema")


def _enum(enum, value: int, prefix: str) -> str | None:
    if value not in enum.values():
        raise EsfError(f"binary: unknown {enum.DESCRIPTOR.name} value {value}")
    return None if value == 0 else enum.Name(value).removeprefix(prefix).lower()


def _name(text: str, what: str) -> str:
    if "\r" in text or "\n" in text:
        raise EsfError(f"binary: {what} contains CR or LF")
    return quote(text)


def _type_name(lookup: Lookup, type_id: int, what: str) -> str:
    t = lookup.types.get(type_id)
    if t is None:
        raise EsfError(f"binary: unknown {what} type ID {type_id}")
    return quote_type(t.name)


def _entry(e, lookup: Lookup) -> str:
    _check_schema(e, "Entry")
    parts = []
    if e.HasField("count"):
        parts.append(f"{e.count}x")
    parts.append(_type_name(lookup, e.type, "item") if e.HasField("type") else "-")
    if e.fit_name:
        parts.append(_name(e.fit_name, "Entry.fit_name"))
    if e.HasField("charge_count") and not e.HasField("charge"):
        raise EsfError("binary: charge_count is set without charge")
    if e.HasField("charge"):
        count = f"{e.charge_count}x " if e.HasField("charge_count") else ""
        parts.append(f":{count}{_type_name(lookup, e.charge, 'charge')}")
    if e.HasField("mutaplasmid"):
        parts.append("+" + _type_name(lookup, e.mutaplasmid, "mutaplasmid"))
    if len(e.override_attributes) != len(e.override_values):
        raise EsfError("binary: override fields have different lengths")
    if e.override_attributes:
        pairs = []
        for attr_id, value in zip(e.override_attributes, e.override_values):
            attr = lookup.attributes.get(attr_id)
            if attr is None:
                raise EsfError(f"binary: unknown attribute ID {attr_id}")
            if not math.isfinite(value):
                raise EsfError("binary: an override value is not finite")
            pairs.append(f"{attr.name} {number(value)}")
        parts.append("{" + ", ".join(pairs) + "}")
    if state := _enum(esf_pb2.State, e.state, "STATE_"):
        parts.append("!" + state)
    if location := _enum(esf_pb2.Location, e.location, "LOCATION_"):
        parts.append("@" + location)
    return " ".join(parts)


def decode(data: bytes, lookup: Lookup) -> tuple[bytes, esf_pb2.Document]:
    """Map a binary document to the text it stands for."""
    if not data:
        raise EsfError("binary: the document is empty")
    doc = esf_pb2.Document()
    try:
        doc.ParseFromString(data)
    except DecodeError as e:
        raise EsfError(f"binary: not valid Protocol Buffers ({e})") from None
    if any(field.field_number == 1 for field in UnknownFieldSet(doc)):
        raise EsfError("binary: Document.fits has the wrong wire type")

    out = []
    for f in doc.fits:
        _check_schema(f, "Fit")
        if f.version != 1:
            raise EsfError(f"binary: unsupported Fit.version {f.version}")
        hull = [_type_name(lookup, f.hull, "hull") if f.HasField("hull") else "-"]
        if f.name:
            hull.append(_name(f.name, "Fit.name"))
        if f.HasField("tactical_mode"):
            hull.append("/" + _type_name(lookup, f.tactical_mode, "tactical mode"))
        out += ["%esf/1", " ".join(hull)]
        out += [_entry(e, lookup) for e in f.entries]
        out.append("")
    return "\n".join(out).encode(), doc


def verify(fits: list[Fit], doc: esf_pb2.Document):
    """Check that every ID is the one its name resolves to."""

    def same(got, message, field: str, what: str):
        want = getattr(message, field) if message.HasField(field) else None
        got_id = None if got is None else got.id
        if got_id != want:
            raise EsfError(f"binary: {what} ID {want} is not what its name resolves to ({got_id})")

    for fit, f in zip(fits, doc.fits):
        same(fit.hull, f, "hull", "hull")
        same(fit.mode, f, "tactical_mode", "tactical mode")
        for item, e in zip(fit.items, f.entries):
            same(item.type, e, "type", "type")
            same(item.charge, e, "charge", "charge")
            same(item.mutaplasmid, e, "mutaplasmid", "mutaplasmid")
            got = [a.id for a, _ in item.overrides]
            if got != list(e.override_attributes):
                raise EsfError(
                    f"binary: attribute IDs {list(e.override_attributes)} resolve to {got}"
                )
