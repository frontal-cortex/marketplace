#!/usr/bin/env python3
"""Refuse a changed pack whose version was not bumped.

    tools/check_versions.py <base index.json>

Compares every pack in the checkout with the index the base branch published:
same version but different file hashes (or a different file list) is an
error, and so is a version going backwards. New packs and removed packs are
fine. Users only ever see a change through Update, and Update keys on the
version — a silent edit would never reach them.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packlib import PackError, load_pack, sha256_hex  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def semver_key(v: str) -> tuple:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    base = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    published = {e["id"]: e for e in base.get("packs", [])}
    errors = 0
    for d in sorted(p for p in (ROOT / "packs").iterdir() if p.is_dir()):
        try:
            pack = load_pack(d)
        except PackError:
            continue  # lint reports it
        old = published.get(pack.id)
        if not old:
            print(f"{pack.id}: new pack")
            continue
        now_v, old_v = str(pack.manifest.get("version", "")), str(old.get("version", ""))
        hashes = {p: sha256_hex(b) for p, b in pack.files.items()}
        changed = hashes != old.get("sha256", {})
        if semver_key(now_v) < semver_key(old_v):
            print(f"{pack.id}: error: version {now_v} is lower than the published {old_v}")
            errors += 1
        elif changed and now_v == old_v:
            diff = sorted(p for p in set(hashes) | set(old.get("sha256", {})) if hashes.get(p) != old.get("sha256", {}).get(p))
            print(f"{pack.id}: error: files changed ({', '.join(diff)}) but version is still {old_v} — bump `version` in manifest.yaml")
            errors += 1
        elif changed:
            print(f"{pack.id}: {old_v} → {now_v}")
        else:
            print(f"{pack.id}: unchanged")
    for pid in sorted(set(published) - {d.name for d in (ROOT / "packs").iterdir() if d.is_dir()}):
        print(f"{pid}: removed (installed copies stay; the index stops listing it)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
