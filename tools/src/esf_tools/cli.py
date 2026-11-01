"""Command line: esf check | canonical | binary | sde | catalog."""

import argparse
import sys
import traceback
from pathlib import Path

import esf_format
from esf_format import EsfError, is_text

from . import base64url, fixture, sde
from .catalog import SdeCatalog
from .runner import DEFAULT_TESTS


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
    parser.add_argument("--catalog", type=Path, help="read types from a test catalog, not the SDE")
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
    write = commands.add_parser("catalog", help="write the test catalog from the SDE")
    write.add_argument("--tests", type=Path, default=DEFAULT_TESTS, help="test case directory")
    write.add_argument(
        "--check", action="store_true", help="only check that the test catalog is up to date"
    )
    args = parser.parse_args(argv)

    if args.command == "sde":
        build = sde.fetch(force=args.force)
        print(f"SDE build {build} at {sde.cache_path()}")
        return 0

    if args.command == "catalog":
        return _catalog(args.tests, args.check)

    if args.file:
        with open(args.file, "rb") as f:
            data = f.read()
    else:
        data = sys.stdin.buffer.read()

    catalog = fixture.JsonCatalog(args.catalog) if args.catalog else SdeCatalog(sde.SDE.load())
    try:
        if args.b64:
            data = from_base64(data)
        fits = esf_format.load(data, catalog)
        if args.command == "canonical":
            out = esf_format.save(fits, catalog).encode()
        elif args.command == "binary":
            out = esf_format.save_binary(fits, catalog)
            if args.b64:
                out = base64url.encode(out) + b"\n"
        else:
            out = b""
    except EsfError as e:
        print(f"invalid: {e}", file=sys.stderr)
        return 1

    sys.stdout.buffer.write(out)
    return 0


def _catalog(tests: Path, check: bool) -> int:
    path = tests / "catalog.json"
    text = fixture.build(sde.SDE.load(), tests)
    if not check:
        path.write_text(text)
        print(f"wrote {path}")
        return 0
    if path.exists() and fixture.same(text, path.read_text()):
        return 0
    print(f"{path} is out of date; run `esf catalog`", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
