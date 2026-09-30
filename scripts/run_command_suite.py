#!/usr/bin/env python3
"""Run the ActionJurisdiction / ActionGate read+write suite against Studionet.

Every command is executed through `bash -c` with a small environment preamble,
so the command string shown in the report is byte-for-byte the string that ran.

Method names are the *deployed* (unprefixed) names. The pasted commands used
prefixed names (actionjurisdiction_*, action_gate_*) which the deployments do
not expose; `orig` records what was pasted so the report can show the
translation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# NOT artifacts/ — `gltest` clears that directory on every pytest run and would
# delete the captured evidence.
OUT = Path("evidence/command-images")
RAW = OUT / "raw"

ENV = {
    "AJ": "0xb1748CD74F52A85dcC1c4C57144BC24F44e7a871",
    "AG": "0xE2b921C8db13b9B2BdB7De0de4990Ff3Da6F807e",
    "CTX": "9d0b60fc4e8005409a78683d53aa781bf5ff69f431a8ca3079f5285857f46dca",
    # Sourced from `get_action 1` — unset in the original paste.
    "DESC_HASH": "d2dc0ab8e40354a8b0d95e0d9b4240261b3dac0db6dd92f14894ebfb8b4ee3d5",
    "COMMITMENT": "5933e947419f5b7eb97a216631601463628225cdaa961a23e732a47da39027f3",
    "MATRIX_HASH": "990eb237c95c6819d354573733cc5596d2e172d3f723b308c6d4993eb642a447",
    "AH": "2222222222222222222222222222222222222222222222222222222222222222",
    "AH2": "3333333333333333333333333333333333333333333333333333333333333333",
}

SETUP = "Setup"
GATE_READ = "ActionGate · read"
AJ_READ = "ActionJurisdiction · read"
AJ_WRITE = "ActionJurisdiction · write"
GATE_WRITE = "ActionGate · write"

# (group, title, command-as-run, command-as-pasted-or-None, note-or-None, timeout)
COMMANDS = [
    (SETUP, "List accounts", "genlayer account list", None, None, 60),
    (SETUP, "Show the rabby account", "genlayer account show --account rabby", None, None, 60),
    (SETUP, "Select the rabby account", "genlayer account use rabby", None, None, 60),
    (
        SETUP,
        "Unlock the rabby account",
        "genlayer account unlock --account rabby",
        None,
        "Prompts for a password on the terminal. Run here with no stdin, so the "
        "prompt cannot be answered — rabby is already unlocked.",
        40,
    ),
    (SETUP, "Select the studionet network", "genlayer network set studionet", None, None, 60),
    (SETUP, "Show network details", "genlayer network info", None, None, 90),

    (GATE_READ, "was_executed — already-executed action hash",
     'genlayer call $AG was_executed --args "$AH"',
     'genlayer call $AG action_gate_was_executed --args "2222…"', None, 120),
    (GATE_READ, "get_execution — already-executed action hash",
     'genlayer call $AG get_execution --args "$AH"',
     'genlayer call $AG action_gate_get_execution --args "2222…"', None, 120),

    (AJ_READ, "get_constants", "genlayer call $AJ get_constants",
     "genlayer call $AJ actionjurisdiction_get_constants", None, 120),
    (AJ_READ, "get_matrix — matrix 1 (sealed)", "genlayer call $AJ get_matrix --args 1",
     "genlayer call $AJ actionjurisdiction_get_jurisdiction --args 1", None, 120),
    (AJ_READ, "get_action — action 1 (AUTHORIZED)", "genlayer call $AJ get_action --args 1",
     "genlayer call $AJ actionjurisdiction_get_action --args 1", None, 120),
    (AJ_READ, "has_approved — action 1, dimension 1",
     'genlayer call $AJ has_approved --args 1 1 "0xac3ac69dc0bde389256dd6748c75817ead9286d9"',
     'genlayer call $AJ actionjurisdiction_has_approved --args 1 1 "0xac3ac69dc0bde389256dd6748c75817ead9286d9"',
     None, 120),
    (AJ_READ, "is_authorized_for — action 1 with the pinned hashes",
     'genlayer call $AJ is_authorized_for --args 1 $CTX "$AH" "$DESC_HASH" "$COMMITMENT" "$MATRIX_HASH"',
     'genlayer call $AJ actionjurisdiction_is_authorized_for --args 1 $CTX "2222…" "$DESC_HASH" "$COMMITMENT" "$MATRIX_HASH"',
     "$DESC_HASH / $COMMITMENT / $MATRIX_HASH were unset in the paste; they are the "
     "values read back from action 1 by get_action above.", 120),

    (AJ_WRITE, "create_matrix — “Matrix 2”",
     'genlayer write $AJ create_matrix --args "Matrix 2" "purpose" 2 false',
     'genlayer write $AJ actionjurisdication_create_matrix --args "Matrix 2" "purpose" 2 false',
     None, 300),
    (AJ_WRITE, "add_dimension — money, on sealed matrix 1",
     'genlayer write $AJ add_dimension --args 1 "money" "touches money" 1',
     'genlayer write $AJ actionjurisdiction_add_dimension --args 1 "money" "touches money" 1',
     None, 300),
    (AJ_WRITE, "add_dimension — security, on sealed matrix 1",
     'genlayer write $AJ add_dimension --args 1 "security" "touches security" 1',
     'genlayer write $AJ actionjurisdiction_add_dimension --args 1 "security" "touches security" 1',
     None, 300),
    (AJ_WRITE, "add_approver — 0xac3ac6… on sealed matrix 1",
     'genlayer write $AJ add_approver --args 1 1 "0xac3ac69dc0bde389256dd6748c75817ead9286d9"',
     'genlayer write $AJ actionjurisdiction_add_approver --args 1 1 "0xac3ac69dc0bde389256dd6748c75817ead9286d9"',
     None, 300),
    (AJ_WRITE, "add_approver — 0xa7eeae… on sealed matrix 1",
     'genlayer write $AJ add_approver --args 1 1 "0xa7eeae0e93793e3146cb14b0700251b8b0ebadfb"',
     'genlayer write $AJ actionjurisdiction_add_approver --args 1 1 "0xa7eeae0e93793e3146cb14b0700251b8b0ebadfb"',
     None, 300),
    (AJ_WRITE, "seal_matrix — matrix 1 (already sealed)",
     "genlayer write $AJ seal_matrix --args 1",
     "genlayer write $AJ actionjurisdiction_seal_jurisdiction --args 1", None, 300),
    (AJ_WRITE, "open_action — action hash 3333… on matrix 1",
     'genlayer write $AJ open_action --args 1 $CTX "$AH2" "description text"',
     'genlayer write $AJ actionjurisdiction_open_action --args 1 $CTX "3333…" "description text"',
     "The pasted “3333...” was truncated; expanded to the full 64-character hash "
     "3333…3333 (already registered by action 2).", 300),
    (AJ_WRITE, "classify_action — action 1 (leader LLM, async)",
     "genlayer write $AJ classify_action --args 1",
     "genlayer write $AJ actionjurisdiction_classify_action --args 1", None, 300),
    (AJ_WRITE, "approve — action 1, dimension 1",
     "genlayer write $AJ approve --args 1 1",
     "genlayer write $AJ actionjurisdiction_approve --args 1 1", None, 300),
    (AJ_WRITE, "revoke_approval — action 1, dimension 1",
     "genlayer write $AJ revoke_approval --args 1 1",
     "genlayer write $AJ actionjurisdiction_revoke_approval --args 1 1", None, 300),
    (AJ_WRITE, "cancel_action — action 4",
     "genlayer write $AJ cancel_action --args 4",
     "genlayer write $AJ actionjurisdiction_cancel_action --args 4", None, 300),

    (GATE_WRITE, "execute — action 1, exact hashes",
     'genlayer write $AG execute --args 1 "$AH" "$DESC_HASH" "$COMMITMENT" "$MATRIX_HASH"',
     'genlayer write $AG action_gate_execute --args 1 "2222…" "$DESC_HASH" "$COMMITMENT" "$MATRIX_HASH"',
     None, 300),
]


# Per-command explanations rendered onto the image. Kept in code, not in the
# generated index.json, so a re-run reproduces them.
NOTES = {
    "13": ("$DESC_HASH / $COMMITMENT / $MATRIX_HASH were unset in the paste - sourced here from the "
           "get_action readback above.\n"
           "Reproducible CLI/node bug: five BARE 64-char hex strings are sent as ASCII, the calldata "
           "payload crosses the single-byte RLP length boundary and the node rejects it "
           "(_InternalRpcError: RLP string ends with 332 superfluous bytes). Verified separately: "
           "0x-prefixed hashes, or shorter arguments, both return false."),
    "14": ("SUCCEEDED - returned matrix_id 4. matrix_id 2 is a throwaway latency probe and matrix_id 3 "
           "is the earlier 'Matrix 2' from the first run, so this create_matrix is numbered 4."),
    "15": "REJECTED: matrix 1 is already SEALED, and a sealed matrix is immutable.",
    "16": "REJECTED: matrix 1 is already SEALED, and a sealed matrix is immutable.",
    "17": "REJECTED: matrix 1 is already SEALED, so the approver set is frozen.",
    "18": "REJECTED: matrix 1 is already SEALED, so the approver set is frozen.",
    "19": "REJECTED: matrix 1 status is already 1 (SEALED).",
    "20": ("REJECTED: action hash 3333...3333 is already registered by action 2 - an exact action hash "
           "can only be registered once. The pasted '3333...' was truncated and was expanded to the "
           "full 64-character hash."),
    "21": "REJECTED: action 1 is already AUTHORIZED (status 2); classify_action only runs on PENDING actions.",
    "22": "REJECTED: action 1 is already AUTHORIZED - approvals cannot change after authorization.",
    "23": "REJECTED: action 1 is already AUTHORIZED - revocation is only allowed while pending.",
    "24": "REJECTED: action 4 does not exist (only actions 1 and 2 are registered).",
    "25": ("REJECTED: ActionGate already executed action hash 2222...2222 - see read #07, where "
           "was_executed returns true."),
}


def preamble() -> str:
    return "; ".join(f"export {k}={v}" for k, v in ENV.items())


def load_existing() -> dict:
    """Prior results keyed by seq, so an interrupted run resumes."""
    path = OUT / "index.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {r["seq"]: r for r in data.get("results", [])}


def save(results: list) -> None:
    (OUT / "index.json").write_text(json.dumps({
        "preamble": ENV,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }, indent=2))


TRANSIENT = (
    "ENETUNREACH", "ETIMEDOUT", "ECONNRESET", "EAI_AGAIN", "EPIPE",
    "fetch failed", "socket hang up", "network timeout", "Gateway Time-out",
)


def is_transient(out: str) -> bool:
    return any(m in out for m in TRANSIENT)


def was_submitted(out: str) -> bool:
    """Evidence the transaction already reached the network — never retry those."""
    return "hash:" in out or "status_name" in out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=len(COMMANDS))
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    (OUT).mkdir(parents=True, exist_ok=True)
    preamble_txt = preamble()
    done = load_existing()
    results: list = []

    for i, (group, title, cmd, orig, note, timeout) in enumerate(COMMANDS, start=1):
        seq = f"{i:02d}"
        if seq in done:
            results.append(done[seq])
            continue
        if not (args.start <= i <= args.end):
            continue
        print(f"[{seq}/{len(COMMANDS)}] {title}", flush=True)
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        t0 = time.time()
        is_write = cmd.strip().startswith("genlayer write")
        max_attempts = 2 if is_write else 4
        output = ""
        exit_code = 0
        timed_out = False
        for attempt in range(1, max_attempts + 1):
            try:
                proc = subprocess.run(
                    ["bash", "-c", f"{preamble_txt}; {cmd}"],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    stdin=subprocess.DEVNULL,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                exit_code = proc.returncode
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                raw_out = exc.stdout or b""
                output = raw_out.decode(errors="replace") if isinstance(raw_out, bytes) else raw_out
                output += f"\n[runner] TIMED OUT after {timeout}s\n"
                exit_code = -1
                timed_out = True
            retryable = is_transient(output) and not (is_write and was_submitted(output))
            if not retryable or attempt == max_attempts:
                break
            print(f"        transient network error -> retry {attempt + 1}/{max_attempts}", flush=True)
            time.sleep(6)
        duration = round(time.time() - t0, 1)

        exec_error = "execution_result: 'ERROR'" in output or "execution_result: \"ERROR\"" in output
        if exec_error or timed_out or "✖" in output or exit_code != 0:
            status = "error"
        elif "successfully executed" in output:
            status = "success"
        else:
            status = "unknown"

        (RAW / f"{seq}.txt").write_text(output)
        used_env = sorted({k for k in ENV if f"${k}" in cmd or f"${{{k}}}" in cmd})
        results.append({
            "seq": seq,
            "group": group,
            "title": title,
            "cmd": cmd,
            "orig": orig,
            "note": note,
            "env": {k: ENV[k] for k in used_env},
            "exit_code": exit_code,
            "duration_s": duration,
            "started": started,
            "status": status,
            "output_file": f"raw/{seq}.txt",
            "output": output,
        })
        if seq in NOTES:
            results[-1]["note"] = NOTES[seq]
        results.sort(key=lambda r: r["seq"])
        save(results)  # checkpoint after every command
        print(f"        -> {status} ({duration}s, exit={exit_code})", flush=True)

    results.sort(key=lambda r: r["seq"])
    save(results)
    ok = sum(1 for r in results if r["status"] == "success")
    print(f"\nDone: {ok}/{len(results)} recorded, {len(results)}/{len(COMMANDS)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
