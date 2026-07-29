---
name: baton-triage
description: >
  Review/triage a work-item for viability, value, and fit; score it and post the
  verdict. Use when the user says "triage X", "review idea/item", "evaluate X",
  "revisar idea". Does not change the stage — records the assessment.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton)
credential: agent
---

# baton triage

Structured assessment of a work-item. `baton` reads/writes the board; you provide
the **judgment**. Triage records a verdict; it does not move the stage (approval is
`baton-approve`).

## Workflow

1. **Read** the item + comments (+ any linked doc + relevant project spec):
   ```bash
   baton show <id>            # title, stage, labels, url
   # full thread: use the backend directly, e.g. gh issue view <id> --comments
   ```
2. **Score** against the criteria below (0-5 each). Adapt example checks to the
   project's domain.
3. **Post the verdict** — fill `{this skill's dir}/templates/verdict.md`:
   ```bash
   baton comment <id> --body "$(cat <<'EOF'
   ## Review
   ...
   EOF
   )"
   ```
   For items with a versioned doc, append a `## Review (YYYY-MM-DD)` section there
   and leave a short verdict comment.
4. **No stage change** — the review comment is the record of "reviewed, pending
   decision". If **rejected**, use `baton-reject`.
5. **Present** the recommendation (approve / revise / reject). If the user approves
   on the spot → continue with `baton-approve`.

## Criteria (0-5 each)
1. **Clarity** — specific user story, well-defined problem.
2. **Viability** — implementable with the current architecture; deps identified;
   realistic complexity.
3. **Value / Impact** — real problem; improves the product's core goals.
4. **Consistency** — aligned with existing patterns; doesn't contradict current
   behavior. Check related items for conflicts/synergies (`baton list --label ...`).
5. **Completeness** — clear acceptance criteria, edge cases, concrete proposal. If an
   agent will implement it and nothing says how to verify the result, cap this at 3.

## Recommendation by score
- **≥ 15/25** → approve · **10-14** → revise (specific improvements) · **< 10** → reject.

Always explain WHY, not just the number.
