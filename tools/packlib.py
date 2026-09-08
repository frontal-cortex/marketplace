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
from datetime import date, timedelta
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
PROPERTY_TYPES = {"text", "number", "date", "checkbox", "select", "multi_select", "status", "person", "url", "relation", "rollup", "formula"}
# Keys a property may carry besides name/type/options (`cortex_core::schema::PropertyDef`).
PROPERTY_KEYS = {"collection", "relation", "property", "function", "from", "where", "expr", "format", "min", "max", "unit", "auto"}
# A property may not shadow a note's own keys.
RESERVED_PROPERTY_NAMES = ("type", "title", "tags", "created", "id", "path", "icon", "cover")
FORMATS = ("percent", "progress", "currency", "stars", "integer", "decimal")
# Frontmatter keys every note may carry, whatever the schema says.
FREE_KEYS = {"title", "type", "tags", "created", "icon", "cover"}
KINDS = ("note", "collection", "bundle")
TIERS = ("official", "verified", "community")
# Date placeholders are resolved against this fixed day (a Monday) so lint can
# parse frontmatter — the same day `cortex_core::marketplace::lint_dates` uses.
LINT_BASE = date(2000, 1, 3)
OFFSET_RE = re.compile(r"^[+-]\d+$")
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


# ── Date placeholders (mirrors `cortex_core::placeholders`) ─────────────────
#
# `{{today}}`, `{{today+7}}`, `{{monday-1}}`, `{{month}}`, `{{week}}` … — one
# vocabulary for templates, seeds and (after `@`) filters. Everything resolves
# against one base day.

def _split_offset(name: str) -> tuple[str, int] | None:
    i = min((k for k in (name.find("+"), name.find("-")) if k >= 0), default=-1)
    if i < 0:
        return name, 0
    word, off = name[:i], name[i:]
    if not OFFSET_RE.match(off):
        return None
    return word, int(off)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _shift_month(d: date, by: int) -> date:
    total = d.year * 12 + (d.month - 1) + by
    return date(total // 12, total % 12 + 1, 1)


def resolve_date(name: str, base: date) -> str | None:
    """One placeholder name (without braces or `@`) against `base`; None when
    it is not a date word."""
    parts = _split_offset(name.strip())
    if parts is None:
        return None
    word, n = parts
    if word in ("today", "date", "now"):
        d = base + timedelta(days=n)
    elif word == "tomorrow":
        d = base + timedelta(days=1 + n)
    elif word == "yesterday":
        d = base - timedelta(days=1 - n)
    elif word == "monday":
        d = _monday(base) + timedelta(days=7 * n)
    elif word == "sunday":
        d = _monday(base) + timedelta(days=6 + 7 * n)
    elif word == "month":
        return _shift_month(base, n).strftime("%Y-%m")
    elif word == "year":
        return str(base.year + n)
    elif word == "week":
        y, w, _ = (_monday(base) + timedelta(days=7 * n)).isocalendar()
        return f"{y}-W{w:02d}"
    else:
        return None
    return d.strftime("%Y-%m-%d")


def is_date_word(name: str) -> bool:
    return resolve_date(name, LINT_BASE) is not None


def expand_dates(text: str, base: date) -> str:
    """Expand every `{{word±n}}` date placeholder in `text` against `base`.
    Other placeholders (`{{title}}`, `{{uuid}}`, unknown words) are left alone."""
    out: list[str] = []
    rest = text
    while True:
        start = rest.find("{{")
        if start < 0:
            break
        out.append(rest[:start])
        after = rest[start + 2:]
        end = after.find("}}")
        if end < 0:
            out.append(rest[start:])
            return "".join(out)
        name = after[:end]
        v = resolve_date(name, base)
        out.append(v if v is not None else "{{" + name + "}}")
        rest = after[end + 2:]
    out.append(rest)
    return "".join(out)


def lint_dates(text: str) -> str:
    """Placeholders resolved against a fixed day so lint can parse frontmatter."""
    return expand_dates(text, LINT_BASE)


# ── Filters (mirrors `cortex_core::data::parse_filter`) ─────────────────────
#
# `field OP value` joined by `and` / `or`; ops == = != > >= < <= contains;
# strings in single or double quotes. Only the grammar is mirrored — enough to
# say whether an `auto:` condition parses; the app evaluates it.

def _filter_tokens(s: str) -> list[str]:
    out: list[str] = []
    cur = ""
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        i += 1
        if c in ("'", '"'):
            lit = ""
            while i < n:
                ch = s[i]
                i += 1
                if ch == c:
                    break
                lit += ch
            out.append("\x01" + lit)  # \x01 marks a string literal, as in Rust
        elif c.isspace():
            if cur:
                out.append(cur)
                cur = ""
        elif c in "=!<>":
            if cur:
                out.append(cur)
                cur = ""
            op = c
            if i < n and s[i] == "=":
                op += "="
                i += 1
            out.append(op)
        else:
            cur += c
    if cur:
        out.append(cur)
    return out


def _rust_debug_str(s: str) -> str:
    """`{:?}` of a Rust String, close enough for the tokens a filter yields."""
    body = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\x01", "\\u{1}")
    return f'"{body}"'


def filter_error(text: str) -> str | None:
    """None when `text` parses as a filter, else the message the app gives.
    This is the tail after "auto condition does not parse: "; it mirrors the
    Rust strings for every case the grammar has, though a token's `{:?}`
    rendering may differ for exotic characters."""
    toks = _filter_tokens(text)
    pos = 0

    def cmp() -> str | None:
        nonlocal pos
        if pos >= len(toks):
            return "Expected field"
        if pos + 1 >= len(toks):
            return "Expected operator"
        if pos + 2 >= len(toks):
            return "Expected value"
        op = toks[pos + 1].lower()
        pos += 3
        if op not in ("==", "=", "!=", ">", ">=", "<", "<=", "contains"):
            return f"Unknown operator: {op}"
        return None

    e = cmp()
    if e:
        return e
    while pos < len(toks) and toks[pos].lower() in ("and", "or"):
        pos += 1
        e = cmp()
        if e:
            return e
    if pos != len(toks):
        return f"Unexpected token in filter: Some({_rust_debug_str(toks[pos])})"
    return None


# ── Formulas (a light mirror of `cortex_core::formula::Formula::parse`) ─────
#
# Python does not run the formula parser; `cortex packs lint` in CI is
# authoritative for formula syntax. This catches what a tokenizer sees —
# empty, an unterminated string, a stray character, a bad number — and
# unbalanced parentheses, with the app's messages where it has one. A formula
# that passes here can still be rejected by the app (`a +`, `if(a)`, …).

def formula_error(src: str) -> str | None:
    depth = 0
    i, n = 0, len(src)
    toks = 0
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            start = i
            while i < n and (src[i].isdigit() or src[i] == "."):
                i += 1
            num = src[start:i]
            try:
                float(num)
            except ValueError:
                return f"bad number {num}"
            toks += 1
            continue
        if c in ("'", '"'):
            i += 1
            while i < n and src[i] != c:
                i += 1
            if i >= n:
                return "unterminated string"
            i += 1
            toks += 1
            continue
        if c.isalpha() or c == "_":
            while i < n and (src[i].isalnum() or src[i] == "_"):
                i += 1
            toks += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return "unexpected RParen after the expression"
            depth -= 1
        elif c in ",+-*/%":
            pass
        elif c in "=!<>":
            if i + 1 < n and src[i + 1] == "=":
                i += 1
        else:
            return f"unexpected character {c!r}"
        toks += 1
        i += 1
    if toks == 0:
        return "empty formula"
    if depth > 0:
        return "expected )"
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
        probe = _strip_template_vars(lint_dates(text))
        if frontmatter(probe) is None:
            err("frontmatter does not parse as YAML")
    # Only the placeholders the app expands: template vars and date words with offsets.
    i = 0
    while True:
        s = text.find("{{", i)
        if s < 0:
            break
        e = text.find("}}", s + 2)
        if e < 0:
            break
        name = text[s + 2:e].strip()
        ok = name in TEMPLATE_VARS or is_date_word(name)
        if not ok:
            err(f"unknown placeholder {{{{{name}}}}} (date, time, title, uuid; date words today, monday, sunday, month, year, week, with offsets like today+7)")
        i = e + 2
    # Raw HTML beyond the allow-list.
    for m in re.finditer("<", text):
        tail = text[m.start():]
        looks_like_tag = len(tail) > 1 and (tail[1].isalpha() or tail[1] == "/" or tail.startswith("<!"))
        if looks_like_tag and not tail.lower().startswith(RAW_HTML_OK):
            err(f"raw HTML is not allowed: `{tail[:20].replace(chr(10), ' ')}`")
            break


def _schema_props(text: str) -> list[dict] | str:
    """The property definitions of a schema file, or an error message.

    The app deserialises into `schema::TypeSchema`; the message for a schema
    it rejects is serde's and differs from ours — the verdict is the same."""
    try:
        s = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return f"schema does not parse: {e}"
    if not isinstance(s, dict) or not isinstance(s.get("properties"), list):
        return "schema does not parse: expected `properties:` as a list"
    for p in s["properties"]:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str) or p.get("type") not in PROPERTY_TYPES:
            return f"schema does not parse: property {p!r} needs a name and a known type ({', '.join(sorted(PROPERTY_TYPES))})"
        for k in ("min", "max"):
            if k in p and (isinstance(p[k], bool) or not isinstance(p[k], (int, float))):
                return f"schema does not parse: property `{p['name']}`: `{k}` must be a number"
    return s["properties"]


def _lint_property(schema_path: str, p: dict, colls: list[str], out: list[Finding]) -> None:
    """The per-property rules of `cortex_core::marketplace::lint`, same messages."""
    err = lambda m: out.append(Finding("error", schema_path, m))
    warn = lambda m: out.append(Finding("warning", schema_path, m))
    name, ty = p["name"], p["type"]
    if name in RESERVED_PROPERTY_NAMES:
        err(f"a property may not be named `{name}` — it is a note's own key; use kind, name, …")
    if ty == "formula":
        expr = p.get("expr")
        if expr is None:
            err(f"formula `{name}` needs `expr:`")
        else:
            e = formula_error(str(expr))
            if e:
                err(f"formula `{name}` does not parse: {e}")
    if ty == "rollup" and p.get("relation") is None:
        err(f"rollup `{name}` needs `relation:` (and `from:` for the reverse side)")
    f = p.get("format")
    if f is not None and str(f) not in FORMATS:
        err(f"`{name}`: unknown format `{f}` ({', '.join(FORMATS)})")
    a = p.get("auto")
    if a is not None:
        e = filter_error(str(a))
        if e:
            err(f"`{name}`: auto condition does not parse: {e}")
    if ty == "relation" and p.get("collection") is not None:
        target = str(p["collection"])
        if target not in colls:
            warn(f"`{name}` relates to `{target}`, which this pack does not install — fine when that pack is present")


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
                    for p in r:
                        _lint_property(schema_path, p, colls, out)
                    props = {p["name"]: p["type"] for p in r}
            all_props[c] = props
        for c in colls:
            props = all_props[c]
            index_path = "index.md" if c == primary else f"index/{c}.md"
            index = pack.text(index_path)
            if index is None:
                err(index_path, f"collection packs ship {index_path} with the views for {c}")
            else:
                fm = frontmatter(lint_dates(index))
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
            text = _strip_template_vars(lint_dates(pack.text(path)))
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
