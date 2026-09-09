#!/usr/bin/env python3
"""Assemble the static site GitHub Pages serves: index.json, every pack's
files at `packs/<id>/<path>` (what `base` in the index points to), the
curation files, and a small human-readable front page.

    tools/build_site.py _site
"""
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    out = Path(argv[0] if argv else "_site")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    index = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    shutil.copy(ROOT / "index.json", out / "index.json")
    for f in ("featured.yaml", "tiers.yaml"):
        if (ROOT / f).is_file():
            shutil.copy(ROOT / f, out / f)
    for e in index["packs"]:
        # The hashed files plus the gallery (`previews` is `<id>/preview/<file>`,
        # not in the hash map because install never fetches it).
        paths = list(e["sha256"]) + [p.split("/", 1)[1] for p in e.get("previews", [])]
        for p in paths:
            src = ROOT / "packs" / e["id"] / p
            dst = out / "packs" / e["id"] / p
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
    (out / ".nojekyll").write_text("")
    rows = "\n".join(
        f"<li><a href=\"https://github.com/frontal-cortex/marketplace/tree/main/packs/{html.escape(e['id'])}\">{html.escape(e['name'])}</a>"
        f" <small>v{html.escape(e['version'])} · {html.escape(e['kind'])} · {html.escape(e['tier'])}</small><br><span>{html.escape(e['summary'])}</span></li>"
        for e in index["packs"]
    )
    (out / "index.html").write_text(f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cortex template marketplace</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 42rem; margin: 3rem auto; padding: 0 1rem; color: #191918; background: #fff; }}
  @media (prefers-color-scheme: dark) {{ body {{ color: #e8e6e0; background: #191918; }} a {{ color: #8cbcf0; }} }}
  li {{ margin: 0 0 .8rem; }} small {{ opacity: .6; }} span {{ opacity: .8; }} code {{ font-size: .9em; }}
</style>
<h1>Cortex template marketplace</h1>
<p>{len(index['packs'])} packs · index generated {html.escape(index['generated'])}.
The app reads <a href="index.json"><code>index.json</code></a>; a pack's files are served under <code>packs/&lt;id&gt;/</code>.
Install one with <code>cortex packs install &lt;id&gt;</code> or from the app's Marketplace page.</p>
<ul>
{rows}
</ul>
<p><a href="https://github.com/frontal-cortex/marketplace">Source and contributing</a></p>
""", encoding="utf-8")
    print(f"{out}: {len(index['packs'])} packs")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
