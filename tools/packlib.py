"""Shared pieces for the marketplace tools: loading packs, the format rules
(`lint`), where each file lands in a vault (`destination`), hashes.

These mirror `cortex_core::marketplace` in the Cortex app so that CI, which
cannot build the app, gives the same answers as `cortex packs lint` and
`cortex packs index`. When a rule changes there, change it here in the same
change.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FORMAT = 1
ALLOWED_EXT = {"md", "yaml", "png", "jpg", "webp", "svg"}
ALLOWED_DIRS = {"templates", "schemas", "seed", "assets", "index"}
ROOT_FILES = {"manifest.yaml", "README.md", "index.md", "preview.png"}
# Shipped with the pack but not listed under `files` (they are not installed).
UNLISTED = {"manifest.yaml", "README.md", "preview.png"}
TEMPLATE_VARS = ("date", "time", "title", "uuid")
RAW_HTML_OK = ("<br", "<sub", "</sub", "<sup", "</sup", "<!--")
PRODUCT_WORDS = ("notion", "obsidian", "evernote", "roam", "logseq", "craft")
PROPERTY_TYPES = {"text", "number", "date", "checkbox", "select", "multi_select", "status", "person", "url", "relation"}
# Frontmatter keys every note may carry, whatever the schema says.
FREE_KEYS = {"title", "type", "tags", "created", "icon", "cover"}
KINDS = ("note", "collection", "bundle")
TIERS = ("official", "verified", "community")
TODAY = "{{today}}"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
ID_RE = re.compile(r"^[a-z0-9-]+$")


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    file: str | None
    message: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "file": self.file, "message": self.message}


@dataclass
class Pack:
    dir: Path
    manifest: dict
    files: dict[str, bytes] = field(default_factory=dict)  # path inside the pack → bytes

    @property
    def id(self) -> str:
        return str(self.manifest.get("id", ""))

    def text(self, path: str) -> str | None:
        b = self.files.get(path)
        return None if b is None else b.decode("utf-8", "replace")


class PackError(Exception):
    pass


def load_pack(dir: Path) -> Pack:
    mf = dir / "manifest.yaml"
    if not mf.is_file():
        raise PackError(f"{dir}: no manifest.yaml")
    try:
        manifest = yaml.safe_load(mf.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PackError(f"{dir}: manifest.yaml does not parse: {e}") from e
    if not isinstance(manifest, dict):
        raise PackError(f"{dir}: manifest.yaml is not a mapping")
    fmt = manifest.get("format", 1)
    if not isinstance(fmt, int) or fmt > FORMAT:
        raise PackError(f"{dir}: manifest format {fmt!r}; this tooling understands {FORMAT}")
    for key in ("id", "name", "version", "kind"):
        if key not in manifest:
            raise PackError(f"{dir}: manifest.yaml lacks `{key}`")
    if manifest["kind"] not in KINDS:
        raise PackError(f"{dir}: kind {manifest['kind']!r} is not one of {', '.join(KINDS)}")
    files: dict[str, bytes] = {}
    for p in sorted(x for x in dir.rglob("*") if x.is_file()):
        files[p.relative_to(dir).as_posix()] = p.read_bytes()
    return Pack(dir=dir, manifest=manifest, files=files)


def pack_dirs(path: Path) -> list[Path]:
    """A pack directory, or every pack under `<path>/packs/`."""
    if (path / "manifest.yaml").is_file():
        return [path]
    if (path / "packs").is_dir():
        return sorted(p for p in (path / "packs").iterdir() if p.is_dir())
    raise PackError(f"{path}: neither a pack (manifest.yaml) nor a marketplace checkout (packs/)")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collections(manifest: dict) -> list[str]:
    """Every collection a pack owns, primary first, without duplicates."""
    out: list[str] = []
    primary = str(manifest.get("collection") or "").strip()
    if primary:
        out.append(primary)
    for c in manifest.get("collections") or []:
        c = str(c)
        if c and c not in out:
            out.append(c)
    return out


def is_index(path: str) -> bool:
    """`index.md` (the primary collection's views) or `index/<c>.md` (another's)."""
    return path == "index.md" or (path.startswith("index/") and path.endswith(".md"))


def destination(manifest: dict, path: str) -> str | None:
    """Where a pack file lands in the vault; None for files that are not installed."""
    colls = collections(manifest)
    primary = colls[0] if colls else None
    pid = manifest.get("id", "")
    if path.startswith("templates/"):
        f = path[len("templates/"):]
        # A template named after one of the pack's collections is that
        # collection's row template — what the table's New row menu offers.
        if f.endswith(".md") and f[:-3] in colls:
            c = f[:-3]
            return f"collections/{c}/_template-{c}.md"
        return "templates/" + f
    if path.startswith("schemas/"):
        return ".cortex/schemas/" + path[len("schemas/"):]
    if path == "index.md":
        return f"collections/{primary}/_index.md" if primary else None
    if path.startswith("index/") and path.endswith(".md"):
        c = path[len("index/"):-3]
        return f"collections/{c}/_index.md" if c in colls else None
    if path.startswith("seed/"):
        rest = path[len("seed/"):]
        if "/" in rest:
            c, tail = rest.split("/", 1)
            if c in colls:
                return f"collections/{c}/{tail}"
        return f"collections/{primary}/{rest}" if primary else None
    if path.startswith("assets/"):
        return f"assets/{pid}/{path[len('assets/'):]}"
    return None


# ── Lint ────────────────────────────────────────────────────────────────────

def _strip_template_vars(text: str) -> str:
    for v in TEMPLATE_VARS:
        text = text.replace("{{" + v + "}}", "x")
    return text


def frontmatter(text: str) -> dict | None:
    """The YAML block between the opening `---` and the next `---`, as a mapping."""
    if not text.startswith("---"):
        return None
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        return None
    try:
        fm = yaml.safe_load(rest[:end])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _lint_markdown(path: str, text: str, out: list[Finding]) -> None:
    err = lambda m: out.append(Finding("error", path, m))
    if text.startswith("---"):
        for line in text.split("\n")[1:]:
            if line == "---":
                break
            if ":" in line:
                _, v = line.split(":", 1)
                if v.lstrip().startswith("{{"):
                    err(f'unquoted placeholder in frontmatter: `{line.strip()}` — write `"{v.strip()}"`')
        probe = _strip_template_vars(text.replace(TODAY, "2000-01-01"))
        if frontmatter(probe) is None:
            err("frontmatter does not parse as YAML")
    # Only the placeholders the app expands.
    i = 0
    while True:
        s = text.find("{{", i)
        if s < 0:
            break
        e = text.find("}}", s + 2)
        if e < 0:
            break
        name = text[s + 2:e].strip()
        ok = name in TEMPLATE_VARS or (name == "today" and (path.startswith("seed/") or is_index(path)))
        if not ok:
            err(f"unknown placeholder {{{{{name}}}}} (templates: date, time, title, uuid; seeds and index.md: today)")
        i = e + 2
    # Raw HTML beyond the allow-list.
    for m in re.finditer("<", text):
        tail = text[m.start():]
        looks_like_tag = len(tail) > 1 and (tail[1].isalpha() or tail[1] == "/" or tail.startswith("<!"))
        if looks_like_tag and not tail.lower().startswith(RAW_HTML_OK):
            err(f"raw HTML is not allowed: `{tail[:20].replace(chr(10), ' ')}`")
            break


def _schema_props(text: str) -> dict[str, str] | str:
    """name → type from a schema file, or an error message."""
    try:
        s = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return f"schema does not parse: {e}"
    if not isinstance(s, dict) or not isinstance(s.get("properties"), list):
        return "schema does not parse: expected `properties:` as a list"
    props: dict[str, str] = {}
    for p in s["properties"]:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str) or p.get("type") not in PROPERTY_TYPES:
            return f"schema does not parse: property {p!r} needs a name and a known type ({', '.join(sorted(PROPERTY_TYPES))})"
        props[p["name"]] = p["type"]
    return props


def lint(pack: Pack) -> list[Finding]:
    """Every rule from the format spec. Errors block; warnings are advice."""
    out: list[Finding] = []
    err = lambda file, m: out.append(Finding("error", file, m))
    warn = lambda file, m: out.append(Finding("warning", file, m))
    m = pack.manifest
    pid = str(m.get("id", ""))
    version = str(m.get("version", ""))
    name = str(m.get("name", "") or "")
    summary = str(m.get("summary", "") or "")
    license_ = str(m.get("license", "") or "")
    min_cortex = str(m.get("min_cortex", "") or "")
    kind = m.get("kind")
    listed_files = [str(f) for f in (m.get("files") or [])]
    includes = [str(x) for x in (m.get("includes") or [])]

    # Identity and versioning.
    if not ID_RE.match(pid):
        err(None, f"id '{pid}' must be lowercase letters, digits and dashes")
    if not SEMVER.match(version):
        err(None, f"version '{version}' is not semver (e.g. 1.0.0)")
    if not name.strip():
        err(None, "name is empty")
    if not summary.strip():
        err(None, "summary is empty")
    if len(summary) > 120:
        warn(None, "summary is longer than 120 characters")
    if not license_.strip():
        err(None, "license is required (an SPDX id such as CC0-1.0 or CC-BY-4.0)")
    if min_cortex and not SEMVER.match(min_cortex):
        err(None, f"min_cortex '{min_cortex}' is not semver")
    for w in PRODUCT_WORDS:
        if w in name.lower() or w in summary.lower():
            warn(None, f"'{w}' in the name or summary — attribution belongs in `credits`")
    if kind == "collection" and not (m.get("collection") or "").strip():
        err(None, "collection packs need `collection: <name>`")
    elif kind == "bundle" and not includes:
        err(None, "bundles need `includes: [pack ids]`")
    elif kind == "bundle" and listed_files:
        err(None, "bundles own no files")

    # Files: listed ⇔ present, allowed types and places, size.
    listed = set(listed_files)
    present = {p for p in pack.files if p not in UNLISTED}
    for p in sorted(listed - present):
        err(p, "listed in `files` but missing")
    for p in sorted(present - listed):
        err(p, "present but not listed in `files`")
    total = 0
    for path, data in pack.files.items():
        total += len(data)
        parts = path.split("/")
        if path.startswith("/") or any(c in ("..", ".", "") for c in parts):
            err(path, "path must be relative and free of `..`")
        ext = path.rsplit(".", 1)[-1].lower() if "." in parts[-1] else ""
        if ext not in ALLOWED_EXT:
            err(path, f"file type .{ext} is not allowed (md, yaml, png, jpg, webp, svg)")
        at_root = "/" not in path
        if not (at_root and path in ROOT_FILES) and parts[0] not in ALLOWED_DIRS:
            err(path, "files live in templates/, schemas/, seed/, index/, assets/ or are index.md / README.md / preview.png")
        if ext in ("png", "jpg", "webp", "svg") and len(data) > 200 * 1024:
            err(path, "images must be 200 KB or smaller")
        if ext == "md":
            _lint_markdown(path, data.decode("utf-8", "replace"), out)
    if total > 2 * 1024 * 1024:
        err(None, "pack is larger than 2 MB")

    # Collection packs: per collection, the schema, views, seeds and row template agree.
    if kind == "collection":
        colls = collections(m)
        primary = colls[0] if colls else ""
        all_props: dict[str, dict[str, str]] = {}
        for c in colls:
            schema_path = f"schemas/{c}.yaml"
            schema_text = pack.text(schema_path)
            props: dict[str, str] = {}
            if schema_text is None:
                err(schema_path, f"collection packs ship a schema named after each collection ({c})")
            else:
                r = _schema_props(schema_text)
                if isinstance(r, str):
                    err(schema_path, r)
                else:
                    props = r
            all_props[c] = props
        for c in colls:
            props = all_props[c]
            index_path = "index.md" if c == primary else f"index/{c}.md"
            index = pack.text(index_path)
            if index is None:
                err(index_path, f"collection packs ship {index_path} with the views for {c}")
            else:
                fm = frontmatter(index.replace(TODAY, "2000-01-01"))
                if fm is None:
                    err(index_path, "no frontmatter")
                else:
                    views = fm.get("views") if isinstance(fm.get("views"), list) else []
                    if not views:
                        err(index_path, "no views")
                    for v in views:
                        if not isinstance(v, dict):
                            continue
                        vkind = v.get("type") if isinstance(v.get("type"), str) else "table"
                        if vkind == "tracker":
                            # `date`/`done` belong to the log; checked when the log is part of this pack.
                            log = v.get("log") if isinstance(v.get("log"), str) else ""
                            if not log.startswith("collections/"):
                                err(index_path, "a tracker view needs `log: collections/<name>` — the collection with one row per day")
                            else:
                                l = log[len("collections/"):]
                                lp = all_props.get(l.rstrip("/"))
                                if lp is not None:
                                    date = v.get("date") if isinstance(v.get("date"), str) else "date"
                                    done = v.get("done") if isinstance(v.get("done"), str) else "done"
                                    if lp.get(date) != "date":
                                        err(index_path, f"tracker `date: {date}` must be a date property of {l}")
                                    if lp.get(done) not in ("relation", "multi_select"):
                                        err(index_path, f"tracker `done: {done}` must be a relation or multi_select property of {l}")
                            continue
                        for key in ("group", "date"):
                            p = v.get(key)
                            if isinstance(p, str) and p not in props:
                                err(index_path, f"view `{key}: {p}` names a property the schema lacks")
                        if vkind == "calendar":
                            d = v.get("date")
                            if not (isinstance(d, str) and props.get(d) == "date"):
                                err(index_path, "a calendar view needs `date:` naming a date property")
            if pack.text(f"templates/{c}.md") is None:
                warn(None, f"no row template templates/{c}.md — New row in {c} will have no shape")
        # Seeds and row templates use only their own collection's properties.
        for path in pack.files:
            owner: str | None = None
            if path.startswith("seed/"):
                rest = path[len("seed/"):]
                if "/" in rest and rest.split("/", 1)[0] in colls:
                    owner = rest.split("/", 1)[0]
                else:
                    owner = primary
            elif path.startswith("templates/") and path.endswith(".md"):
                t = path[len("templates/"):-3]
                if t in colls:
                    owner = t
            if owner is None or owner not in all_props:
                continue
            props = all_props[owner]
            text = _strip_template_vars(pack.text(path).replace(TODAY, "2000-01-01"))
            fm = frontmatter(text)
            if fm:
                for key in fm:
                    if key not in FREE_KEYS and key not in props:
                        err(path, f"property `{key}` is not in the {owner} schema")
    return out


# ── Index ───────────────────────────────────────────────────────────────────

def manifest_json(m: dict) -> dict:
    """The manifest as the app serialises it (field order and omissions match
    `cortex_core::marketplace::Manifest`)."""
    author = m.get("author") or {}
    out = {
        "format": int(m.get("format", 1)),
        "id": str(m["id"]),
        "name": str(m["name"]),
        "version": str(m["version"]),
        "kind": m["kind"],
        "summary": str(m.get("summary", "") or ""),
        "description": str(m.get("description", "") or ""),
        "tags": [str(t) for t in (m.get("tags") or [])],
        "author": {"name": str(author.get("name", "") or "")},
        "license": str(m.get("license", "") or ""),
    }
    if author.get("url"):
        out["author"]["url"] = str(author["url"])
    if m.get("credits"):
        out["credits"] = str(m["credits"])
    if m.get("min_cortex"):
        out["min_cortex"] = str(m["min_cortex"])
    if m.get("collection"):
        out["collection"] = str(m["collection"])
    if m.get("collections"):
        out["collections"] = [str(x) for x in m["collections"]]
    if m.get("includes"):
        out["includes"] = [str(x) for x in m["includes"]]
    out["files"] = [str(f) for f in (m.get("files") or [])]
    return out


def load_tiers(repo: Path) -> dict[str, str]:
    p = repo / "tiers.yaml"
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
