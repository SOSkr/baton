# Hooks (optional)

A comment nobody writes is a board nobody can read. Skills say *when* to comment,
but nothing forces the agent to remember. These hooks close that gap: the harness
detects the event and injects a reminder; the agent still writes the content,
because only it knows what happened.

Optional — baton works without them.

## `pr-comment-reminder`

Fires after a `gh pr create`, when the current branch follows baton's convention
(`feature/<id>-<slug>`, plus `bugfix|hotfix|chore|fix`). Reminds the agent to run
`baton comment <id>` with the PR link and what is still open. Silent otherwise:
wrong command, or a branch with no item id, and it exits without a word.

Install it for Claude Code by copying the script somewhere on your machine and
registering it in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "~/.claude/hooks/pr-comment-reminder", "timeout": 10 }
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
