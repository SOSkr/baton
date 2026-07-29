## Verification — #<item> vs PR #<n>

**Verdict: <PASS / FAIL / INCONCLUSIVE>**

### Acceptance criteria
| # | Criterion | Met | Evidence |
|---|---|---|---|
| 1 | <criterion, quoted from the item> | yes/no | `file.py:42` / test name |
| 2 | <...> | | |

### Verification run
```
$ <the command from the item's Verification section>
<the decisive line of output, verbatim>
```
<or: "the item states no Verification" — say so, do not invent one>

### Out of scope
<clean · or the files touched that the item said not to touch, listed>

### Unrequested changes
Files in the diff that no criterion asked for: <list, or "none">

### Blocking
- <what must change before merge>

### Non-blocking
- <what can land as a follow-up item>
