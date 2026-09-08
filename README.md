# Cortex template marketplace

Template packs for [Cortex](https://github.com/frontal-cortex/cortex): note
templates and databases that install into a vault as plain Markdown and YAML.
No code, no plugins, nothing that runs — the same materials a vault is already
made of, so every pack is readable in a text editor and keeps working in any
other Markdown tool.

**Use them** from the app's Marketplace page (`Ctrl+Shift+B`, or *Browse
templates…* in the command palette) or a terminal:

```
cortex packs list                # what's available — bundled official packs plus this index
cortex packs show tasks          # manifest, files, and exactly what an install would write
cortex packs install tasks       # into templates/, .cortex/schemas/, collections/tasks/
cortex packs update              # newer versions; files you edited are kept
cortex packs remove tasks        # deletes only the files it wrote that you have not changed
```

**Contribute one**: see [CONTRIBUTING.md](CONTRIBUTING.md) — export from your
own vault with `cortex packs new`, lint, open a pull request.

## How it is served

- `index.json` is **generated** on every merge to `main` and committed back —
  never edited by hand. It lists every pack with its manifest, trust tier, a
  sha256 per file and the commit it was generated from.
- The same workflow publishes `index.json` and every pack's files to GitHub
  Pages: <https://frontal-cortex.github.io/marketplace/> — the app's default
  index URL. The app verifies each downloaded file against the hash in the
  index and refuses a mismatch.
- The app bundles a snapshot of the `official` packs, so the marketplace works
  offline; the live index adds newer versions and the community tiers.
- A company can host its own registry: run `tools/gen_index.py --base
  https://host/packs/` over a checkout, serve the files, and point
  `marketplace_url` (or `marketplace_extra`) in the vault's settings at it.
- A tag (`v0.2.0`) makes a GitHub Release with a snapshot tarball; the app
  repository vendors it with `tools/sync-packs.sh <tag>`.

## Layout

```
marketplace/
├── packs/<id>/            # one folder per pack, any tier
│   ├── manifest.yaml
│   ├── README.md          # optional long description
│   ├── preview.png        # optional card image, ≤ 200 KB
│   ├── templates/*.md     # → <vault>/templates/ — except templates/<collection>.md,
│   │                      #   which is that collection's row template → collections/<collection>/_template-<collection>.md
│   ├── schemas/*.yaml     # → <vault>/.cortex/schemas/<collection>.yaml    (collection packs)
│   ├── index.md           # → <vault>/collections/<collection>/_index.md   (collection packs: the views)
│   ├── index/<c>.md       # → <vault>/collections/<c>/_index.md           (packs with more than one collection)
│   ├── seed/*.md          # → <vault>/collections/<collection>/            (collection packs: example rows)
│   ├── seed/<c>/*.md      # → <vault>/collections/<c>/                     (rows for an extra collection)
│   └── assets/*           # → <vault>/assets/<id>/
├── index.json             # GENERATED — what the app fetches
├── featured.yaml          # hand-curated order for the app's front page
├── tiers.yaml             # trust tier per pack, set by maintainers: official | verified | community
├── tools/                 # lint, index, preview, version check, site build (Python 3 + PyYAML)
└── .github/workflows/     # lint.yml (every PR), index.yml (merge → index + Pages), release.yml (tag → release)
```

## `manifest.yaml` (format 1)

```yaml
format: 1
id: tasks                        # [a-z0-9-], equals the folder name
name: "Tasks"
version: 1.0.0                   # semver; bump whenever any file changes (CI refuses a silent change)
kind: collection                 # note | collection | bundle
summary: "One line, ≤ 120 characters, no product names."
description: |
  A paragraph. Markdown allowed.
tags: [productivity, tasks, database]
author:
  name: "Your name"
  url: https://example.com
license: CC0-1.0                 # SPDX id; CC0-1.0 or CC-BY-4.0 for content
credits: "Where the design comes from — attribution lives here, not in the summary."
min_cortex: 0.1.0                # lowest app version the pack's features need
collection: tasks                # collection packs only: the folder under collections/
# collections: [task-log]        # extra collections the pack owns (a habits list and its daily log):
                                 # schemas/<c>.yaml, index/<c>.md, templates/<c>.md, seed/<c>/ address each
files:                           # every file the pack installs, nothing else
  - templates/tasks.md
  - schemas/tasks.yaml
  - index.md
  - seed/example-task.md
```

Bundles list `includes: [pack ids]` instead of `files`.

## Rules (`tools/lint.py`, the same rules as `cortex packs lint`)

- Only `.md`, `.yaml`, `.png`, `.jpg`, `.webp`, `.svg`; only in the folders
  above; no `..`, no absolute paths; ≤ 2 MB per pack, ≤ 200 KB per image.
- `files` lists every installed file and every listed file exists.
- Frontmatter parses. **Placeholders are quoted** (`created: "{{date}}"`).
  Templates may use `{{date}}`, `{{time}}`, `{{title}}`, `{{uuid}}` (expanded
  when a note is created from them — row templates too). Any file may use the
  **date words** `{{today}}`, `{{tomorrow}}`, `{{yesterday}}`, `{{monday}}`,
  `{{sunday}}` (this week's), `{{month}}` (`YYYY-MM`), `{{year}}`, `{{week}}`
  (`YYYY-Www`), each with an optional offset — `{{today+7}}`, `{{monday-1}}`,
  `{{month+1}}` (seeds and indexes: expanded once, at install; templates: when
  the note is created). Anything else in `{{…}}` is an error.
- Schema property types are ones the app knows (`text`, `number`, `date`,
  `checkbox`, `select`, `multi_select`, `status`, `person`, `url`,
  `relation`, `rollup`, `formula`). A property may carry `collection`,
  `relation`, `property`, `function`, `from`, `where`, `expr`, `format`,
  `min`, `max`, `unit`, `auto` (see the app's docs on views, filters and
  computed properties). A property is not named `type`, `title`, `tags`,
  `created`, `id`, `path`, `icon` or `cover` — those are a note's own keys.
  A `formula` has `expr:`; a `rollup` has `relation:` (plus `from:` for the
  reverse side); `format` is `percent`, `progress`, `currency`, `stars`,
  `integer` or `decimal`; `auto:` is a filter (`status == done`); a
  `relation` to a collection the pack does not install is a warning, not an
  error. The app's `cortex packs lint` is authoritative for formula syntax;
  `tools/lint.py` (what CI runs) only catches the obvious — empty, unbalanced
  parentheses, unterminated string — so run the app's lint too.
- Every `group:` / `date:` in an index names a schema property;
  a calendar view's `date:` is a date property; a tracker view names its
  `log: collections/<name>`, and when that log is in the pack its `date` is a
  date property and its `done` a relation or multi-select; seed rows and each
  row template use only their own collection's properties. A pack with several
  collections ships a schema and an index for each.
- No raw HTML beyond `<br>`, `<sub>`, `<sup>` and comments.
- `name` and `summary` carry no third-party product names — put them in `credits`.

## Trust tiers

| Tier | Who | How it gets there | Shown |
|---|---|---|---|
| `official` | Cortex team | Written or adopted by maintainers; bundled in the app | by default, first |
| `verified` | Community | Passed lint **and** a maintainer reviewed the content against the checklist | by default, with a badge |
| `community` | Community | Passed lint; a maintainer merged after a sanity glance | by default, with a badge; the `marketplace_tiers` setting hides it |

The tier lives in `tiers.yaml`, owned by maintainers — a pack cannot promote
itself. Packs missing from that file are `community`.

## The packs

| Pack | Kind | Installs |
|---|---|---|
| daily-note | note | `templates/daily.md` |
| weekly-review | note | `templates/weekly-review.md` |
| meeting-notes | note | `templates/meeting.md` |
| one-on-one | note | `templates/one-on-one.md` |
| para-index | note | `templates/para-index.md` |
| decision-log | note | `templates/decision.md` |
| tasks | collection | `collections/tasks/` (table, board by status, calendar on due) |
| project-tracker | collection | `collections/projects/` (table, board by status, calendar on deadline) |
| reading-list | collection | `collections/reading/` (table, board by status, gallery) |
| habit-tracker | collection | `collections/habits/` (one row per habit-week; table, calendar on week, board by habit) |
| budget-tracker | collection | `collections/budget/` (table, board by category, calendar on date) |
| recipe-box | collection | `collections/recipes/` (table, gallery, board by cuisine) |
| contacts | collection | `collections/contacts/` (table, board by relationship, calendar on follow-up) |
| goals | collection | `collections/goals/` (table, board by status, calendar on target date) |
| content-calendar | collection | `collections/content/` (table, board by status, calendar on publish date) |

The first ten are `featured.yaml`. Every pack here is `official` and CC0.

## Tools

```bash
pip install pyyaml
tools/lint.py                    # every pack (or: tools/lint.py packs/tasks)
tools/gen_index.py               # regenerate index.json (CI does this on merge)
tools/preview.py tasks           # the Markdown preview CI posts on a pull request
tools/check_versions.py index.json   # what CI runs: changed files need a new version
tools/build_site.py _site        # the Pages site, locally
```

`cortex packs lint` and `cortex packs index` in the app give the same answers;
the Python copies exist so CI needs nothing but this repository.
