"""Download, cache and load the SDE tables that esf/1 reads."""

import json
import os
import re
import sys
import tempfile
import urllib.request
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from esf.lookup import SQUADRON_SIZE

LATEST_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
CACHE_VERSION = 2


@dataclass(frozen=True)
class Type:
    id: int
    name: str
    group_id: int
    published: bool
    volume: float
    capacity: float


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    category_id: int


@dataclass(frozen=True)
class Category:
    id: int
    name: str


@dataclass(frozen=True)
class Effect:
    id: int
    name: str
    category_id: int


@dataclass(frozen=True)
class Attribute:
    id: int
    name: str
    published: bool
    default: float


@dataclass(frozen=True)
class Mutaplasmid:
    id: int
    bases: frozenset[int]
    attributes: tuple[int, ...]


class SDE:
    def __init__(self, data: dict):
        self.types = {r[0]: Type(r[0], r[1], r[2], bool(r[3]), r[4], r[5]) for r in data["types"]}
        self.groups = {r[0]: Group(*r) for r in data["groups"]}
        self.categories = {r[0]: Category(*r) for r in data["categories"]}
        self.effects = {r[0]: Effect(*r) for r in data["effects"]}
        self.attributes = {
            r[0]: Attribute(r[0], r[1], bool(r[2]), r[3]) for r in data["attributes"]
        }
        self.mutaplasmids = {
            r[0]: Mutaplasmid(r[0], frozenset(r[1]), tuple(r[2])) for r in data["mutaplasmids"]
        }
        self.type_effects: dict[int, tuple[int, ...]] = {
            int(k): tuple(v) for k, v in data["type_effects"].items()
        }
        self.type_attributes: dict[int, dict[int, float]] = {
            int(k): {int(a): v for a, v in values.items()}
            for k, values in data["type_attributes"].items()
        }

    @classmethod
    def load(cls) -> "SDE":
        data = _read(cache_path())
        if data is None:
            fetch()
            data = _read(cache_path())
        return cls(data)


def cache_path() -> Path:
    if path := os.environ.get("ESF_SDE"):
        return Path(path)
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "esf" / "sde.json"


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data if data.get("version") == CACHE_VERSION else None


@contextmanager
def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as f:
        try:
            import fcntl
        except ImportError:
            yield
            return
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def latest_build() -> tuple[int, str]:
    request = urllib.request.Request(LATEST_URL, method="HEAD")
    with urllib.request.urlopen(request) as response:
        url = response.geturl()
    match = re.search(r"-(\d+)-jsonl\.zip$", url)
    if not match:
        raise RuntimeError(f"cannot find the SDE build number in {url}")
    return int(match.group(1)), url


def fetch(force: bool = False) -> int:
    """Download the latest SDE into the cache, unless it is already there."""
    path = cache_path()
    with _lock(path):
        build, url = latest_build()
        cached = _read(path)
        if not force and cached is not None and cached["build"] == build:
            return build

        print(f"Downloading SDE build {build} ...", file=sys.stderr)
        with tempfile.TemporaryFile() as archive:
            with urllib.request.urlopen(url) as response:
                while chunk := response.read(1 << 20):
                    archive.write(chunk)
            archive.seek(0)
            with zipfile.ZipFile(archive) as zf:
                data = extract(zf)

        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
            json.dump(data, f, separators=(",", ":"))
        Path(f.name).replace(path)
        return build


def _rows(zf: zipfile.ZipFile, name: str):
    with zf.open(name) as f:
        for line in f:
            yield json.loads(line)


def extract(zf: zipfile.ZipFile) -> dict:
    """Read the tables esf/1 needs from an SDE archive (JSONL)."""
    build = next(_rows(zf, "_sde.jsonl"))["buildNumber"]

    types = [
        [
            t["_key"],
            t["name"]["en"],
            t["groupID"],
            int(bool(t.get("published"))),
            t.get("volume", 0.0),
            t.get("capacity", 0.0),
        ]
        for t in _rows(zf, "types.jsonl")
        if t["name"].get("en")
    ]
    groups = [[g["_key"], g["name"]["en"], g["categoryID"]] for g in _rows(zf, "groups.jsonl")]
    categories = [[c["_key"], c["name"]["en"]] for c in _rows(zf, "categories.jsonl")]
    effects = [
        [e["_key"], e["name"], e.get("effectCategoryID", 0)]
        for e in _rows(zf, "dogmaEffects.jsonl")
    ]
    attributes = [
        [a["_key"], a["name"], int(bool(a.get("published"))), a.get("defaultValue", 0.0)]
        for a in _rows(zf, "dogmaAttributes.jsonl")
    ]

    mutaplasmids = []
    for d in _rows(zf, "dynamicItemAttributes.jsonl"):
        bases = sorted({b for m in d["inputOutputMapping"] for b in m["applicableTypes"]})
        mutaplasmids.append([d["_key"], bases, sorted(a["_key"] for a in d["attributeIDs"])])

    kept = {a for _, _, attrs in mutaplasmids for a in attrs}
    kept |= {a[0] for a in attributes if a[1] == SQUADRON_SIZE}

    type_effects = {}
    type_attributes = {}
    for d in _rows(zf, "typeDogma.jsonl"):
        if effects_of := [e["effectID"] for e in d.get("dogmaEffects", [])]:
            type_effects[d["_key"]] = effects_of
        values = {
            a["attributeID"]: a["value"]
            for a in d.get("dogmaAttributes", [])
            if a["attributeID"] in kept
        }
        if values:
            type_attributes[d["_key"]] = values

    return {
        "version": CACHE_VERSION,
        "build": build,
        "types": types,
        "groups": groups,
        "categories": categories,
        "effects": effects,
        "attributes": attributes,
        "mutaplasmids": mutaplasmids,
        "type_effects": type_effects,
        "type_attributes": type_attributes,
    }
