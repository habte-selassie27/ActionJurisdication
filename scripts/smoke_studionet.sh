#!/usr/bin/env bash
set -euo pipefail

# Exercises every public method of both contracts: 7 reads + 10 writes = 17.
#   ActionJurisdiction ($AJ): get_constants, get_jurisdiction, get_action, has_approved,
#     is_authorized_for (reads) + create_jurisdiction, add_dimension, add_approver,
#     seal_jurisdiction, open_action, classify_action, approve, revoke_approval,
#     cancel_action (writes)
#   ActionGate ($AG): was_executed, get_execution (reads) + execute (write)
# Method names are PREFIXED (actionjurisdiction_* / action_gate_*), matching the
# current source tree, which renamed the authority-matrix concept to
# "jurisdiction" throughout.
#
# $AJ defaults to the ActionJurisdiction redeployed from this source at
# 0x58bad42C5357ad88A720e378Be6256148facAE01. $AG has no default: the matching
# ActionGate address must be supplied, e.g.
#
#   AG=0x<gate address> ./scripts/smoke_studionet.sh
#
# The superseded pair 0xb1748CD7.../0xE2b921C8... was built from a separate
# codebase that called itself "AuthorityMatrix" and exposed UNPREFIXED
# create_matrix / get_matrix / seal_matrix. Do not point $AG at that gate.
#
# Step 20 diffs the exercised set against `genlayer schema` and fails if any
# public method was skipped.

export AJ="${AJ:-0x58bad42C5357ad88A720e378Be6256148facAE01}"
export AG="${AG:-}"   # set to the new ActionGate address before running
export CTX=9d0b60fc4e8005409a78683d53aa781bf5ff69f431a8ca3079f5285857f46dca

RABBY=0x5B3661C576c7001e6d6279C67F3779705d334c89
MAIN=0x37cdbd86743e2b80486413e89ca4c70a58147889

AH_DONE=2222222222222222222222222222222222222222222222222222222222222222
# action_hash is unique per deployment (actionjurisdication.py:641), so derive
# fresh ones per run; the fixed 4444/5555 constants are already registered.
AH_NEW=$(python3 -c "import hashlib,time;print(hashlib.sha256(('smoke-'+str(time.time_ns())).encode()).hexdigest())")
AH_CANCEL=$(python3 -c "import hashlib,time;print(hashlib.sha256(('cancel-'+str(time.time_ns())).encode()).hexdigest())")

if [[ -z "$AG" ]]; then
  echo "AG is not set. Pass the new ActionGate address, e.g.:" >&2
  echo "  AG=0x<gate address> $0" >&2
  exit 2
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

step() { printf '\n========== %s\n' "$*"; }

EXERCISED=()

NET_ERR='fetch failed|ECONNRESET|ETIMEDOUT|EAI_AGAIN|socket hang up|502 |503 |network error|aborted'

try_call() {
  local n out
  for n in 1 2 3 4 5; do
    if out=$(genlayer call "$@" 2>&1); then
      printf '%s\n' "$out"
      return 0
    fi
    if grep -Eq "$NET_ERR" <<<"$out"; then
      sleep 4
      continue
    fi
    printf '%s\n' "$out" >&2
    return 1
  done
  printf '%s\n' "$out" >&2
  return 2
}

call() {
  EXERCISED+=("$2")
  local rc=0
  try_call "$@" || rc=$?
  if [[ $rc -eq 2 ]]; then
    echo "network failure calling $2 after 5 attempts" >&2
    exit 1
  fi
  return $rc
}

LEADER_CHECK='
import re, sys
t = sys.stdin.read()
i = t.find("leader_receipt")
if i < 0:
    print("no leader_receipt in output", file=sys.stderr); sys.exit(2)
end = len(t)
for marker in ("validators:", "mode: \x27validator\x27"):
    j = t.find(marker, i)
    if j != -1:
        end = min(end, j)
seg = t[i:min(end, i + 20000)]
results = re.findall(r"execution_result: \x27([A-Z]+)\x27", seg)
if not results:
    print("no execution_result in leader receipt", file=sys.stderr); sys.exit(2)
final = results[-1]
if final != "SUCCESS":
    p = re.search(r"status: \x27rollback\x27,\s*payload: \x27([^\x27]*)", seg) or \
        re.search(r"status: \x27rollback\x27,\s*payload: \x27([^\x27]*)", t)
    if p:
        print("rollback: " + p.group(1)[:400], file=sys.stderr)
    s = re.search(r"stderr: \x27([^\x27]*)", seg)
    if s and s.group(1):
        print("stderr: " + s.group(1)[:600], file=sys.stderr)
    note = "" if len(results) == 1 else " receipts=" + ",".join(results)
    print("leader execution_result: " + final + note, file=sys.stderr)
    sys.exit(1)
sys.exit(0)
'

write() {
  local out rc=0 diag="" drc=0 h="" rdiag="" rrc=0
  EXERCISED+=("$2")
  out=$(genlayer write "$@" 2>&1) || rc=$?
  if [[ $rc -ne 0 ]] || grep -Eq "^error:|✖" <<<"$out"; then
    echo "$out" | tail -25 >&2
    if grep -Eq "$NET_ERR" <<<"$out"; then
      echo "NETWORK FAILURE during write of $2 - re-run; ids are re-discovered" >&2
    else
      echo "WRITE REJECTED: $*" >&2
    fi
    exit 1
  fi
  diag=$(printf '%s' "$out" | python3 -c "$LEADER_CHECK" 2>&1) || drc=$?
  if [[ $drc -eq 2 ]]; then
    h=$(grep -Eo "hash: '?0x[0-9a-fA-F]{64}" <<<"$out" | head -1 | grep -Eo "0x[0-9a-fA-F]{64}")
    if [[ -n "$h" ]]; then
      rdiag=$(printf '%s' "$(genlayer receipt "$h" 2>/dev/null)" | python3 -c "$LEADER_CHECK" 2>&1) || rrc=$?
      if [[ $rrc -eq 0 ]]; then
        drc=0
        diag=""
      elif [[ $rrc -eq 1 ]]; then
        drc=1
        diag="$rdiag"
      fi
    fi
    if [[ $drc -eq 2 ]]; then
      echo "WARN: could not verify leader receipt for $2 ($h)" >&2
      printf '%s\n' "$diag" >&2
      drc=0
    fi
  fi
  if [[ $drc -ne 0 ]]; then
    printf '%s\n' "$diag" >&2
    echo "CONTRACT EXECUTION FAILED: $*" >&2
    echo "(validator 'idle'/quorum ERROR lines are normal and ignored)" >&2
    exit 1
  fi
  grep -E "^ +hash:|status_name|✔ Write" <<<"$out" || true
}

fetch_schema() {
  local n out
  for n in 1 2 3 4 5; do
    if out=$(genlayer schema "$1" 2>&1) && grep -q "schema retrieved successfully" <<<"$out"; then
      printf '%s\n' "$out" >"$2"
      return 0
    fi
    sleep 4
  done
  echo "$out" | tail -6 >&2
  return 1
}

next_free() {
  local method=$1 n=$2 rc=0
  while :; do
    rc=0
    try_call "$AJ" "$method" --args "$n" >/dev/null 2>&1 || rc=$?
    if [[ $rc -eq 0 ]]; then
      n=$((n + 1))
      continue
    fi
    break
  done
  if [[ $rc -eq 2 ]]; then
    echo "network failure probing $method" >&2
    exit 1
  fi
  echo "$n"
}

action_field() {
  local rc=0 out
  out=$(try_call "$AJ" actionjurisdiction_get_action --args "$1" 2>/dev/null) || rc=$?
  if [[ $rc -eq 2 ]]; then
    echo "network failure reading action $1" >&2
    exit 1
  fi
  [[ $rc -eq 0 ]] || return 1
  sed -n "s/^  $2: \(.*\)$/\1/p" <<<"$out" | tr -d "'" | head -1 |
    sed -e 's/,*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

step "0. environment"
genlayer account list
genlayer account use rabby
genlayer network set studionet
genlayer network info

step "1. schema (readonly flags decide call vs write)"
fetch_schema "$AJ" "$TMP/schema_AJ.txt" || {
  echo "schema fetch failed for AJ" >&2
  exit 1
}
fetch_schema "$AG" "$TMP/schema_AG.txt" || {
  echo "schema fetch failed for AG" >&2
  exit 1
}
grep -E "^ +[a-z_]+: \{|readonly" "$TMP/schema_AJ.txt" "$TMP/schema_AG.txt"

step "2. ActionGate read 1/2: was_executed (already-executed action)"
call "$AG" action_gate_was_executed --args "$AH_DONE"

step "3. ActionGate read 2/2: get_execution"
call "$AG" action_gate_get_execution --args "$AH_DONE"

step "4. jurisdiction read 1/5: get_constants"
call "$AJ" actionjurisdiction_get_constants

JURISDICTION_ID=$(next_free get_jurisdiction 1)
step "5. jurisdiction read 2/5: get_jurisdiction (first free id = $JURISDICTION_ID)"
call "$AJ" actionjurisdiction_get_jurisdiction --args 1 || true

ACTION_ID=$(next_free get_action 1)
step "6. jurisdiction read 3/5: get_action (first free id = $ACTION_ID)"
call "$AJ" actionjurisdiction_get_action --args 1 || true

step "7. jurisdiction read 4/5: has_approved + is_authorized_for (false-path)"
call "$AJ" actionjurisdiction_has_approved --args 1 1 "$RABBY" || true
call "$AJ" actionjurisdiction_is_authorized_for --args 1 aa bb cc dd ee || true
echo "note: is_authorized_for's true-path cannot be read through this CLI version"
echo "      (gen_call RLP bug with >=4 raw 64-hex args). Step 16's execute calls"
echo "      the same function on-chain and only succeeds when it returns true."

step "8. write: create_jurisdiction (min_distinct=2 so a revoke is possible)"
JURISDICTION_ID=$(next_free get_jurisdiction 1)
write "$AJ" actionjurisdiction_create_jurisdiction --args "Smoke jurisdiction" "Covers every entrypoint of this deployment." 2 true
echo "jurisdiction_id=$JURISDICTION_ID"

step "9. write: add_dimension x2 + add_approver x2"
write "$AJ" actionjurisdiction_add_dimension --args "$JURISDICTION_ID" money "Touches spending, transfers, and amounts." 1
write "$AJ" actionjurisdiction_add_dimension --args "$JURISDICTION_ID" security "Touches credentials, access, and privileged systems." 1
write "$AJ" actionjurisdiction_add_approver --args "$JURISDICTION_ID" 1 "$RABBY"
write "$AJ" actionjurisdiction_add_approver --args "$JURISDICTION_ID" 1 "$MAIN"
write "$AJ" actionjurisdiction_add_approver --args "$JURISDICTION_ID" 2 "$RABBY"
write "$AJ" actionjurisdiction_add_approver --args "$JURISDICTION_ID" 2 "$MAIN"
call "$AJ" actionjurisdiction_get_jurisdiction --args "$JURISDICTION_ID"

step "10. write: seal_jurisdiction"
write "$AJ" actionjurisdiction_seal_jurisdiction --args "$JURISDICTION_ID"

step "11. write: open_action"
ACTION_ID=$(next_free get_action 1)
write "$AJ" actionjurisdiction_open_action --args "$JURISDICTION_ID" "$CTX" "$AH_NEW" \
  "Move 100 GL out of the treasury (money) and rotate the admin API credentials (security)."

step "12. write: classify_action (leader LLM, asynchronous)"
for attempt in 1 2 3; do
  write "$AJ" actionjurisdiction_classify_action --args "$ACTION_ID"
  status=0
  for p in $(seq 1 12); do
    status=$(action_field "$ACTION_ID" status || echo 0)
    echo "action $ACTION_ID status=$status (poll $p/12)"
    [[ "$status" == 1 || "$status" == 3 || "$status" == 4 ]] && break
    sleep 10
  done
  if [[ "$status" == 1 ]]; then
    break
  fi
  if [[ "$attempt" == 3 ]]; then
    echo "classification never reached AWAITING_APPROVALS (status=$status); aborting" >&2
    exit 1
  fi
  echo "classification returned status=$status; opening a fresh action"
  AH_NEW=$(python3 -c "import hashlib,time;print(hashlib.sha256(('smoke-retry-'+str(time.time_ns())).encode()).hexdigest())")
  ACTION_ID=$(next_free get_action 1)
  write "$AJ" actionjurisdiction_open_action --args "$JURISDICTION_ID" "$CTX" "$AH_NEW" \
    "Approve a 100 GL treasury transfer (money) and a credential rotation for privileged systems (security)."
done

MASK=$(action_field "$ACTION_ID" required_mask)
echo "required_mask=$MASK"
mapfile -t DIMS < <(python3 -c "
m = int('$MASK')
print('\n'.join(str(i) for i in range(1, 17) if m & (1 << (i - 1))))
")
if [[ ${#DIMS[@]} -eq 0 ]]; then
  echo "no dimension required; cannot exercise approve" >&2
  exit 1
fi
echo "required dimensions: ${DIMS[*]}"

step "13. approve -> revoke -> approve (revoke only works before authorization)"
write "$AJ" actionjurisdiction_approve --args "$ACTION_ID" "${DIMS[0]}"
write "$AJ" actionjurisdiction_revoke_approval --args "$ACTION_ID" "${DIMS[0]}"
write "$AJ" actionjurisdiction_approve --args "$ACTION_ID" "${DIMS[0]}"

step "14. second distinct approver (switch to main)"
genlayer account use main
for d in "${DIMS[@]}"; do
  status=$(action_field "$ACTION_ID" status)
  [[ "$status" == 1 ]] || break
  write "$AJ" actionjurisdiction_approve --args "$ACTION_ID" "$d"
done
genlayer account use rabby

status=$(action_field "$ACTION_ID" status)
echo "action $ACTION_ID status_name=$(action_field "$ACTION_ID" status_name)"
if [[ "$status" != 2 ]]; then
  echo "action did not reach AUTHORIZED (status=$status); gate execute would fail" >&2
  exit 1
fi

step "15. jurisdiction read 5/5: get_action (hashes for the gate)"
call "$AJ" actionjurisdiction_get_action --args "$ACTION_ID"
DESC_HASH=$(action_field "$ACTION_ID" description_hash)
COMMITMENT=$(action_field "$ACTION_ID" action_commitment)
JURISDICTION_HASH=$(action_field "$ACTION_ID" jurisdiction_hash)
echo "desc=$DESC_HASH"
echo "commitment=$COMMITMENT"
echo "jurisdiction_hash=$JURISDICTION_HASH"

step "16. write: gate execute"
write "$AG" action_gate_execute --args "$ACTION_ID" "$AH_NEW" "$DESC_HASH" "$COMMITMENT" "$JURISDICTION_HASH"

step "17. gate reads confirm the execution"
call "$AG" action_gate_was_executed --args "$AH_NEW"
call "$AG" action_gate_get_execution --args "$AH_NEW"

step "18. negative reads"
call "$AG" action_gate_was_executed --args "$(python3 -c "print('f'*64)")"
call "$AG" action_gate_get_execution --args "$(python3 -c "print('f'*64)")" || true
call "$AJ" actionjurisdiction_is_authorized_for --args "$ACTION_ID" "$CTX" "$AH_NEW" aa bb cc || true

step "19. cancel_action on a fresh pending action"
CANCEL_ID=$(next_free get_action 1)
write "$AJ" actionjurisdiction_open_action --args "$JURISDICTION_ID" "$CTX" "$AH_CANCEL" "Routine key rotation, cancelled for this smoke test."
write "$AJ" actionjurisdiction_cancel_action --args "$CANCEL_ID"
call "$AJ" actionjurisdiction_get_action --args "$CANCEL_ID"

step "20. coverage check: every public method of both contracts"
fetch_schema "$AJ" "$TMP/schema_AJ2.txt" || cp "$TMP/schema_AJ.txt" "$TMP/schema_AJ2.txt"
fetch_schema "$AG" "$TMP/schema_AG2.txt" || cp "$TMP/schema_AG.txt" "$TMP/schema_AG2.txt"
cat "$TMP/schema_AJ2.txt" "$TMP/schema_AG2.txt" >"$TMP/schema_all.txt"

python3 - "$TMP/schema_all.txt" "${EXERCISED[@]}" <<'PY'
import re, sys

text = open(sys.argv[1]).read()
seen = set(sys.argv[2:])

methods, current = [], None
for line in text.splitlines():
    m = re.match(r"^    ([a-z_]+): \{", line)
    if m:
        current = m.group(1)
        methods.append([current, None])
    r = re.search(r"readonly: (true|false)", line)
    if r and current:
        methods[-1][1] = r.group(1) == "true"
        current = None

pairs = [tuple(m) for m in methods if m[1] is not None]
missing = [(n, ro) for n, ro in pairs if n not in seen]
extra = sorted(seen - {n for n, _ in pairs})

print(f"public methods on chain: {len(pairs)}")
print(f"exercised by this script: {len(pairs) - len(missing)}")
for name, ro in pairs:
    kind = "read " if ro else "write"
    flag = "OK  " if name in seen else "MISS"
    print(f"  {flag} {kind} {name}")
if extra:
    print(f"  note: called but not in schema: {', '.join(extra)}")
print("RESULT:", "ALL METHODS COVERED" if not missing else f"MISSING {[n for n, _ in missing]}")
sys.exit(1 if missing else 0)
PY
