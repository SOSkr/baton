#!/bin/bash
# Ship: PR <head> -> <base>, wait checks, merge, then watch the deploy-verification
# workflow (which is what usually creates the tag / release).
#
# Usage (from the target repo root):
#   ship-pr.sh "release summary" [--no-merge] [--base master] [--head develop] [--workflow verify-deploy]
set -euo pipefail

title="${1:?usage: ship-pr.sh \"release summary\" [--no-merge] [--base B] [--head H] [--workflow W]}"
shift

no_merge=""
base="master"
head="develop"
workflow="verify-deploy"
while [ $# -gt 0 ]; do
    case "$1" in
        --no-merge) no_merge=1; shift ;;
        --base)     base="${2:?--base needs a value}"; shift 2 ;;
        --head)     head="${2:?--head needs a value}"; shift 2 ;;
        --workflow) workflow="${2:?--workflow needs a value}"; shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

git fetch -q origin "$base" "$head"
mapfile -t commits < <(git log --oneline --no-merges "origin/$base..origin/$head")
if [ "${#commits[@]}" -eq 0 ]; then
    echo "Nothing to ship: $head has no commits over $base." >&2
    exit 1
fi

printf 'Commits to ship (%d):\n' "${#commits[@]}"
printf '  %s\n' "${commits[@]}"

body=$(printf '## Includes\n\n'; printf -- '- %s\n' "${commits[@]}")

# Reuse the open head->base PR if there is one, so the script is resumable
url=$(gh pr list --base "$base" --head "$head" --state open --json url -q '.[0].url')
if [ -z "$url" ]; then
    url=$(gh pr create --base "$base" --head "$head" --title "release: $title" --body "$body")
fi
echo "PR: $url"

# Checks take a few seconds to register after the PR is created
echo "Waiting for checks to register..."
for _ in $(seq 1 12); do
    [ -n "$(gh pr checks "$url" 2>/dev/null || true)" ] && break
    sleep 5
done
gh pr checks "$url" --watch --interval 10

if [ -n "$no_merge" ]; then
    echo "Checks green. Merge manually: gh pr merge $url --merge --admin"
    exit 0
fi

# --admin: branch protection asks for a review and you cannot approve your own PR
gh pr merge "$url" --merge --admin
echo "Merged into $base."

if ! gh workflow view "$workflow" > /dev/null 2>&1; then
    echo "note: no '$workflow' workflow in this repo — deploy not verified, no tag" >&2
    exit 0
fi

git fetch -q origin "$base"
sha=$(git rev-parse "origin/$base")
echo "Waiting for the '$workflow' run for $sha ..."
run_id=""
for _ in $(seq 1 30); do
    run_id=$(gh run list --workflow="$workflow" --json databaseId,headSha \
        -q ".[] | select(.headSha == \"$sha\") | .databaseId" | head -1)
    [ -n "$run_id" ] && break
    sleep 5
done
if [ -z "$run_id" ]; then
    echo "warning: no '$workflow' run appeared within 150s — check with 'gh run list'" >&2
    exit 1
fi

gh run watch "$run_id" --exit-status
git fetch -q --tags origin
echo "Deploy verified. Latest tag: $(git tag -l 'v*' --sort=-v:refname | head -1)"
