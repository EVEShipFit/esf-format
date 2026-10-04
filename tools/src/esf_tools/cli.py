"""Command line: esf check | canonical | binary | sde."""

import argparse
import sys
import traceback

import esf
from esf import EsfError, is_text

from . import base64url, sde


def from_base64(data: bytes) -> bytes:
    if is_text(data):
        return data
    try:
        return base64url.decode(data)
    except ValueError:
        raise EsfError("not valid base64url") from None


def main(argv: list[str] | None = None) -> int:
    """Exit 0 for valid, 1 for invalid, 2 for anything else."""
    try:
        return _main(argv)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 2


def _main(argv: list[str] | None) -> int:
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
        fits = esf.read(data, esf.Lookup(sde.SDE.load()))
    except EsfError as e:
        print(f"invalid: {e}", file=sys.stderr)
        return 1

    if args.command == "canonical":
        sys.stdout.buffer.write(esf.to_text(fits).encode())
    elif args.command == "binary":
        out = esf.to_binary(fits)
        if args.b64:
            out = base64url.encode(out) + b"\n"
        sys.stdout.buffer.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
