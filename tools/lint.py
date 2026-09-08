#!/usr/bin/env python3
"""Check packs against the format rules — the same rules as `cortex packs lint`.
CI runs this on every pull request; errors block the merge, warnings advise.

    tools/lint.py                # every pack under packs/
    tools/lint.py packs/tasks    # one pack
    tools/lint.py --json …       # machine-readable findings
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packlib import Finding, PackError, lint, load_pack, pack_dirs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")] or [ROOT]
    dirs: list[Path] = []
    for p in paths:
        try:
            dirs += pack_dirs(p)
        except PackError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    errors = 0
    report = []
    for d in dirs:
        pid = d.name
        try:
            findings = lint(load_pack(d))
        except PackError as e:
            findings = [Finding("error", None, str(e))]
        for f in findings:
            if f.severity == "error":
                errors += 1
            if not as_json:
                where = f"{f.file}: " if f.file else ""
                print(f"{pid}: {f.severity}: {where}{f.message}")
        report.append({"id": pid, "findings": [f.as_dict() for f in findings]})
    if as_json:
        print(json.dumps(report, indent=2))
    elif errors == 0:
        print("ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
