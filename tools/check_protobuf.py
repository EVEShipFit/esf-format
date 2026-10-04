"""Check that every canonical.b64 round-trips through the official protobuf library."""

import base64
import importlib
import sys
import tempfile
from pathlib import Path

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    with tempfile.TemporaryDirectory() as out:
        if protoc.main(["protoc", f"-I{ROOT}", f"--python_out={out}", str(ROOT / "esf.proto")]):
            return 1
        sys.path.insert(0, out)
        esf_pb2 = importlib.import_module("esf_pb2")

    failed = 0
    paths = sorted((ROOT / "tests" / "valid").glob("*/canonical.b64"))
    for path in paths:
        text = path.read_bytes().strip()
        data = base64.urlsafe_b64decode(text + b"=" * (-len(text) % 4))
        doc = esf_pb2.Document()
        doc.ParseFromString(data)
        if doc.SerializeToString(deterministic=True) != data:
            print(f"FAIL {path.relative_to(ROOT)}: protobuf encodes it differently")
            failed += 1

    print(f"{len(paths) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
