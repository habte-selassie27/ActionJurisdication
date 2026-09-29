#!/usr/bin/env bash
set -euo pipefail

# Exercises every public method of both contracts: 7 reads + 10 writes = 17.
#   ActionJurisdiction ($AJ): get_constants, get_matrix, get_action, has_approved,
#     is_authorized_for (reads) + create_matrix, add_dimension, add_approver,
#     seal_matrix, open_action, classify_action, approve, revoke_approval,
#     cancel_action (writes)
#   ActionGate ($AG): was_executed, get_execution (reads) + execute (write)
# Method names are UNPREFIXED because these deployments carry the pre-rename
# build. The current repo build uses actionjurisdication_* / action_gate_*.
# Step 20 diffs the exercised set against `genlayer schema` and fails if any
# public method was skipped.

export AJ=0xb1748CD74F52A85dcC1c4C57144BC24F44e7a871
export AG=0xE2b921C8db13b9B2BdB7De0de4990Ff3Da6F807e
export CTX=9d0b60fc4e8005409a78683d53aa781bf5ff69f431a8ca3079f5285857f46dca

RABBY=0x5B3661C576c7001e6d6279C67F3779705d334c89
MAIN=0x37cdbd86743e2b80486413e89ca4c70a58147889

AH_DONE=2222222222222222222222222222222222222222222222222222222222222222
AH_NEW=4444444444444444444444444444444444444444444444444444444444444444
AH_CANCEL=5555555555555555555555555555555555555555555555555555555555555555

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

step() { printf '\n========== %s\n' "$*"; }

EXERCISED=()

call() {
  EXERCISED+=("$2")
  genlayer call "$@"
}

write() {
  local out
  EXERCISED+=("$2")
  if ! out=$(genlayer write "$@" 2>&1); then
    echo "$out" | tail -25 >&2
    echo "WRITE REJECTED: $*" >&2
    exit 1
  fi
  if grep -q "execution_result: 'ERROR'" <<<"$out"; then
    echo "$out" | grep -A8 "execution_result: 'ERROR'" | head -30 >&2
    echo "CONTRACT EXECUTION FAILED: $*" >&2
    exit 1
  fi
  grep -E "^ +hash:|status_name|✔ Write" <<<"$out" || true
}

next_free() {
  local method=$1 n=$2
  while out=$(genlayer call "$AJ" "$method" --args "$n" 2>&1) &&
    grep -q "successfully executed" <<<"$out"; do
    n=$((n + 1))
  done
  echo "$n"
}

action_field() {
  genlayer call "$AJ" get_action --args "$1" 2>/dev/null |
    sed -n "s/^  $2: \(.*\)$/\1/p" | tr -d "'" | head -1
}

step "0. environment"
genlayer account list
genlayer account use rabby
genlayer network set studionet
genlayer network info

step "1. schema (readonly flags decide call vs write)"
genlayer schema "$AJ" >"$TMP/schema_AJ.txt"
genlayer schema "$AG" >"$TMP/schema_AG.txt"
grep -E "^ +[a-z_]+: \{|readonly" "$TMP/schema_AJ.txt" "$TMP/schema_AG.txt"

step "2. ActionGate read 1/2: was_executed (already-executed action)"
call "$AG" was_executed --args "$AH_DONE"

step "3. ActionGate read 2/2: get_execution"
call "$AG" get_execution --args "$AH_DONE"

step "4. jurisdiction read 1/5: get_constants"
call "$AJ" get_constants

MATRIX_ID=$(next_free get_matrix 1)
step "5. jurisdiction read 2/5: get_matrix (first free id = $MATRIX_ID)"
call "$AJ" get_matrix --args 1 || true

ACTION_ID=$(next_free get_action 1)
step "6. jurisdiction read 3/5: get_action (first free id = $ACTION_ID)"
call "$AJ" get_action --args 1 || true

step "7. jurisdiction read 4/5: has_approved + is_authorized_for (false-path)"
call "$AJ" has_approved --args 1 1 "$RABBY" || true
call "$AJ" is_authorized_for --args 1 aa bb cc dd ee || true
echo "note: is_authorized_for's true-path cannot be read through this CLI version"
echo "      (gen_call RLP bug with >=4 raw 64-hex args). Step 16's execute calls"
echo "      the same function on-chain and only succeeds when it returns true."

step "8. write: create_matrix (min_distinct=2 so a revoke is possible)"
MATRIX_ID=$(next_free get_matrix 1)
write "$AJ" create_matrix --args "Smoke matrix" "Covers every entrypoint of this deployment." 2 true
echo "matrix_id=$MATRIX_ID"

step "9. write: add_dimension x2 + add_approver x2"
write "$AJ" add_dimension --args "$MATRIX_ID" money "Touches spending, transfers, and amounts." 1
write "$AJ" add_dimension --args "$MATRIX_ID" security "Touches credentials, access, and privileged systems." 1
write "$AJ" add_approver --args "$MATRIX_ID" 1 "$RABBY"
write "$AJ" add_approver --args "$MATRIX_ID" 1 "$MAIN"
write "$AJ" add_approver --args "$MATRIX_ID" 2 "$RABBY"
write "$AJ" add_approver --args "$MATRIX_ID" 2 "$MAIN"
call "$AJ" get_matrix --args "$MATRIX_ID"

step "10. write: seal_matrix"
write "$AJ" seal_matrix --args "$MATRIX_ID"

step "11. write: open_action"
ACTION_ID=$(next_free get_action 1)
write "$AJ" open_action --args "$MATRIX_ID" "$CTX" "$AH_NEW" \
  "Move 100 GL out of the treasury (money) and rotate the admin API credentials (security)."

step "12. write: classify_action (leader LLM, asynchronous)"
for attempt in 1 2 3; do
  write "$AJ" classify_action --args "$ACTION_ID"
  status=$(action_field "$ACTION_ID" status)
  echo "action $ACTION_ID status=$status"
  if [[ "$status" == 1 ]]; then
    break
  fi
  if [[ "$attempt" == 3 ]]; then
    echo "classification never reached AWAITING_APPROVALS; aborting" >&2
    exit 1
  fi
  echo "classification returned $status; opening a fresh action"
  AH_NEW=$(python3 -c "import hashlib;print(hashlib.sha256(b'smoke-$attempt'.encode()).hexdigest())")
  ACTION_ID=$(next_free get_action 1)
  write "$AJ" open_action --args "$MATRIX_ID" "$CTX" "$AH_NEW" \
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
write "$AJ" approve --args "$ACTION_ID" "${DIMS[0]}"
write "$AJ" revoke_approval --args "$ACTION_ID" "${DIMS[0]}"
write "$AJ" approve --args "$ACTION_ID" "${DIMS[0]}"

step "14. second distinct approver (switch to main)"
genlayer account use main
for d in "${DIMS[@]}"; do
  status=$(action_field "$ACTION_ID" status)
  [[ "$status" == 1 ]] || break
  write "$AJ" approve --args "$ACTION_ID" "$d"
done
genlayer account use rabby

status=$(action_field "$ACTION_ID" status)
echo "action $ACTION_ID status_name=$(action_field "$ACTION_ID" status_name)"
if [[ "$status" != 2 ]]; then
  echo "action did not reach AUTHORIZED (status=$status); gate execute would fail" >&2
  exit 1
fi

step "15. jurisdiction read 5/5: get_action (hashes for the gate)"
call "$AJ" get_action --args "$ACTION_ID"
DESC_HASH=$(action_field "$ACTION_ID" description_hash)
COMMITMENT=$(action_field "$ACTION_ID" action_commitment)
MATRIX_HASH=$(action_field "$ACTION_ID" matrix_hash)
echo "desc=$DESC_HASH"
echo "commitment=$COMMITMENT"
echo "matrix=$MATRIX_HASH"

step "16. write: gate execute"
write "$AG" execute --args "$ACTION_ID" "$AH_NEW" "$DESC_HASH" "$COMMITMENT" "$MATRIX_HASH"

step "17. gate reads confirm the execution"
call "$AG" was_executed --args "$AH_NEW"
call "$AG" get_execution --args "$AH_NEW"

step "18. negative reads"
call "$AG" was_executed --args "$(python3 -c "print('f'*64)")"
call "$AG" get_execution --args "$(python3 -c "print('f'*64)")" || true
call "$AJ" is_authorized_for --args "$ACTION_ID" "$CTX" "$AH_NEW" aa bb cc || true

step "19. cancel_action on a fresh pending action"
CANCEL_ID=$(next_free get_action 1)
write "$AJ" open_action --args "$MATRIX_ID" "$CTX" "$AH_CANCEL" "Routine key rotation, cancelled for this smoke test."
write "$AJ" cancel_action --args "$CANCEL_ID"
call "$AJ" get_action --args "$CANCEL_ID"

step "20. coverage check: every public method of both contracts"
{
  genlayer schema "$AJ" 2>/dev/null
  genlayer schema "$AG" 2>/dev/null
} >"$TMP/schema_all.txt"

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
