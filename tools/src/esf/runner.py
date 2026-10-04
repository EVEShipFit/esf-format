"""Run the esf/1 test cases against any tool: esf-test [options] -- COMMAND..."""

import argparse
import base64
import difflib
import os
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TESTS = Path(__file__).resolve().parents[3] / "tests"


@dataclass
class Case:
    path: Path
    valid: bool
    spec: str
    description: str

    @property
    def name(self) -> str:
        return f"{'valid' if self.valid else 'invalid'}/{self.path.name}"

    @property
    def input_path(self) -> Path:
        for name in ("input.esf", "input.b64"):
            if (self.path / name).exists():
                return self.path / name
        raise FileNotFoundError(f"{self.path} has no input.esf or input.b64")

    @property
    def is_binary(self) -> bool:
        return self.input_path.suffix == ".b64"


def b64(path: Path) -> bytes:
    data = path.read_bytes().strip()
    return base64.urlsafe_b64decode(data + b"=" * (-len(data) % 4))


def load(path: Path) -> bytes:
    return b64(path) if path.suffix == ".b64" else path.read_bytes()


def discover(root: Path) -> list[Case]:
    cases = []
    for kind in ("valid", "invalid"):
        for path in sorted((root / kind).iterdir()):
            with open(path / "case.toml", "rb") as f:
                meta = tomllib.load(f)
            cases.append(Case(path, kind == "valid", meta["spec"], meta["description"]))
    return cases


class Runner:
    def __init__(self, command: list[str], canonical: bool, binary: bool):
        self.command = command
        self.canonical = canonical
        self.binary = binary

    def run(self, action: str, data: bytes) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*self.command, action], input=data, capture_output=True, timeout=60, check=False
        )

    def expect_valid(self, data: bytes, what: str) -> list[str]:
        result = self.run("check", data)
        if result.returncode != 0:
            return [
                f"{what}: rejected (exit {result.returncode}): {result.stderr.decode().strip()}"
            ]
        return []

    def expect_output(self, action: str, data: bytes, want: bytes, what: str) -> list[str]:
        result = self.run(action, data)
        if result.returncode != 0:
            return [f"{what}: exit {result.returncode}: {result.stderr.decode().strip()}"]
        if result.stdout == want:
            return []
        if action == "binary":
            got = base64.urlsafe_b64encode(result.stdout).rstrip(b"=").decode()
            return [
                (
                    f"{what}: binary differs\n  want {want.hex()}\n  got  {result.stdout.hex()}"
                    f"\n  got (base64url) {got}"
                )
            ]
        diff = difflib.unified_diff(
            want.decode(errors="replace").splitlines(keepends=True),
            result.stdout.decode(errors="replace").splitlines(keepends=True),
            "expected",
            "got",
        )
        return [f"{what}: output differs\n" + "".join(diff).rstrip()]

    def test(self, case: Case) -> list[str]:
        data = load(case.input_path)
        if not case.valid:
            result = self.run("check", data)
            if result.returncode == 1:
                return []
            if result.returncode == 0:
                return ["accepted an invalid document"]
            return [
                f"check: exit {result.returncode}, expected 1: {result.stderr.decode().strip()}"
            ]

        errors = self.expect_valid(data, "check input")
        canonical = (case.path / "canonical.esf").read_bytes()
        encoded = b64(case.path / "canonical.b64")
        if self.canonical:
            errors += self.expect_output("canonical", data, canonical, "canonical of input")
            errors += self.expect_output(
                "canonical", canonical, canonical, "canonical of canonical.esf"
            )
        if self.binary:
            errors += self.expect_output("binary", data, encoded, "binary of input")
            errors += self.expect_valid(encoded, "check canonical.b64")
            if self.canonical:
                errors += self.expect_output(
                    "canonical", encoded, canonical, "canonical of canonical.b64"
                )
        return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="esf-test",
        description=__doc__,
        epilog="The command is run as `COMMAND check|canonical|binary` with the document on "
        "stdin. See tests/README.md.",
    )
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS, help="test case directory")
    parser.add_argument("-k", dest="filter", default="", help="only cases whose name contains this")
    parser.add_argument("--no-canonical", action="store_true", help="skip canonical output checks")
    parser.add_argument(
        "--no-binary", action="store_true", help="skip binary form checks and cases"
    )
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count(), help="parallel jobs")
    parser.add_argument("-v", "--verbose", action="store_true", help="list every case")
    parser.add_argument("command", nargs="+", help="the tool to test")
    args = parser.parse_args(argv)

    cases = [c for c in discover(args.tests) if args.filter in c.name]
    if args.no_binary:
        cases = [c for c in cases if not c.is_binary]
    runner = Runner(args.command, not args.no_canonical, not args.no_binary)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(runner.test, cases))

    failed = 0
    for case, errors in zip(cases, results):
        if errors:
            failed += 1
            print(f"FAIL {case.name} (§{case.spec}): {case.description}")
            for error in errors:
                print("  " + error.replace("\n", "\n  "))
        elif args.verbose:
            print(f"ok   {case.name}")

    print(f"{len(cases) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
