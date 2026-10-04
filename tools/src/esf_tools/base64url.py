"""Base64url without padding (RFC 4648 §5), as the binary form uses in text."""

import base64
import re

_ALPHABET = re.compile(rb"[A-Za-z0-9_-]*")


def decode(data: bytes) -> bytes:
    data = data.strip()
    if not _ALPHABET.fullmatch(data) or len(data) % 4 == 1:
        raise ValueError("not valid base64url")
    return base64.urlsafe_b64decode(data + b"=" * (-len(data) % 4))


def encode(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")
