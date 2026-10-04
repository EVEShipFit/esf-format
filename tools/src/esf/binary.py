"""The binary form (SPEC §10)."""

import math
import struct
from dataclasses import dataclass, field

from .canonical import CanonFit, quote, quote_type
from .canonical import number as format_number
from .resolve import Fit
from .sde import SDE
from .text import HOLDS, EsfError

STATES = ("off", "on", "heat")
LOCATIONS = ("high", "mid", "low", "rig", "sub", "svc", "cargo", "bay", *HOLDS)

VARINT, I64, LEN, I32 = 0, 1, 2, 5
UINT32_MAX = (1 << 32) - 1


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(number: int, wire: int) -> bytes:
    return _varint(number << 3 | wire)


def _uint(number: int, value: int | None) -> bytes:
    return b"" if value is None else _key(number, VARINT) + _varint(value)


def _bytes(number: int, value: bytes) -> bytes:
    return _key(number, LEN) + _varint(len(value)) + value


def _encode_line(line) -> bytes:
    out = _uint(1, line.type.id if line.type else None)
    out += _uint(2, line.count)
    if line.fit_name:
        out += _bytes(3, line.fit_name.encode())
    out += _uint(4, line.charge.id if line.charge else None)
    out += _uint(5, line.charge_count)
    out += _uint(6, line.mutaplasmid.id if line.mutaplasmid else None)
    if line.overrides:
        out += _bytes(7, b"".join(_varint(a.id) for a, _ in line.overrides))
        out += _bytes(8, b"".join(struct.pack("<d", v) for _, v in line.overrides))
    if line.state:
        out += _uint(9, STATES.index(line.state) + 1)
    if line.location:
        out += _uint(10, LOCATIONS.index(line.location) + 1)
    return out


def encode(fits: list[CanonFit]) -> bytes:
    out = b""
    for fit in fits:
        body = _uint(1, 1)
        body += _uint(2, fit.hull.id if fit.hull else None)
        if fit.name:
            body += _bytes(3, fit.name.encode())
        body += _uint(4, fit.mode.id if fit.mode else None)
        for line in fit.lines:
            body += _bytes(5, _encode_line(line))
        out += _bytes(1, body)
    return out


def _varint_at(data: bytes, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if i >= len(data):
            raise EsfError("binary: truncated varint")
        if shift >= 64:
            raise EsfError("binary: varint is too long")
        byte = data[i]
        i += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, i


def _fields(data: bytes):
    """Yield (field number, wire type, value) for each record in a message."""
    i = 0
    while i < len(data):
        key, i = _varint_at(data, i)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise EsfError("binary: field number 0")
        if wire == VARINT:
            value, i = _varint_at(data, i)
        elif wire in (I64, I32, LEN):
            size = 8 if wire == I64 else 4
            if wire == LEN:
                size, i = _varint_at(data, i)
            if i + size > len(data):
                raise EsfError("binary: truncated record")
            value = data[i : i + size]
            i += size
        else:
            raise EsfError(f"binary: unsupported wire type {wire}")
        yield number, wire, value


def _packed(data: bytes) -> list[int]:
    out = []
    i = 0
    while i < len(data):
        value, i = _varint_at(data, i)
        out.append(value)
    return out


def _expect(number: int, wire: int, expected: int, message: str):
    if wire != expected:
        raise EsfError(f"binary: {message} field {number} has the wrong wire type")


def _uint32(value: int, what: str) -> int:
    if value > UINT32_MAX:
        raise EsfError(f"binary: {what} is out of range")
    return value


def _enum(value: int, size: int, what: str) -> int:
    if value > size:
        raise EsfError(f"binary: unknown {what} value {value}")
    return value


def _string(value: bytes, what: str) -> str:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        raise EsfError(f"binary: {what} is not valid UTF-8") from None
    if "\r" in text or "\n" in text:
        raise EsfError(f"binary: {what} contains CR or LF")
    return text


@dataclass
class _Entry:
    type: int | None = None
    count: int | None = None
    fit_name: str = ""
    charge: int | None = None
    charge_count: int | None = None
    mutaplasmid: int | None = None
    attributes: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    state: int = 0
    location: int = 0


@dataclass
class _Fit:
    version: int = 0
    hull: int | None = None
    name: str = ""
    mode: int | None = None
    entries: list[_Entry] = field(default_factory=list)


def _entry(data: bytes) -> _Entry:
    e = _Entry()
    for number, wire, value in _fields(data):
        if number in (1, 2, 4, 5, 6):
            _expect(number, wire, VARINT, "Entry")
            value = _uint32(value, f"Entry field {number}")
            name = {1: "type", 2: "count", 4: "charge", 5: "charge_count", 6: "mutaplasmid"}
            setattr(e, name[number], value)
        elif number == 3:
            _expect(number, wire, LEN, "Entry")
            e.fit_name = _string(value, "Entry.fit_name")
        elif number == 7:
            if wire == VARINT:
                e.attributes.append(_uint32(value, "an attribute ID"))
            else:
                _expect(number, wire, LEN, "Entry")
                e.attributes += [_uint32(v, "an attribute ID") for v in _packed(value)]
        elif number == 8:
            if wire == I64:
                e.values.append(struct.unpack("<d", value)[0])
            else:
                _expect(number, wire, LEN, "Entry")
                if len(value) % 8:
                    raise EsfError("binary: truncated override_values")
                e.values += [v for (v,) in struct.iter_unpack("<d", value)]
        elif number == 9:
            _expect(number, wire, VARINT, "Entry")
            e.state = _enum(value, len(STATES), "State")
        elif number == 10:
            _expect(number, wire, VARINT, "Entry")
            e.location = _enum(value, len(LOCATIONS), "Location")
        else:
            raise EsfError(f"binary: unknown Entry field {number}")
    return e


def _fit(data: bytes) -> _Fit:
    f = _Fit()
    for number, wire, value in _fields(data):
        if number in (1, 2, 4):
            _expect(number, wire, VARINT, "Fit")
            value = _uint32(value, f"Fit field {number}")
            setattr(f, {1: "version", 2: "hull", 4: "mode"}[number], value)
        elif number == 3:
            _expect(number, wire, LEN, "Fit")
            f.name = _string(value, "Fit.name")
        elif number == 5:
            _expect(number, wire, LEN, "Fit")
            f.entries.append(_entry(value))
        else:
            raise EsfError(f"binary: unknown Fit field {number}")
    return f


@dataclass
class Expected:
    """The IDs a decoded document must resolve back to (SPEC §10.2)."""

    fits: list[_Fit]


def _type_name(sde: SDE, type_id: int, what: str) -> str:
    t = sde.types.get(type_id)
    if t is None:
        raise EsfError(f"binary: unknown {what} type ID {type_id}")
    return quote_type(t.name)


def decode(data: bytes, sde: SDE) -> tuple[bytes, Expected]:
    """Map a binary document to the text it stands for."""
    if not data:
        raise EsfError("binary: the document is empty")

    fits = []
    for number, wire, value in _fields(data):
        if number == 1:
            _expect(number, wire, LEN, "Document")
            fits.append(_fit(value))

    out = []
    for f in fits:
        if f.version != 1:
            raise EsfError(f"binary: unsupported Fit.version {f.version}")
        hull = ["-" if f.hull is None else _type_name(sde, f.hull, "hull")]
        if f.name:
            hull.append(quote(f.name))
        if f.mode is not None:
            hull.append("/" + _type_name(sde, f.mode, "tactical mode"))
        out += ["%esf/1", " ".join(hull)]

        for e in f.entries:
            parts = []
            if e.count is not None:
                parts.append(f"{e.count}x")
            parts.append("-" if e.type is None else _type_name(sde, e.type, "item"))
            if e.fit_name:
                parts.append(quote(e.fit_name))
            if e.charge_count is not None and e.charge is None:
                raise EsfError("binary: charge_count is set without charge")
            if e.charge is not None:
                count = "" if e.charge_count is None else f"{e.charge_count}x "
                parts.append(f":{count}{_type_name(sde, e.charge, 'charge')}")
            if e.mutaplasmid is not None:
                parts.append("+" + _type_name(sde, e.mutaplasmid, "mutaplasmid"))
            if len(e.attributes) != len(e.values):
                raise EsfError("binary: override fields have different lengths")
            if e.attributes:
                pairs = []
                for attr_id, value in zip(e.attributes, e.values):
                    attr = sde.attributes.get(attr_id)
                    if attr is None:
                        raise EsfError(f"binary: unknown attribute ID {attr_id}")
                    if not math.isfinite(value):
                        raise EsfError("binary: an override value is not finite")
                    pairs.append(f"{attr.name} {format_number(value)}")
                parts.append("{" + ", ".join(pairs) + "}")
            if e.state:
                parts.append("!" + STATES[e.state - 1])
            if e.location:
                parts.append("@" + LOCATIONS[e.location - 1])
            out.append(" ".join(parts))
        out.append("")

    return "\n".join(out).encode(), Expected(fits)


def verify(fits: list[Fit], expected: Expected):
    """Check that every ID is the one its name resolves to."""

    def same(got, want: int | None, what: str):
        got_id = None if got is None else got.id
        if got_id != want:
            raise EsfError(f"binary: {what} ID {want} is not what its name resolves to ({got_id})")

    for fit, f in zip(fits, expected.fits):
        same(fit.hull, f.hull, "hull")
        same(fit.mode, f.mode, "tactical mode")
        for item, e in zip(fit.items, f.entries):
            same(item.type, e.type, "type")
            same(item.charge, e.charge, "charge")
            same(item.mutaplasmid, e.mutaplasmid, "mutaplasmid")
            got = [a.id for a, _ in item.overrides]
            if got != e.attributes:
                raise EsfError(f"binary: attribute IDs {e.attributes} resolve to {got}")
