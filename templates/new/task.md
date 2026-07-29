## User story
As <role>, I want <capability> so that <outcome>.

## Context
Where this lives today, what currently happens, why it is a problem.

## Proposal
What changes. Concrete enough to implement without a second conversation.

## Acceptance criteria
- [ ] <observable condition that must hold when this is done>
- [ ] <...>

<!-- Optional — agent-executed items. Drop both if a human implements this. -->
## Verification
`<the one command to run>` — expected: <result>.
(or: open <URL/artifact>, expect <what you should see>)

## Out of scope
<what must not change — the behaviour, module or contract, **not a file path**. An
item can sit on the board for weeks and paths rot; worse, a stale path makes the
scope check pass for the wrong reason. `baton-verify` resolves this to real files
against the tree as it is at review time.>

<!-- Optional — ONE item that cannot land as a single change. A box is a part that
     must land before the item can close, and the gate in baton-start is what
     enforces it. Never one box per task — for several ITEMS, use an epic.

     Two shapes, same gate:

     per REPO — the work spans repos. Each box's area label maps to one via
       `repos:` in .baton/config.yaml, so baton-start knows where to branch
       without asking.

     per PHASE — a wide mechanical change (a rename across the whole codebase)
       where no vertical slice can be green on its own, because the moment the
       old form disappears everything breaks at once. Expand, migrate, contract:
       the old form survives until nothing calls it, so every phase stays green.
       These boxes are ordered by nature; baton-start says what that means for
       whoever picks the item up. -->
## Checklist
- [ ] `area:<x>` → <owner/repo> — PR: <link>
- [ ] `area:<y>` → <owner/repo> — PR: <link>

<!-- ...or, for a wide mechanical change, one box per phase, in order:
- [ ] expand — add <new form> beside <old form>, nothing uses it yet  — PR: <link>
- [ ] migrate — <package or directory>                                — PR: <link>
- [ ] migrate — <package or directory>                                — PR: <link>
- [ ] contract — delete <old form>, now that nothing calls it         — PR: <link>
-->

<!-- The area label on each box is what maps to a repo via `repos:` in
     .baton/config.yaml, so baton-start knows where to branch without asking. -->
