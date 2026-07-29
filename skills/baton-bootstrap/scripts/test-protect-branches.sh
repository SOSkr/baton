#!/bin/bash
# Runnable check for protect-branches.sh. No network: a stub `gh` on PATH records
# every call and replays canned answers, so what is under test is the script's own
# decisions — which branches, which JSON body, when to refuse.
#
# Run: bash skills/baton-bootstrap/scripts/test-protect-branches.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/protect-branches.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

mkdir -p "$TMP/bin"
cat > "$TMP/bin/gh" <<'STUB'
#!/bin/bash
echo "gh $*" >> "$GH_LOG"
case "$*" in
    *".permissions.admin"*)   echo "${ADMIN:-true}" ;;
    *"-X PUT"*)               cat > "$GH_LOG.body" ;;   # capture the request body
    *"/branches/"*"--silent"*) [ "${BRANCH_EXISTS:-1}" = 1 ] || exit 1 ;;
    *"/branches/"*)           echo "protected=true checks=test" ;;
    *"nameWithOwner"*)        echo "acme/app" ;;
esac
exit 0
STUB
# `baton config` must be absent for the fallback path, present for the config path
cat > "$TMP/bin/baton" <<'STUB'
#!/bin/bash
[ "${BATON_CONFIGURED:-0}" = 1 ] || exit 1
case "$2" in
    git.production)  echo main ;;
    git.integration) echo trunk ;;
esac
STUB
chmod +x "$TMP/bin/gh" "$TMP/bin/baton"

run() {   # run <name> -- <args...>   ; env via ADMIN/BRANCH_EXISTS/BATON_CONFIGURED
    : > "$TMP/log"; rm -f "$TMP/log.body"
    PATH="$TMP/bin:$PATH" GH_LOG="$TMP/log" \
        bash "$SCRIPT" --repo acme/app "$@" > "$TMP/out" 2>&1
    echo $?
}

check() {
    local name=$1 cond=$2
    if eval "$cond"; then echo "  ok   $name"; else
        echo "  FAIL $name"; sed 's/^/       /' "$TMP/log" 2>/dev/null; fails=$((fails+1)); fi
}

echo "protect-branches:"

rc=$(run --check test)
check "applies to both branches" '[ "$(grep -c "X PUT" "$TMP/log")" = 2 ]'
check "reads each one back"      '[ "$(grep -c "branches/.* --jq" "$TMP/log")" -ge 2 ]'
check "succeeds"                 '[ "$rc" = 0 ]'
check "requires the check"       'grep -q "\"contexts\": *\[ *\"test\" *\]" <(jq -c . "$TMP/log.body")  || jq -e ".required_status_checks.contexts == [\"test\"]" "$TMP/log.body" >/dev/null'
check "review count defaults 1"  'jq -e ".required_pull_request_reviews.required_approving_review_count == 1" "$TMP/log.body" >/dev/null'
check "enforce_admins off"       'jq -e ".enforce_admins == false" "$TMP/log.body" >/dev/null'

check "deletes merged branches"  'grep -q "PATCH repos/acme/app -F delete_branch_on_merge=true" "$TMP/log"'

rc=$(run --no-checks)
check "--no-checks nulls them"   'jq -e ".required_status_checks == null" "$TMP/log.body" >/dev/null'

# Refusing to guess is the point: neither default is safe to hand someone silently.
rc=$(run)
check "refuses with no flags"    '[ "$rc" = 2 ] && ! [ -f "$TMP/log.body" ]'

rc=$(ADMIN=false run --check test)
check "refuses without admin"    '[ "$rc" = 1 ] && ! [ -f "$TMP/log.body" ]'
check "says why"                 'grep -q "no admin" "$TMP/out"'

rc=$(BRANCH_EXISTS=0 run --check test)
check "fails on missing branch"  '[ "$rc" = 1 ]'

rc=$(BATON_CONFIGURED=1 run --check test)
check "takes names from config"  'grep -q "branches/main/protection" "$TMP/log" && grep -q "branches/trunk/protection" "$TMP/log"'

rc=$(run --check a --check b --reviews 2 --enforce-admins)
check "repeatable --check"       'jq -e ".required_status_checks.contexts == [\"a\",\"b\"]" "$TMP/log.body" >/dev/null'
check "--reviews honoured"       'jq -e ".required_pull_request_reviews.required_approving_review_count == 2" "$TMP/log.body" >/dev/null'
check "--enforce-admins honoured" 'jq -e ".enforce_admins == true" "$TMP/log.body" >/dev/null'

[ "$fails" -eq 0 ] && { echo "ok"; exit 0; } || { echo "$fails failed"; exit 1; }
