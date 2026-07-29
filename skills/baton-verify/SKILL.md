---
name: baton-verify
description: >
  Validate a PR against the work-item it claims to implement: acceptance criteria met,
  Verification run, nothing touched that was declared out of scope. Use when the user
  says "validate PR", "does this PR do the task", "revisar el PR de X", "verificar
  <id>", or before advancing an item to Done.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton), gh
credential: agent
---

# baton verify

The gate between `baton-start` and `baton-ship`. An agent implemented something; this
answers the two questions the reviewer would otherwise re-read the whole diff to
answer: **did it do the task**, and **did it only do the task**.

This is a **review, never an approval.** Post findings; a human (or the admin
credential) approves and merges. On GitHub the PR author cannot approve their own PR —
that separation is the point, do not route around it.

## Workflow

1. **Read the item** — the contract you are checking against:
   ```bash
   baton show <id> --comments
   ```
   Take the acceptance criteria, the `Verification` section, and `Out of scope`
   verbatim. If the item has none of those, say so in the verdict and score the
   review INCONCLUSIVE — do not invent criteria and then grade against them.
2. **Read the diff**:
   ```bash
   gh pr view <n> --json title,body,files
   gh pr diff <n> --name-only     # blast radius first
   gh pr diff <n>                 # then what it actually did
   ```
   Files first, on purpose: the scope question is answerable before you read a line
   of logic, and it is the one that most often fails.
3. **Run the Verification** exactly as the item states it — do not substitute a
   command you like better. Quote the decisive line of output verbatim. If it cannot
   be run here (needs a browser, a deploy, prod data), say that; an unrun check is
   never a passed check.
4. **Check the four questions**:
   - every acceptance criterion satisfied, with a `file:line` or test name as evidence
   - Verification passes
   - nothing in `Out of scope` was touched. The item names a **behaviour, module or
     contract**, not paths — so **resolve it to the files it means in the tree as it
     is now**, list those files in the verdict, and check the diff against that list.
     You are not the implementer, and that is exactly why this resolution is yours to
     make: asking the author of a change to draw its own boundary is asking the wrong
     party. If the boundary cannot be resolved to anything concrete, score that
     dimension INCONCLUSIVE — never PASS
   - files changed that **no criterion asked for** — the usual shape of a 20-line
     change that arrived as 300
5. **Post the verdict** — fill `{this skill's dir}/templates/pr-review.md`:
   ```bash
   gh pr comment <n> --body "$(cat <<'EOF'
   ...filled template...
   EOF
   )"
   baton comment <id> --body "Verified PR #<n>: <PASS/FAIL> — <one line>."
   ```
   The PR gets the detail, the item gets the one-liner: the item is the trail
   someone reads in six months, and a full review table there is noise.
6. **Only on PASS** does the item advance — and this skill is the **only** thing that
   advances it. `baton-start` hands off here and does not move the item itself:
   ```bash
   baton advance <id> --to Done
   ```
   FAIL leaves it In Progress. Do not advance an item whose verification you could
   not run. Projects that declare `stages.verify` in config get this enforced by the
   CLI, which refuses any jump over that stage.

## Verdicts

| Verdict | Means |
|---|---|
| **PASS** | every criterion met, Verification run and green, scope clean |
| **FAIL** | a criterion unmet, Verification red, or out-of-scope files touched |
| **INCONCLUSIVE** | the item does not state enough to check it, or the check cannot run here |

INCONCLUSIVE is a real answer and the honest one when the item is thin. Do not round
it up to PASS because the diff looks fine — "looks fine" is what this skill exists to
replace. Then fix the item: an item that cannot be verified twice will not be
verifiable the third time either.

## Notes
- **Scope creep is a finding, not a bonus.** Extra work that nobody asked for goes in
  its own item — say which, and file it if it is worth keeping.
- Unrequested refactors inside touched files are the grey zone: flag them non-blocking
  if they are small and local, blocking if they make the diff unreviewable.
- Multi-part items: verifying one part ticks one box. See the closure gate in
  `baton-start` — the item does not reach Done until the last part lands.
