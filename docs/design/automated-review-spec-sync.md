# Automated PR Review & Spec Sync

## Overview

Two automated actions that extend baton's lifecycle:

1. **Automated PR Review** — on PR open/update, an AI agent reviews code against item requirements, acceptance criteria, and code-comment consistency.
2. **Spec Sync** — on merge to develop, an AI agent detects spec↔code discrepancies and opens a PR with spec updates (spec-anchored development).

Both use `openclaw agent exec` (headless, one-shot) running in GitHub Actions. No external server required.

---

## Architecture principles

- **Baton integrates, does not execute.** Baton provides installable CI workflows and skills. The project installs them via `baton bootstrap`.
- **Skill layer, not CLI layer.** Review logic lives in skills (`baton-verify` already exists; `baton-spec` is new). CLI unchanged.
- **Configurable per project.** LLM provider, model per skill, extra rules — all in `.baton/config.yaml`.
- **Multi-language.** Stack detection is hybrid: CLI scaffolds files, agent decides which tools to configure. Works for Python, Node, PHP, Laravel, FastAPI, Java, any stack.

---

## Action 1: Automated PR Review

### Trigger
- `pull_request` events: `opened`, `ready_for_review`, `synchronize`

### Flow

```
PR created/updated
  → GitHub Action checks out repo
  → Install openclaw (npm cache)
  → openclaw agent exec --isolated --auth-env-only --json
  → Parse JSON output
  → Post review comments on PR (approve / request changes)
```

### Universal rules (always checked)

1. **Task requirements** — diff implements what the board item describes.
2. **Acceptance criteria** — each criterion has evidence in code or tests.
3. **Code-comment consistency** — comments match what the code actually does.

### Per-project rules

```yaml
# .baton/config.yaml
review:
  block_on: error      # error | warning | never
  extra_rules: []      # project-specific rules
```

### LLM configuration

```yaml
llm:
  default:
    provider: openai
    model: gpt-4o-mini
  skills:
    verify:
      model: gpt-4o          # baton-verify uses stronger model
    spec:
      model: claude-sonnet-4-20250514
```

Each skill can override the default model. Unset skills inherit `default`.

### CI installation

`baton bootstrap` detects project language and installs the appropriate workflow under `.github/workflows/baton-pr-review.yml`. The agent handles unrecognized stacks dynamically.

### skip conditions
- None. Every PR gets reviewed.

---

## Action 2: Spec Sync (post-merge)

### Spec-anchored development

Following SDD: specs live in the repo (`specs/<item-id>-<slug>.md`), versioned alongside code. They evolve with the feature — created at start, verified after merge.

### Spec creation

`baton start` automatically creates the spec file from a template. The developer refines it during implementation. The spec travels in the feature branch and is merged with the code.

### Spec verification (post-merge)

#### Trigger
Push to `develop` (merge event)

#### skip logic (zero-token, CI-level)
1. PR label is `documentation` → skip
2. PR label is `spec-sync` → skip (prevent loop)
3. Branch prefix is `docs/spec-sync-` → skip
4. Changes are trivial (< 3 files, only docs/config/bumps) → skip
5. Otherwise → agent evaluates

#### Flow

```
Merge to develop
  → CI checks skip conditions (no tokens used)
  → If not skipped: openclaw agent exec
    → Agent compares diff vs existing specs
    → If spec exists and diff mismatches → generate spec update
    → If no spec exists but change merits one → generate new spec
    → If no spec needed → silent skip
  → If spec changes generated → create branch docs/spec-sync-<id>
  → Open PR with changes (human approves)
```

### Spec templates

Templates live in baton repo under `templates/specs/`. Installed by `baton bootstrap`.

Default template:
```markdown
# <item-title>

## Requirements
- 

## Acceptance Criteria
- 

## Notes
```

Config maps item types to templates:
```yaml
# .baton/config.yaml
specs:
  templates:
    feature: feature.md
    bug: bug.md
    default: spec.md
  path: specs/      # where specs live in the repo
```

---

## CI workflow example

```yaml
# .github/workflows/baton-pr-review.yml
name: Baton PR Review
on:
  pull_request:
    types: [opened, ready_for_review, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm install -g openclaw@latest
      - run: |
          openclaw agent exec \
            --isolated \
            --auth-env-only \
            --json \
            --timeout 600 \
            "Review PR #${{ github.event.pull_request.number }} in ${{ github.repository }}. \
             Focus on: task requirements matching, acceptance criteria coverage, \
             and code-comment consistency. Post findings as GitHub review comments."
        env:
          ANTHROPIC_API_KEY: ${{ secrets.LLM_API_KEY }}
```

---

## Implementation priority

1. **Action 1 first** — `baton-verify` already exists. Only needs CI workflow + config.
2. **Action 2 second** — `baton-spec` skill (new) + templates + spec creation in `baton start`.

---

## Decisions log

| # | Decision | Outcome |
|---|----------|---------|
| 1 | Baton role | Integrates/recommends, does not execute tools directly |
| 2 | Review agent runtime | `openclaw agent exec` headless in CI, npm cache |
| 3 | PR review rules | 3 universal rules, extensible via `.baton/config.yaml` |
| 4 | LLM config | Per skill override in `.baton/config.yaml` |
| 5 | Stack detection | Hybrid: CLI scaffolds, agent decides tools |
| 6 | Spec format | Configurable template, default minimal |
| 7 | Spec creation | `baton start` auto-creates spec file |
| 8 | Spec sync trigger | Post-merge to develop, with skip logic |
| 9 | Spec sync output | PR with spec changes, human-approved |
| 10 | Spec templates storage | In baton repo, installed by `baton bootstrap` |
| 11 | Loop prevention | Label `spec-sync`, branch `docs/spec-sync-*`, label `documentation` |
| 12 | Implementation order | PR review first, spec sync second |

---

## Open questions

- Does OpenClaw publish a Docker image? (would simplify CI if yes)
- `auth-env-only` — which env var names does OpenClaw expect per provider? Document these per provider.
- GitHub token for posting review comments: personal access token or `${{ secrets.GITHUB_TOKEN }}`?
