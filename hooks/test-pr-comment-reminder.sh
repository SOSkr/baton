#!/bin/bash
# Runnable check for the pr-comment-reminder hook. No network, no board: a stub
# `baton` on PATH records the calls, so what is under test is the hook's own
# decisions — when to post, when to shut up.
#
# Run: bash hooks/test-pr-comment-reminder.sh
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pr-comment-reminder"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

mkdir -p "$TMP/repo" "$TMP/bin"
git -C "$TMP/repo" init -q .
git -C "$TMP/repo" checkout -q -b feature/42-dark-mode

cat > "$TMP/bin/baton" <<'STUB'
#!/bin/bash
echo "baton $*" >> "$BATON_LOG"
[ "$1" = show ] && { [ "${BOARD:-up}" = down ] && exit 1; printf '%s\n' "${COMMENTS:-}"; }
exit 0
STUB
chmod +x "$TMP/bin/baton"

# fire <name> <command> [expect-comment: yes|no] ; extra env via COMMENTS/BOARD
fire() {
    local name=$1 cmd=$2 expect=$3
    : > "$TMP/log"
    printf '{"tool_input":{"command":"%s"},"tool_response":{"stdout":"https://h/x/pull/77"},"cwd":"%s"}' \
        "$cmd" "$TMP/repo" \
        | PATH="$TMP/bin:$PATH" BATON_LOG="$TMP/log" COMMENTS="${COMMENTS:-}" BOARD="${BOARD:-up}" \
          bash "$HOOK" > "$TMP/out" 2>/dev/null
    local got=no
    grep -q '^baton comment' "$TMP/log" && got=yes
    if [ "$got" = "$expect" ]; then
        echo "  ok   $name"
    else
        echo "  FAIL $name — expected comment=$expect, got=$got"; cat "$TMP/log"; fails=$((fails+1))
    fi
}

echo "pr-comment-reminder:"
COMMENTS="" BOARD=up   fire "posts the link when missing"        "gh pr create --fill" yes
COMMENTS="x https://h/x/pull/77 y" BOARD=up fire "does not repeat an existing link" "gh pr create --fill" no
COMMENTS="" BOARD=down fire "silent when the board is unreachable" "gh pr create --fill" no
COMMENTS="" BOARD=up   fire "ignores non-creation commands"       "gh pr list" no
# A release PR (--head <integration>) bundles many items: it must not be pinned to
# whichever item branch you happen to be standing on.
COMMENTS="" BOARD=up   fire "ignores a PR whose --head is another branch" \
                            "gh pr create --base master --head develop" no
COMMENTS="" BOARD=up   fire "still fires when --head IS the current branch" \
                            "gh pr create --head feature/42-dark-mode" yes

# The prefix set is the four commit types; the long forms stay accepted so a
# near-miss is never silently ignored.
for b in feat/42-dark-mode fix/42-x chore/42-x hotfix/42-x feature/42-x bugfix/42-x; do
    git -C "$TMP/repo" checkout -q -b "$b"
    COMMENTS="" BOARD=up fire "accepts $b" "gh pr create --fill" yes
done

# Board-prefixed ids: Plane shows CANGURO-42, `baton show` takes 42. Before this was
# handled the hook matched nothing and said nothing — the worst possible failure.
git -C "$TMP/repo" checkout -q -b feat/CANGURO-42-dark-mode
COMMENTS="" BOARD=up   fire "accepts a board-prefixed id"          "gh pr create --fill" yes
grep -q 'baton comment 42' "$TMP/log" \
    && echo "  ok   strips the board prefix from the id" \
    || { echo "  FAIL board prefix not stripped:"; cat "$TMP/log"; fails=$((fails+1)); }

git -C "$TMP/repo" checkout -q -b no-prefix-at-all
COMMENTS="" BOARD=up   fire "ignores a branch with no prefix"      "gh pr create --fill" no

git -C "$TMP/repo" checkout -q -b feat/sin-numero-aqui
COMMENTS="" BOARD=up   fire "ignores a prefixed branch with no id" "gh pr create --fill" no

git -C "$TMP/repo" checkout -q -b develop
COMMENTS="" BOARD=up   fire "ignores a branch with no item id"    "gh pr create --fill" no

[ "$fails" -eq 0 ] && { echo "ok"; exit 0; } || { echo "$fails failed"; exit 1; }
