#!/usr/bin/env python3
"""Render a Markdown preview of packs — what CI posts on a pull request so a
reviewer sees the template, the table's columns and views, and every file an
install would write, without checking the branch out.

    tools/preview.py tasks daily-note > preview.md
    tools/preview.py            # every pack
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packlib import PackError, destination, frontmatter, lint, load_pack, load_tiers  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- pack-preview -->"


def body_after_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4:].lstrip("\n")
    return text


def excerpt(text: str, limit: int = 30) -> str:
    lines = text.rstrip().split("\n")
    shown = lines[:limit]
    more = f"\n… {len(lines) - limit} more lines" if len(lines) > limit else ""
    return "\n".join(shown) + more


def render(pid: str, tiers: dict[str, str]) -> str:
    d = ROOT / "packs" / pid
    if not d.is_dir():
        return f"### `{pid}`\n\nRemoved in this change. Installed copies stay; the index stops listing it.\n"
    try:
        pack = load_pack(d)
    except PackError as e:
        return f"### `{pid}`\n\n❌ {e}\n"
    m = pack.manifest
    out = [f"### {m.get('name', pid)} (`{pid}`) v{m.get('version', '?')} — {m.get('kind')} · {tiers.get(pid, 'community')}", ""]
    if m.get("summary"):
        out += [f"> {m['summary']}", ""]
    if m.get("description"):
        out += [str(m["description"]).strip(), ""]
    meta = []
    if (m.get("author") or {}).get("name"):
        meta.append(f"by {m['author']['name']}")
    if m.get("license"):
        meta.append(f"licence {m['license']}")
    if m.get("tags"):
        meta.append("tags " + ", ".join(f"`{t}`" for t in m["tags"]))
    if m.get("credits"):
        meta.append(f"credits: {m['credits']}")
    if meta:
        out += [" · ".join(meta), ""]

    findings = lint(pack)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if errors or warnings:
        out.append(f"**Lint:** {len(errors)} error(s), {len(warnings)} warning(s)")
        for f in findings:
            where = f"`{f.file}`: " if f.file else ""
            out.append(f"- {'❌' if f.severity == 'error' else '⚠️'} {where}{f.message}")
        out.append("")
    else:
        out += ["**Lint:** ok", ""]

    installs = [(p, destination(m, p)) for p in m.get("files") or []]
    if installs:
        out += ["**Installs**", "", "| file in the pack | lands at |", "|---|---|"]
        out += [f"| `{p}` | `{dest or '(not installed)'}` |" for p, dest in installs]
        out.append("")
    if m.get("kind") == "bundle":
        out += ["**Includes:** " + ", ".join(f"`{x}`" for x in m.get("includes") or []), ""]

    if m.get("kind") == "collection" and m.get("collection"):
        coll = m["collection"]
        schema = pack.text(f"schemas/{coll}.yaml")
        if schema:
            import yaml
            try:
                props = (yaml.safe_load(schema) or {}).get("properties") or []
            except yaml.YAMLError:
                props = []
            cols = []
            for p in props:
                if isinstance(p, dict):
                    opts = [o.get("name") if isinstance(o, dict) else o for o in (p.get("options") or [])]
                    cols.append(f"`{p.get('name')}` ({p.get('type')}{': ' + ' / '.join(map(str, opts)) if opts else ''})")
            if cols:
                out += ["**Columns:** " + ", ".join(cols), ""]
        index = pack.text("index.md")
        fm = frontmatter(index.replace("{{today}}", "2000-01-01")) if index else None
        views = (fm or {}).get("views") or []
        if views:
            names = []
            for v in views:
                if isinstance(v, dict):
                    extra = f" by {v['group']}" if v.get("group") else f" on {v['date']}" if v.get("date") else ""
                    names.append(f"{v.get('name')} ({v.get('type')}{extra})")
            out += ["**Views:** " + " · ".join(names), ""]
    for p in m.get("files") or []:
        if p.startswith("templates/") and p.endswith(".md"):
            t = pack.text(p)
            if t:
                # A row template is often frontmatter only — then the frontmatter is the shape worth showing.
                body = body_after_frontmatter(t)
                shown = body if body.strip() else t
                out += [f"<details><summary><code>{p}</code></summary>", "", "```markdown", excerpt(shown), "```", "", "</details>", ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    tiers = load_tiers(ROOT)
    ids = [a for a in argv if a] or sorted(p.name for p in (ROOT / "packs").iterdir() if p.is_dir())
    parts = [MARKER, "## Pack preview", "", "Rendered by `tools/preview.py` from the files in this pull request.", ""]
    parts += [render(pid, tiers) for pid in ids]
    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
