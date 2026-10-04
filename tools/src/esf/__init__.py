"""Reference implementation of esf/1 (SPEC.md)."""

from . import binary, canonical, resolve, text
from .canonical import CanonFit
from .lookup import Lookup
from .text import EsfError

__all__ = ["CanonFit", "EsfError", "Lookup", "is_text", "read", "to_binary", "to_text"]


def is_text(data: bytes) -> bool:
    """Whether a document is text, by its first byte (§10)."""
    return data[:1] in (b"%", b" ")


def read(data: bytes, lookup: Lookup) -> list[CanonFit]:
    """Validate a text or binary document, and return its canonical form."""
    if is_text(data):
        return [
            canonical.canonical_fit(f, lookup) for f in resolve.resolve(text.parse(data), lookup)
        ]
    source, doc = binary.decode(data, lookup)
    fits = resolve.resolve(text.parse(source), lookup)
    binary.verify(fits, doc)
    return [canonical.canonical_fit(f, lookup) for f in fits]


def to_text(fits: list[CanonFit]) -> str:
    return canonical.render(fits)


def to_binary(fits: list[CanonFit]) -> bytes:
    return binary.encode(fits)
