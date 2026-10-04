"""Command line: esf check | canonical | binary | sde."""

import argparse
import base64
import binascii
import sys

from . import binary, canonical, resolve, sde, text
from .text import EsfError


def is_text(data: bytes) -> bool:
    return data[:1] in (b"%", b" ")


def read(data: bytes, db: sde.SDE) -> list[canonical.CanonFit]:
    """Validate a text or binary document, and return its canonical form."""
    if is_text(data):
        fits = resolve.resolve(text.parse(data), db)
    else:
        source, expected = binary.decode(data, db)
        fits = resolve.resolve(text.parse(source), db)
        binary.verify(fits, expected)
    return [canonical.canonical_fit(fit, db) for fit in fits]


def from_base64(data: bytes) -> bytes:
    if is_text(data):
        return data
    data = data.strip()
    try:
        return base64.urlsafe_b64decode(data + b"=" * (-len(data) % 4))
    except (binascii.Error, ValueError):
        raise EsfError("not valid base64url") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esf", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (
        ("check", "validate a document"),
        ("canonical", "write the canonical text form"),
        ("binary", "write the binary form"),
    ):
        cmd = commands.add_parser(name, help=help)
        cmd.add_argument("file", nargs="?", help="input file (default: stdin)")
        cmd.add_argument("--b64", action="store_true", help="binary form is base64url, in and out")
    fetch = commands.add_parser("sde", help="download the latest SDE into the cache")
    fetch.add_argument("--force", action="store_true", help="download even if up to date")
    args = parser.parse_args(argv)

    if args.command == "sde":
        build = sde.fetch(force=args.force)
        print(f"SDE build {build} at {sde.cache_path()}")
        return 0

    if args.file:
        with open(args.file, "rb") as f:
            data = f.read()
    else:
        data = sys.stdin.buffer.read()

    try:
        if args.b64:
            data = from_base64(data)
        fits = read(data, sde.SDE.load())
    except EsfError as e:
        print(f"invalid: {e}", file=sys.stderr)
        return 1

    if args.command == "canonical":
        sys.stdout.buffer.write(canonical.render(fits).encode())
    elif args.command == "binary":
        out = binary.encode(fits)
        if args.b64:
            out = base64.urlsafe_b64encode(out).rstrip(b"=") + b"\n"
        sys.stdout.buffer.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
