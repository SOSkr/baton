# Hooks (optional)

A comment nobody writes is a board nobody can read. Skills say *when* to comment,
but nothing forces the agent to remember. These hooks close that gap: the harness
detects the event and injects a reminder; the agent still writes the content,
because only it knows what happened.

Optional — baton works without them.

## `pr-comment-reminder`

Fires after a `gh pr create`, when the current branch follows baton's convention —
`<prefix>/<id>-<slug>`, prefix one of `feat|fix|chore|hotfix` (the long forms
`feature|bugfix` are accepted too). The id is the number `baton show` takes, bare or
with the board's prefix: `feat/42-dark-mode` and `feat/CANGURO-42-dark-mode` both
resolve to item 42. Then it does two things:

1. **Posts the PR link to the item** — the one fact the board cannot derive on its
   own. A board on one host knows nothing about a repo on another, so this link
   exists nowhere else. Skipped if the link is already in the comments.
2. **Reminds the agent to add the rest** — what it does, what is still open, what
   blocked it. That needs judgment; a script writing it would produce noise.

Silent otherwise: wrong command, a branch with no item id, no `baton` on PATH, or a
board that does not answer (most repos have no board — it must not break them).
It also stays out of the way when the PR is about a **different** branch — an
explicit `--head` that is not the one you are on, which is what a release PR looks
like (`--base master --head develop`). Those bundle many items, so pinning their
link to whichever item branch you happen to be standing on would be a lie.
Failures are swallowed; the hook never fails your turn.

Checks: `bash hooks/test-pr-comment-reminder.sh` (no network, stubbed `baton`).

Give it a `timeout` of ~20s: it makes up to two board calls, which cross the network
for a hosted backend.

Install it for Claude Code by copying the script somewhere on your machine and
registering it in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "~/.claude/hooks/pr-comment-reminder", "timeout": 20 }
        ]
      }
    ]
  }
}
```

Needs `jq` and `git` on PATH.

## Why only PR creation

Commits are too frequent to report and git already records them; a comment per
commit is noise that trains everyone to skip comments. The events worth a comment
are the ones another person cannot reconstruct: **a PR exists**, **this is
blocked**, **my part is done**. The first is mechanically detectable, so it gets a
hook. The other two need judgment — they live in `baton-start`.

## The risk worth knowing

This hook writes to a board other people read. If a branch is named
`feature/42-...` but 42 is not the item you think it is, the comment lands on the
wrong item. That is why the parse demands the full `<prefix>/<digits>-<slug>` shape
and gives up on anything else — and why the auto-posted text is one factual line,
not a summary. If you would rather it never wrote on its own, delete the
`baton comment` block: the reminder alone still works.
