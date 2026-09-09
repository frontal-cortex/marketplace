# Contributing a template pack

Thanks for sharing one. A pack is a folder of Markdown and YAML — no code —
so contributing is mostly about making a template that works in a real vault
and describing it honestly.

## The short version

1. **Make it** in your own vault until it works: a template under
   `templates/`, or a database under `collections/<name>/` with its schema.
2. **Export** it:
   ```
   cortex packs new my-pack --from templates/my-note.md       # a note template
   cortex packs new my-pack --from collections/reading         # a database
   ```
   That writes `my-pack/` with a `manifest.yaml`. Edit `summary`,
   `description`, `tags`, `author`, `license`; strip personal data from seed
   rows (they are examples, and everyone will see them); add a `preview.png`
   if you like (a screenshot of the table or note, ≤ 200 KB), and more
   screenshots under `preview/` — one per view, named so they sort in the
   order you want them shown (`01-reading-shelf.png`, `02-…`).
3. **Lint** until clean: `cortex packs lint my-pack` (or `tools/lint.py my-pack`
   from a checkout of this repository — same rules).
4. **Submit**: fork this repository, copy your folder to `packs/my-pack/`,
   open a pull request. CI lints it and posts a rendered preview on the PR.
5. **Review**: a maintainer merges it → `community` tier, and the index
   regenerates on merge; the app sees it on its next Refresh. If they also
   run the checklist below and it passes, it becomes `verified`.
6. **Update** later: change the files, bump `version`, PR again. CI refuses a
   changed pack with an unchanged version. Users see *Update* in the app;
   nothing changes in their vault until they click it, and files they edited
   are kept.

## What we ask of a pack

- **Licence**: `CC0-1.0` or `CC-BY-4.0` in the manifest. You keep the
  copyright; the licence is what lets people install, edit and share it.
- **Credits, not trademarks**: if the design comes from somewhere, say so in
  `credits`. Do not put third-party product names in `name` or `summary`
  (lint warns), and do not use another product's name as your pack's name.
- **No personal data**: seed rows are examples. No real names, emails,
  addresses, account numbers — yours or anyone else's.
- **Plain files only**: nothing executable, no raw HTML beyond `<br>`,
  `<sub>`, `<sup>` and comments, no remote images.
- **Written for the reader, not for an agent**: people point AI agents at
  their vaults, and your seeds and pages become part of what those agents
  read. Text that addresses an agent ("ignore previous instructions", "you
  are an assistant…") or tells anyone to run commands that change a machine
  (`curl … | sh`, `rm -rf`, `sudo`) makes lint warn and a reviewer refuse.
  Mentioning `cortex set` in a how-to is fine.
- **Your own name**: a pack's `id`, `name` and hero must not imitate another
  pack's. The bundled packs' ids are reserved; a look-alike ("tasks-pro" with
  the Tasks hero) is declined, and an existing id can only be updated by its
  listed author or a maintainer.
- **Quoted placeholders**: `created: "{{date}}"`. Templates may use
  `{{date}}`, `{{time}}`, `{{title}}`, `{{uuid}}`; any file may use the date
  words `{{today}}`, `{{monday}}`, `{{month}}`, `{{week}}`, … with offsets
  like `{{today+7}}` (see the README's rules).
- **Formulas parse**: CI's `tools/lint.py` only checks the obvious; the app's
  `cortex packs lint` is authoritative for `expr:` — run it before you submit.
- **One thing, well**: a pack does one job and its summary says what that
  is in one line. A bundle (`kind: bundle`, `includes: [...]`) groups packs
  that belong together.

## The review checklist (for `verified`)

A maintainer grants `verified` after checking, in a real vault, from a clean
install:

- Does what the summary says.
- Templates open cleanly in the app; placeholders resolve; no empty headings
  that will never be filled.
- Database packs: the views make sense, seed rows are obviously examples, the
  row template matches the schema.
- No personal data, no third-party trademarks in names, licence set, credits
  given where a design is borrowed.
- Every seed body and page body read in full, with an agent in mind: nothing
  addresses an AI, nothing asks the reader to run commands that change a
  machine, no links to schemes other than `http`, `https`, `mailto`, no remote
  images. Lint's warnings for this are resolved, not waved through.
- The name and hero are the pack's own, not a look-alike of another pack.
- Uninstall leaves nothing behind.

`verified` is recorded in `tiers.yaml` by a maintainer. It is revoked the same
way if a later version fails the checklist, or on a takedown (below).

## Governance

- **Maintainers** are the people in `CODEOWNERS`. Every pull request needs one
  of them; `tiers.yaml`, `featured.yaml`, the tooling and the workflows need
  one of them too — a contributor cannot promote their own pack.
- **Response time**: expect a first look within a week. If a PR sits longer,
  comment on it; that is not rude.
- **Takedowns**: a pack that turns out to contain personal data, infringing
  content or a trademark problem is removed or demoted by a maintainer. The
  index stops listing it on the next merge; installed copies stay — they are
  the user's files.
- **Official packs** are written or adopted by the Cortex team and bundled
  with the app. A community pack can be adopted: we will ask first, keep your
  credit, and it stays under your licence.
- **Conduct**: be kind in reviews and in issues. Critique the pack, not the
  person. Harassment of any kind gets a warning, then a block.

## A first submission, walked through

Say you keep a reading list as a database in your vault, at
`collections/reading/`, with a schema you built up over a month. To share it:

```
$ cortex packs new reading-tracker --from collections/reading --out ~/src
wrote /home/you/src/reading-tracker
Edit manifest.yaml (summary, description, tags), add seeds if you like, then: cortex packs lint /home/you/src/reading-tracker
```

The folder now holds `manifest.yaml`, `schemas/reading.yaml`, `index.md`
(your views), `templates/reading.md` (your row template, if you had one) and
one seed row per note in the collection. Open `manifest.yaml`:

```yaml
format: 1
id: reading-tracker
name: "Reading Tracker"
version: 1.0.0
kind: collection
summary: "Books and articles with status, rating and the date you finished — board by status, calendar by finish date."
description: |
  What I actually use: a row per book with a five-star rating, a status
  board (Want / Reading / Done) and a calendar of finish dates so the year's
  reading is visible at a glance.
tags: [reading, books, database]
author:
  name: "Your Name"
  url: https://github.com/you
license: CC0-1.0
collection: reading
files:
  - schemas/reading.yaml
  - index.md
  - templates/reading.md
  - seed/example-book.md
```

Delete the seed rows that are your real books and keep one obviously-example
row (`title: "Example book — delete me"`). Then:

```
$ cortex packs lint ~/src/reading-tracker
reading-tracker: warning: summary is longer than 120 characters
```

Shorten the summary, lint again until it prints `ok`, and open the pull
request with the folder at `packs/reading-tracker/`. Within a minute CI
comments with the rendered template, the table's columns and views, and the
list of files an install writes. A maintainer merges it; the next Refresh in
anyone's app lists *Reading Tracker* under Community.

A month later you add a `format` property (Paperback / Ebook / Audio). Edit
the schema and the row template, set `version: 1.1.0`, PR again. Users who
installed 1.0.0 see *Update*; clicking it adds the property to their schema
and leaves every row and every edited file alone.
