#!/usr/bin/env python3
"""Run the ActionJurisdication / ActionGate read+write suite against Studionet.

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

OUT = Path("artifacts/command-images")
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
     "genlayer call $AJ actionjurisdiction_get_matrix --args 1", None, 120),
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
     "genlayer write $AJ actionjurisdiction_seal_matrix --args 1", None, 300),
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


def preamble() -> str:
    return "; ".join(f"export {k}={v}" for k, v in ENV.items())


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    preamble_txt = preamble()
    results = []

    for i, (group, title, cmd, orig, note, timeout) in enumerate(COMMANDS, start=1):
        seq = f"{i:02d}"
        print(f"[{seq}/{len(COMMANDS)}] {title}", flush=True)
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        t0 = time.time()
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
            output = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            output += f"\n[runner] TIMED OUT after {timeout}s\n"
            exit_code = -1
            timed_out = True
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
        print(f"        -> {status} ({duration}s, exit={exit_code})", flush=True)

    (OUT / "index.json").write_text(json.dumps({
        "preamble": ENV,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }, indent=2))
    ok = sum(1 for r in results if r["status"] == "success")
    print(f"\nDone: {ok}/{len(results)} successful")
    return 0


if __name__ == "__main__":
    sys.exit(main())
