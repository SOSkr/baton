#!/bin/bash
# Protect the integration and production branches, so the thing that writes code
# cannot merge its own work unreviewed.
#
# This is shipped rather than left as prose because branch protection is NOT
# language-specific: it is the same GitHub policy for every project. The CI workflow
# that produces the required check IS language-specific — that part stays yours.
#
# Needs ADMIN rights. Uses $GH_ADMIN_TOKEN when set, so the agent credential never
# needs them.
#
# Usage (from the target repo, or anywhere with --repo):
#   protect-branches.sh --check test
#   protect-branches.sh --repo acme/app --check test --check lint --reviews 2
#   protect-branches.sh --no-checks          # CI does not exist yet; rerun later
#
# Idempotent: the API call is a PUT, so rerunning is safe and is how you add a
# required check once CI exists.
set -euo pipefail

repo=""
reviews=1
enforce_admins=false
no_checks=""
checks=()

while [ $# -gt 0 ]; do
    case "$1" in
        --repo)            repo="${2:?--repo needs OWNER/REPO}"; shift 2 ;;
        --check)           checks+=("${2:?--check needs a name}"); shift 2 ;;
        --no-checks)       no_checks=1; shift ;;
        --reviews)         reviews="${2:?--reviews needs a number}"; shift 2 ;;
        --enforce-admins)  enforce_admins=true; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ "${#checks[@]}" -eq 0 ] && [ -z "$no_checks" ]; then
    cat >&2 <<'MSG'
Refusing to guess: pass --check <name>, or --no-checks to say you mean it.

A protection with no required check lets a red PR merge. A protection requiring a
check that does not exist yet makes every PR HANG — it does not fail, it waits for a
status that never arrives. Neither is a default anyone should get by accident.

Require ONE aggregated name, never the names a build matrix produces: a matrix
reports `test (3.11)`, `test (3.12)`, ... and no plain `test`, so adding a version
later would block every PR until someone with admin edits this again.
MSG
    exit 2
fi

# The admin credential is the point. Falling back to the agent's would half-apply the
# protections and report success — repo writes succeed, admin writes do not.
if [ -n "${GH_ADMIN_TOKEN:-}" ]; then
    export GH_TOKEN="$GH_ADMIN_TOKEN"
else
    echo "note: \$GH_ADMIN_TOKEN not set — using the current credential." >&2
fi

[ -n "$repo" ] || repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)

perms=$(gh api "repos/$repo" --jq '.permissions.admin')
if [ "$perms" != "true" ]; then
    echo "error: this credential has no admin on $repo — branch protection needs it." >&2
    echo "       Set \$GH_ADMIN_TOKEN, or have whoever holds admin run this." >&2
    exit 1
fi

# Branch names come from the project's config; the classic pair is only a fallback.
production=$(baton config git.production 2>/dev/null || echo master)
integration=$(baton config git.integration 2>/dev/null || echo develop)

# Built conditionally on purpose: `printf '%s\n'` with no arguments still prints one
# empty line, which would make contexts `[""]` — a protection requiring a check named
# empty string, which no run ever reports. Every PR would hang, forever.
if [ "${#checks[@]}" -gt 0 ]; then
    contexts=$(printf '%s\n' "${checks[@]}" | jq -R . | jq -s .)
else
    contexts='[]'
fi

body=$(jq -n \
    --argjson reviews "$reviews" \
    --argjson enforce "$enforce_admins" \
    --argjson contexts "$contexts" \
    '{
       required_pull_request_reviews: { required_approving_review_count: $reviews },
       required_status_checks: (if ($contexts | length) > 0
                                then { strict: false, contexts: $contexts }
                                else null end),
       enforce_admins: $enforce,
       restrictions: null
     }')

# Setting de repo, no de protección, pero la misma clase de política: agnóstica del
# lenguaje y se pone una vez. Con agentes pesa más de lo normal — un día de trabajo
# son veinte ramas, y sin esto quedan las veinte colgando en el remoto.
gh api -X PATCH "repos/$repo" -F delete_branch_on_merge=true > /dev/null
echo "  delete_branch_on_merge: true"

failed=0
for br in "$production" "$integration"; do
    if [ "$br" = "$production" ] && [ "$br" = "$integration" ] && [ -n "${done_once:-}" ]; then
        continue                      # trunk-based: both names point at one branch
    fi
    done_once=1
    if ! gh api "repos/$repo/branches/$br" --silent 2>/dev/null; then
        echo "  $br: does NOT exist — skipped" >&2
        failed=1
        continue
    fi
    gh api -X PUT "repos/$repo/branches/$br/protection" --input - <<<"$body" > /dev/null
    # Read it back. A PUT that returned 200 and a branch that is actually protected
    # are different claims.
    state=$(gh api "repos/$repo/branches/$br" \
            --jq '"protected=\(.protected) checks=\(.protection.required_status_checks.contexts // [] | join(","))"')
    echo "  $br: $state"
done

[ "$failed" -eq 0 ] || { echo "some branches were skipped — see above" >&2; exit 1; }
echo "Protected $repo: reviews>=$reviews, enforce_admins=$enforce_admins."
