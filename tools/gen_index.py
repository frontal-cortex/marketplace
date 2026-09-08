#!/usr/bin/env python3
"""Regenerate index.json — the file the app fetches — from packs/*/manifest.yaml,
tiers.yaml and a sha256 of every file. Same output as `cortex packs index`.

    tools/gen_index.py [--base URL] [--out index.json]

`base` is where pack files are served from: `{base}{id}/{path}`. The default
is this repository's GitHub Pages site; a private registry passes its own.
Packs with lint errors abort the run — the index only ever lists valid packs.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packlib import FORMAT, PackError, lint, load_pack, load_tiers, manifest_json, sha256_hex  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://frontal-cortex.github.io/marketplace/packs/"


def build_index(repo: Path, base: str) -> dict:
    tiers = load_tiers(repo)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = ""
    entries = []
    for d in sorted(p for p in (repo / "packs").iterdir() if p.is_dir()):
        pack = load_pack(d)
        errors = [f for f in lint(pack) if f.severity == "error"]
        if errors:
            raise PackError(f"{pack.id}: " + "; ".join(f.message for f in errors))
        if pack.id != d.name:
            raise PackError(f"{d}: id does not match folder")
        entry = manifest_json(pack.manifest)
        entry["tier"] = tiers.get(pack.id, "community")
        entry["preview"] = f"{pack.id}/preview.png" if "preview.png" in pack.files else None
        entry["sha256"] = {p: sha256_hex(b) for p, b in sorted(pack.files.items())}
        entry["commit"] = commit
        entries.append(entry)
    return {
        "format": FORMAT,
        "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "base": base,
        "packs": entries,
    }


def main(argv: list[str]) -> int:
    base, out = DEFAULT_BASE, ROOT / "index.json"
    it = iter(argv)
    for a in it:
        if a == "--base":
            base = next(it)
        elif a == "--out":
            out = Path(next(it))
        else:
            print(f"unknown argument {a}", file=sys.stderr)
            return 2
    try:
        index = build_index(ROOT, base)
    except PackError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    # Keep the old timestamp when nothing else changed, so CI does not commit
    # an index that differs only by the clock.
    if out.is_file():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            if {**old, "generated": None} == {**index, "generated": None}:
                index["generated"] = old["generated"]
        except (json.JSONDecodeError, KeyError):
            pass
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out}: {len(index['packs'])} packs")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
