#!/usr/bin/env bash
# Exercises only ActionGate: 2 reads + 1 write, plus negative cases.
#
# ActionGate holds no authorization logic of its own. It is a consumer that
# asks ActionJurisdiction whether an exact, consumer-bound action commitment is
# authorized, and records the execution if so. So a meaningful test needs an
# action that is already AUTHORIZED upstream.
#
# Two modes:
#   1. Given an authorized action (default) - read its hashes from
#      ActionJurisdiction, then prove the gate accepts the exact commitment
#      and rejects tampered variants.
#   2. Gate-only mode (--gate-only) - exercise the reads and the revert paths
#      with no dependency on an authorized action. Works immediately.
#
# Usage:
#   AG=0x<gate> AJ=0x<jurisdiction> ./scripts/gate_check.sh
#   AG=0x<gate> ./scripts/gate_check.sh --gate-only
#   AG=0x<gate> AJ=0x<j> ACTION_ID=3 ./scripts/gate_check.sh
#
# ACTION_ID is optional; without it the script scans ids 1..10 for the first
# AUTHORIZED action. The context hash is read from that action rather than
# taken as an input, so it never needs to be supplied.
#
# The published Studionet pair 0xb1748CD7.../0xE2b921C8... is a superseded
# build that used unprefixed create_matrix/get_matrix and an "AuthorityMatrix"
# commitment domain. This script targets the prefixed build only.

set -euo pipefail

export AJ="${AJ:-0x58bad42C5357ad88A720e378Be6256148facAE01}"
export AG="${AG:-}"
GATE_ONLY=0
[[ "${1:-}" == "--gate-only" ]] && GATE_ONLY=1

die() { echo "$*" >&2; exit 1; }

[[ -n "$AG" ]] || die "AG is not set. Example: AG=0x<gate address> $0"

command -v genlayer >/dev/null 2>&1 || die "genlayer CLI not found"
command -v python3  >/dev/null 2>&1 || die "python3 not found"

step() { printf '\n========== %s\n' "$*"; }
ok()   { echo "PASS: $*"; }
bad()  { echo "FAIL: $*"; FAILED=$((FAILED + 1)); }
FAILED=0

# Studionet RPC drops connections intermittently. Retry only on transport-level
# errors so a real contract revert still surfaces immediately.
NET_ERR='fetch failed|ECONNRESET|ETIMEDOUT|EAI_AGAIN|socket hang up|502 |503 |network error|aborted|ConnectTimeout'

try_call() {
  local n out
  for n in 1 2 3 4 5; do
    if out=$(genlayer call "$@" 2>&1); then printf '%s\n' "$out"; return 0; fi
    if grep -Eq "$NET_ERR" <<<"$out"; then sleep 4; continue; fi
    printf '%s\n' "$out"; return 1
  done
  printf '%s\n' "$out"; return 2
}

# Same, for writes, which must also reach leader consensus.
try_write() {
  local n out
  for n in 1 2 3 4 5; do
    if out=$(genlayer write "$@" 2>&1); then printf '%s\n' "$out"; return 0; fi
    if grep -Eq "$NET_ERR" <<<"$out"; then sleep 4; continue; fi
    printf '%s\n' "$out"; return 1
  done
  printf '%s\n' "$out"; return 2
}

# Read a top-level field out of a get_action / get_execution result.
field() {
  sed -n "s/^  $2: \(.*\)$/\1/p" <<<"$1" | tr -d "'" | head -1 |
    sed -e 's/,*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# Decode the base64 UserError the node returns on a contract revert.
# Note: python3 -c keeps stdin on the pipe; a heredoc would swallow it.
revert_reason() {
  python3 -c '
import re, sys, base64
t = sys.stdin.read()
m = re.search(r"result: \x27([A-Za-z0-9+/=]{8,})\x27", t)
if m:
    try:
        print(base64.b64decode(m.group(1)).decode().lstrip("\x00\x01").strip())
    except Exception:
        pass
' 2>/dev/null || true
}

# A contract revert on a write still exits 0 from the CLI: the rollback rides
# in the receipt as `status: 'rollback', payload: '...'`. Prints that payload
# and returns 0 only when the write actually rolled back.
write_rollback() {
  python3 -c '
import re, sys, base64
t = sys.stdin.read()
m = re.search(r"status: \x27rollback\x27,\s*payload: \x27([^\x27]*)", t)
if m:
    print(m.group(1)); sys.exit(0)
m = re.search(r"result: \x27([A-Za-z0-9+/=]{8,})\x27", t)
if m:
    try:
        print(base64.b64decode(m.group(1)).decode().lstrip("\x00\x01").strip()); sys.exit(0)
    except Exception:
        pass
sys.exit(1)
' 2>/dev/null
}

step "0. environment"
genlayer network info | grep -E "alias|chainId" || true
genlayer account list
echo "gate:        $AG"
echo "jurisdiction: $AJ"
[[ $GATE_ONLY -eq 1 ]] && echo "mode:        gate-only (no authorized action required)"

JUR=""
if [[ $GATE_ONLY -eq 0 ]]; then
  step "0b. detect the registry method prefix"
  if probe=$(try_call "$AJ" actionjurisdication_get_constants 2>&1) &&
    grep -q "successfully executed" <<<"$probe"; then
    JUR=actionjurisdication
  elif probe=$(try_call "$AJ" actionjurisdiction_get_constants 2>&1) &&
    grep -q "successfully executed" <<<"$probe"; then
    JUR=actionjurisdiction
  else
    die "registry $AJ exposes neither actionjurisdication_* nor actionjurisdiction_*"
  fi
  echo "registry prefix: ${JUR}_"
fi

step "1. deployed schema of the gate"
genlayer schema "$AG" 2>&1 | grep -iE "schema retrieved|error" | head -3 || true

step "2. constructor binding is readable from the gate's own schema"
genlayer schema "$AG" 2>&1 | grep -iE "authority_matrix_address|action_jurisdiction_address|context_hash" | head -4 || true

UNKNOWN=$(python3 -c "print('f'*64)")

step "3. confirm the gate exposes the prefixed method names"
probe=$(try_call "$AG" action_gate_was_executed --args "$UNKNOWN" 2>&1) || true
if grep -q "private method" <<<"$probe"; then
  echo "That address does not expose action_gate_was_executed." >&2
  echo "It looks like the superseded AuthorityMatrix-era build, which uses" >&2
  echo "unprefixed was_executed. Point AG at the gate redeployed from this source." >&2
  exit 2
fi
ok "gate exposes the prefixed build"

step "3. read: action_gate_was_executed on an unknown hash (expect false)"
out=$(try_call "$AG" action_gate_was_executed --args "$UNKNOWN" 2>&1) || true
echo "$out" | grep -E "^(true|false)$" >/dev/null \
  && ok "was_executed($UNKNOWN) = $(echo "$out" | grep -E '^(true|false)$' | head -1)" \
  || bad "was_executed($UNKNOWN) did not return a bare boolean"

step "4. read: action_gate_get_execution on an unknown hash (expect EXPECTED revert)"
out=$(try_call "$AG" action_gate_get_execution --args "$UNKNOWN" 2>&1) && rc=0 || rc=$?
reason=$(printf '%s' "$out" | revert_reason)
if [[ $rc -ne 0 ]]; then
  [[ "$reason" == *unknown* ]] \
    && ok "get_execution rejected with: $reason" \
    || bad "reverted but reason was unexpected: ${reason:-<none>}"
else
  bad "get_execution on an unknown hash unexpectedly succeeded"
fi

if [[ $GATE_ONLY -eq 1 ]]; then
  step "gate-only mode complete"
  echo "reads and revert paths exercised; skipped the write, which needs an authorized action"
  [[ $FAILED -eq 0 ]] || die "$FAILED check(s) failed"
  echo "ALL CHECKS PASSED"
  exit 0
fi

step "5. locate an AUTHORIZED action in ActionJurisdiction"
if [[ -z "${ACTION_ID:-}" ]]; then
  ACTION_ID=""
  FALLBACK_ID=""
  for n in $(seq 1 10); do
    out=$(try_call "$AJ" "${JUR}_get_action" --args "$n" 2>&1) || continue
    [[ "$(field "$out" status_name)" == "AUTHORIZED" ]] || continue
    [[ -n "$FALLBACK_ID" ]] || FALLBACK_ID=$n
    # Prefer an action this gate has not consumed: only an unconsumed
    # action_hash can reach the authorization check (replay wins otherwise).
    ah=$(field "$out" action_hash)
    used=$(try_call "$AG" action_gate_was_executed --args "$ah" 2>&1 |
      grep -E '^(true|false)$' | head -1 || true)
    if [[ "$used" != "true" ]]; then ACTION_ID=$n; break; fi
  done
  [[ -n "$ACTION_ID" ]] || ACTION_ID=$FALLBACK_ID
  [[ -n "$ACTION_ID" ]] || die "no AUTHORIZED action found in ids 1..10. Create one first (scripts/smoke_studionet.sh) or pass ACTION_ID=."
  echo "using action_id=$ACTION_ID"
fi

step "6. read: the action's binding fields"
ACTION=$(try_call "$AJ" "${JUR}_get_action" --args "$ACTION_ID" 2>&1) || true
for f in status_name action_hash description_hash action_commitment jurisdiction_hash matrix_hash context_hash; do
  printf '  %-20s %s\n' "$f" "$(field "$ACTION" "$f")"
done
AH=$(field "$ACTION" action_hash)
DH=$(field "$ACTION" description_hash)
CM=$(field "$ACTION" action_commitment)
# The gate's 5th argument is the jurisdiction hash. Matrix-era deployments
# (built before matrix -> jurisdiction rename) expose the same value as
# matrix_hash, so fall back to it when jurisdiction_hash is absent.
JH=$(field "$ACTION" jurisdiction_hash)
JH=${JH:-$(field "$ACTION" matrix_hash)}
CTX_ACTUAL=$(field "$ACTION" context_hash)
[[ -n "$AH" && -n "$DH" && -n "$CM" && -n "$JH" ]] || die "could not read the action's binding fields"

step "7. gate already executed this action? (decides the write path)"
EXECUTED=$(try_call "$AG" action_gate_was_executed --args "$AH" 2>&1 | grep -E '^(true|false)$' | head -1 || true)
echo "was_executed($AH) = $EXECUTED"

if [[ "$EXECUTED" == "true" ]]; then
  step "8. read: action_gate_get_execution replay-protection check"
  out=$(try_call "$AG" action_gate_get_execution --args "$AH" 2>&1) || true
  g_caller=$(field "$out" caller); g_aid=$(field "$out" action_id)
  g_ah=$(field "$out" action_hash);    g_dh=$(field "$out" description_hash)
  g_cm=$(field "$out" action_commitment); g_jh=$(field "$out" jurisdiction_hash)
  g_ctx=$(field "$out" context_hash)
  g_jh=${g_jh:-$(field "$out" matrix_hash)}
  [[ "$g_ah" == "$AH" ]] && ok "recorded action_hash matches"  || bad "action_hash mismatch: $g_ah"
  [[ "$g_dh" == "$DH" ]] && ok "recorded description_hash matches" || bad "description_hash mismatch: $g_dh"
  [[ "$g_cm" == "$CM" ]] && ok "recorded action_commitment matches" || bad "action_commitment mismatch: $g_cm"
  [[ "$g_jh" == "$JH" ]] && ok "recorded jurisdiction_hash matches"  || bad "jurisdiction_hash mismatch: $g_jh"
  [[ "$g_ctx" == "$CTX_ACTUAL" ]] && ok "recorded context_hash matches" || bad "context_hash mismatch: $g_ctx"
  echo "  caller=$g_caller action_id=$g_aid"

  step "9. replay must be refused (expect EXPECTED revert)"
  out=$(try_write "$AG" action_gate_execute --args "$ACTION_ID" "$AH" "$DH" "$CM" "$JH" 2>&1) || true
  reason=$(printf '%s' "$out" | write_rollback) && rolled=1 || rolled=0
  [[ $rolled -eq 1 && "$reason" == *already* ]] \
    && ok "replay refused: $reason" \
    || bad "replay not refused as expected (reason=${reason:-<none>})"

  step "10. tampered variants: skipped (already-executed)"
  echo "  the gate rejects a replayed action_hash before it re-checks authorization,"
  echo "  so consumer binding can only be demonstrated before the first execute."
  echo "  Re-run against a fresh action to exercise steps 10/11."
else
  # The gate checks replay protection before authorization, so the tampered
  # variants must be attempted while the action_hash is still unrecorded.
  step "8. tampered description_hash must be refused (consumer binding)"
  # The gate forwards the description hash to the jurisdiction, so a substituted
  # value breaks the commitment and the action is no longer authorized for it.
  BAD_DH=$(python3 -c "print('a'*64)")
  out=$(try_write "$AG" action_gate_execute \
          --args "$ACTION_ID" "$AH" "$BAD_DH" "$CM" "$JH" 2>&1) || true
  reason=$(printf '%s' "$out" | write_rollback) && rolled=1 || rolled=0
  [[ $rolled -eq 1 && "$reason" == *not*valid* ]] \
    && ok "refused: $reason" \
    || bad "tampered description_hash not refused (reason=${reason:-<none>})"

  step "9. tampered jurisdiction_hash must be refused"
  out=$(try_write "$AG" action_gate_execute \
          --args "$ACTION_ID" "$AH" "$DH" "$CM" "$BAD_DH" 2>&1) || true
  reason=$(printf '%s' "$out" | write_rollback) && rolled=1 || rolled=0
  [[ $rolled -eq 1 && "$reason" == *not*valid* ]] \
    && ok "refused: $reason" \
    || bad "tampered jurisdiction_hash not refused (reason=${reason:-<none>})"

  step "10. write: action_gate_execute with the exact commitment"
  out=$(try_write "$AG" action_gate_execute --args "$ACTION_ID" "$AH" "$DH" "$CM" "$JH")
  reason=$(printf '%s' "$out" | write_rollback) && rolled=1 || rolled=0
  [[ $rolled -eq 0 ]] && grep -E "✔ Write" <<<"$out" >/dev/null \
    && ok "execute accepted and finalized" \
    || { echo "rollback: ${reason:-<none>}"; echo "$out" | tail -8; bad "execute did not report success"; }

  step "11. confirm the execution is recorded"
  EXECUTED=$(try_call "$AG" action_gate_was_executed --args "$AH" 2>&1 | grep -E '^(true|false)$' | head -1 || true)
  [[ "$EXECUTED" == "true" ]] && ok "was_executed flipped to true" || bad "was_executed is '$EXECUTED'"
  REC=$(try_call "$AG" action_gate_get_execution --args "$AH" 2>&1) || true
  [[ "$(field "$REC" action_commitment)" == "$CM" ]] \
    && ok "recorded commitment matches what was submitted" \
    || bad "recorded commitment does not match the submission"

  step "12. replay must be refused (expect EXPECTED revert)"
  out=$(try_write "$AG" action_gate_execute --args "$ACTION_ID" "$AH" "$DH" "$CM" "$JH" 2>&1) || true
  reason=$(printf '%s' "$out" | write_rollback) && rolled=1 || rolled=0
  [[ $rolled -eq 1 && "$reason" == *already* ]] \
    && ok "replay refused: $reason" \
    || bad "replay not refused as expected (reason=${reason:-<none>})"
fi

step "13. non-hex / wrong-length hashes must be refused before any upstream call"
out=$(try_write "$AG" action_gate_execute --args "$ACTION_ID" "$AH" "zz" "$CM" "$JH" 2>&1) || true
reason=$(printf '%s' "$out" | write_rollback) && rolled=1 || rolled=0
[[ $rolled -eq 1 && "$reason" == *64*lowercase*hex* ]] \
  && ok "refused: $reason" \
  || bad "malformed hash not refused as expected (reason=${reason:-<none>})"

step "14. execution record unchanged after the refused attempts"
FINAL=$(try_call "$AG" action_gate_was_executed --args "$AH" 2>&1 | grep -E '^(true|false)$' | head -1 || true)
[[ "$FINAL" == "$EXECUTED" ]] \
  && ok "was_executed still $FINAL, no partial write occurred" \
  || bad "was_executed changed from $EXECUTED to $FINAL after refused writes"

step "summary"
if [[ $FAILED -eq 0 ]]; then
  echo "ALL CHECKS PASSED"
else
  die "$FAILED check(s) failed"
fi
