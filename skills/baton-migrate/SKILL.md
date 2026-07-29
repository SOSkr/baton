---
name: baton-migrate
description: >
  Move an old GitHub Projects board onto the real board (Plane) — items, stages,
  labels, and the comment trail. Use when the user says "migrate the board", "migrar
  de github projects", "traer los issues a Plane", "import the old project".
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board), gh
credential: agent
---

# baton migrate

One-way, one-time: GitHub Projects → the board baton now points at. GitHub Projects is
no longer a baton backend; what is left of it is a **read-only** source (`baton export`).
Nothing in this skill writes to GitHub.

Run it once per source board. It is not a sync — there is no going back and no second
pass that reconciles. Get it right, then close the old board.

## 1. Export the source — read-only, safe to repeat

Which old board belongs to which project is **project data**, so it lives in that
project's config — the skills are installed globally and must never carry it:

```yaml
# <project>/.baton/config.yaml
migrate_from:
  repo: OWNER/REPO
  project: 5          # ProjectV2 number
```

```bash
cd <the project>          # config is found by walking up from cwd
baton export --state all > /tmp/source.json
```

Flags override for a one-off: `baton export --from-github OWNER/REPO --project 5`.
Without a project number you get the issues but no stages. `--state all` on purpose:
closed items carry decisions, and the point of moving is not losing them.

Each exported item carries `comments`. **That is the part that matters.** Titles and
bodies survive anywhere; the thread is where the decisions, the rejected paths and the
blockers live, and it is what `baton-catch-up` reads afterwards.

## 2. Map before you write

Read `baton stages` on the destination and reconcile it against `stages` in the export.
Show the user the mapping and get it confirmed **before creating anything** — a wrong
stage map means re-doing the whole migration by hand.

| Source (GitHub) | Destination (Plane) | Note |
|---|---|---|
| title, body | name, description | direct |
| labels | labels | direct — created on demand |
| `priority:*` label | **native priority field** | `baton new --priority high` — do not carry the label across |
| Status stage | state, by name | needs the confirmed map |
| comments | comments | one per comment, oldest first, attribution preserved |
| open/closed | state group | close after creating, so the trail lands first |
| milestone | epic (module) | only if the old board used them — see `baton-roadmap` |

**Check what is native on the destination before assuming a label.** On this board
`priority` is a real field while `type` and `area` are not, so `priority:high` should
become the native value and the rest stay labels. `baton doctor` reports what the
backend actually supports; do not guess from another project.

## 3. Create, in order

Per item: create → comments (oldest first) → stage → close if it was closed.

```bash
baton new --title "..." --body "$(...)" --label type:idea
baton comment <new-id> --body "..."
baton advance <new-id> --to "<mapped stage>"
baton close <new-id> --reason "migrated closed from OWNER/REPO#<old>"
```

Two rules that save the migration:

- **Ids change.** The new board assigns its own. Keep a source→destination map as you
  go and print it at the end — cross-references between items, and any PR that named an
  old number, are unreadable without it.
- **Say where it came from.** Put `migrated from OWNER/REPO#<n>` in the body or the
  first comment. Six months later that line is the only way to answer "where is the
  original discussion".

## 4. Verify before declaring it done

```bash
baton list --state all | wc -l      # count matches the export?
baton show <id> --comments          # spot-check: did the trail actually land?
```

Check the count, then open two or three items and confirm the comments are there and in
order. A migration that moved titles and dropped threads looks successful and is not.

Report: how many moved, the id map, and anything that did not transfer cleanly. Never
report success on the count alone.

## Notes
- **Resumable by hand, not automatically.** If it stops halfway, the already-created
  items are real. Diff the id map against the export before re-running, or you will get
  duplicates — baton has no dedupe.
- Attribution: comments are recreated by whoever runs this, so the original author is
  lost unless you write it into the comment body. Prefix it: `@alice (2026-03-11): ...`.
- Big boards: `baton export` makes one API call per item for comments. Slow, not
  fragile. Let it run.
