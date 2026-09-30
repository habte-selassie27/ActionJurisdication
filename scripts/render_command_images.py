#!/usr/bin/env python3
"""Render each suite command + its result to a standalone PNG.

Reads artifacts/command-images/index.json, emits one HTML card per command,
screenshots it with headless Chrome, then trims the trailing page background
with Pillow. If the card was clipped by the viewport it retries taller.

Writes produce ~700 lines of consensus detail, so each write card carries a
short parsed digest and the raw dump is elided in the middle (the complete
capture always stays in artifacts/command-images/raw/<seq>.txt).
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

# NOT artifacts/ — `gltest` clears that directory on every pytest run.
OUT = Path("evidence/command-images")
HTML_DIR = OUT / "html"
PNG_DIR = OUT / "png"
RAW = OUT / "raw"

PAGE_BG = (13, 17, 23)  # #0d1117
WIDTH = 1400
KEEP_HEAD = 55
KEEP_TAIL = 55

GROUP_COLOR = {
    "Setup": "#6e7681",
    "ActionGate · read": "#a371f7",
    "ActionJurisdiction · read": "#58a6ff",
    "ActionJurisdiction · write": "#f0883e",
    "ActionGate · write": "#d29922",
}

CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: #0d1117;
  font-family: "DejaVu Sans Mono", "Liberation Mono", Menlo, Consolas, monospace;
  -webkit-font-smoothing: antialiased;
}
.card {
  margin: 28px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 14px;
  padding: 26px 30px 24px;
}
.hdr { display: flex; align-items: center; gap: 12px; }
.seq {
  background: #21262d; color: #58a6ff; border: 1px solid #30363d;
  border-radius: 7px; padding: 5px 11px; font-size: 15px; font-weight: 700;
}
.group {
  border-radius: 999px; padding: 5px 13px; font-size: 13px;
  color: #0d1117; font-weight: 700; letter-spacing: .3px;
}
.status {
  margin-left: auto; border-radius: 999px; padding: 5px 14px;
  font-size: 13px; font-weight: 700; letter-spacing: .5px;
}
.status.success { background: #1b4721; color: #3fb950; border: 1px solid #2ea043; }
.status.error   { background: #4b1418; color: #f85149; border: 1px solid #da3633; }
.status.unknown { background: #2b2300; color: #d29922; border: 1px solid #9e6a03; }
.title { color: #e6edf3; font-size: 21px; font-weight: 700; margin: 16px 0 4px; }
.sub { color: #8b949e; font-size: 13px; margin-bottom: 14px; }
.lbl {
  font-size: 11.5px; letter-spacing: 1.4px; text-transform: uppercase;
  color: #8b949e; margin: 16px 0 7px; font-weight: 700;
}
.lbl.blue { color: #58a6ff; }
.lbl.amber { color: #d29922; }
.lbl.grey { color: #6e7681; }
.lbl.green { color: #3fb950; }
pre {
  margin: 0; white-space: pre-wrap; word-break: break-all;
  background: #0d1117; border-radius: 8px; padding: 15px 18px;
  font-family: inherit;
}
.cmd { border-left: 3px solid #58a6ff; font-size: 15.5px; color: #e6edf3; line-height: 1.5; }
.cmd .p { color: #3fb950; font-weight: 700; }
.old { border-left: 3px solid #6e7681; font-size: 13.5px; color: #8b949e; line-height: 1.5; }
.env { border-left: 3px solid #6e7681; font-size: 13.5px; color: #a5d6ff; line-height: 1.55; }
.digest { border-left: 3px solid #3fb950; font-size: 14.5px; color: #e6edf3; line-height: 1.6; }
.digest .k { color: #8b949e; }
.digest .v { color: #7ee787; }
.digest .v.bad { color: #ff7b72; }
.digest .v.neut { color: #a5d6ff; }
.note {
  border-left: 3px solid #d29922; background: #1f1a0b; color: #e3b341;
  border-radius: 0 8px 8px 0; padding: 13px 18px; font-size: 14px; line-height: 1.55;
  white-space: pre-wrap; word-break: break-word;
}
.res { font-size: 14px; line-height: 1.5; color: #c9d1d9; }
.res.ok   { border-left: 3px solid #2ea043; }
.res.bad  { border-left: 3px solid #da3633; }
.res.neut { border-left: 3px solid #6e7681; }
.omit {
  color: #6e7681; background: #161b22; border-left: 3px dashed #30363d;
  padding: 9px 18px; font-size: 13px; white-space: pre-wrap; word-break: break-all;
}
.foot {
  margin-top: 18px; padding-top: 14px; border-top: 1px solid #21262d;
  color: #6e7681; font-size: 13px;
}
.foot b { color: #8b949e; }
"""

TRANSIENT = ("ENETUNREACH", "ETIMEDOUT", "ECONNRESET", "fetch failed", "RLP string")


def is_write(r: dict) -> bool:
    return r["cmd"].strip().startswith("genlayer write")


def classify(r: dict) -> tuple[str, str]:
    """Return (css_status, pill_label).

    A GenLayer write prints "Write operation successfully executed" whenever the
    transaction is accepted, even when the contract reverted. The contract-level
    truth is `execution_result` in the consensus payload: unanimous ERROR means
    the contract rejected the call.
    """
    out = r["output"]
    if is_write(r):
        results = re.findall(r"execution_result: '(\w+)'", out)
        if r["exit_code"] != 0 or not out.strip():
            return "error", "ERROR"
        if "SUCCESS" in results:
            return "success", "CONTRACT EXECUTED"
        if results and all(x == "ERROR" for x in results):
            return "error", "CONTRACT REVERTED"
        return "unknown", "NO MARKER"

    if "✖" in out or r["exit_code"] != 0 or any(m in out for m in TRANSIENT):
        return "error", "ERROR"
    if "successfully executed" in out or "✔" in out:
        return "success", "SUCCESS"
    if r["exit_code"] == 0 and out.strip():
        return "success", "SUCCESS"
    return "unknown", "NO MARKER"


def digest_html(r: dict) -> str:
    """Parsed one-screen summary of a write's consensus result."""
    out = r["output"]
    if not is_write(r) or not out.strip():
        return ""

    tx = re.search(r"hash: '(0x[0-9a-fA-F]+)'", out)
    if not tx:
        tx = re.search(r"Write Transaction Hash:\n(0x[0-9a-fA-F]+)", out)
    method = re.search(r'"method":"(\w+)"', out)
    calldata = re.search(r"readable: '(.*?)'", out, re.S)
    status = re.search(r"\n  status: (\d+)", out)
    result = re.search(r"\n  result: (\d+)", out)
    status_name = re.findall(r"status_name: '(\w+)'", out)
    execs = re.findall(r"execution_result: '(\w+)'", out)

    if execs and all(x == "ERROR" for x in execs):
        verdict, cls = "REVERTED — contract rejected the call", "bad"
    elif "SUCCESS" in execs:
        verdict, cls = "executed successfully", ""
    else:
        verdict, cls = "n/a", "neut"

    rows = [
        ("transaction", tx.group(1) if tx else "n/a", "neut"),
        ("method", method.group(1) if method else "n/a", ""),
        ("calldata", calldata.group(1).strip() if calldata else "n/a", "neut"),
        ("consensus status", (status_name[-1] if status_name else "n/a")
         + (f"  (status {status.group(1)}, result {result.group(1)})"
            if status and result else ""), "neut"),
        ("execution_result", "  ".join(execs) if execs else "n/a", cls),
        ("contract verdict", verdict, cls),
    ]
    body = "".join(
        f"<div><span class='k'>{html.escape(k)}:</span> "
        f"<span class='v {c}'>{html.escape(v)}</span></div>"
        for k, v, c in rows
    )
    return f"<div class='lbl green'>result digest</div><pre class='digest'>{body}</pre>"


def elide(out: str) -> str:
    """Trim the middle of a very long dump, always pointing at the raw capture."""
    lines = out.rstrip("\n").split("\n")
    if len(lines) <= KEEP_HEAD + KEEP_TAIL + 10:
        return "\n".join(lines)
    hidden = len(lines) - KEEP_HEAD - KEEP_TAIL
    marker = (f"…  {hidden} lines omitted — full capture: "
              f"evidence/command-images/raw/<seq>.txt  …")
    return "\n".join(lines[:KEEP_HEAD] + [marker] + lines[-KEEP_TAIL:])


def build_html(r: dict, status: str, label: str) -> str:
    p: list[str] = []
    p.append(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>")
    p.append("<div class='card'>")

    p.append("<div class='hdr'>")
    p.append(f"<span class='seq'>{html.escape(r['seq'])}</span>")
    gc = GROUP_COLOR.get(r["group"], "#6e7681")
    p.append(f"<span class='group' style='background:{gc}'>{html.escape(r['group'])}</span>")
    p.append(f"<span class='status {status}'>{html.escape(label)}</span>")
    p.append("</div>")

    p.append(f"<div class='title'>{html.escape(r['title'])}</div>")
    p.append("<div class='sub'>genlayer 0.39.2 · studionet · chain id 61999 · "
             "account rabby (0x5B36…4c89)</div>")

    if r.get("orig"):
        p.append("<div class='lbl grey'>as pasted — method name corrected for the deployed build</div>")
        p.append(f"<pre class='old'>{html.escape(r['orig'])}</pre>")

    p.append("<div class='lbl blue'>command (exactly as executed)</div>")
    p.append(f"<pre class='cmd'><span class='p'>$ </span>{html.escape(r['cmd'])}</pre>")

    if r.get("env"):
        lines = "\n".join(f"{k}={v}" for k, v in r["env"].items())
        p.append("<div class='lbl grey'>environment</div>")
        p.append(f"<pre class='env'>{html.escape(lines)}</pre>")

    if r.get("note"):
        p.append("<div class='lbl amber'>note</div>")
        p.append(f"<div class='note'>{html.escape(r['note'])}</div>")

    p.append(digest_html(r))

    p.append("<div class='lbl'>raw output</div>")
    res_cls = {"success": "ok", "error": "bad", "unknown": "neut"}[status]
    body = elide(r["output"].rstrip("\n")) or "(no output)"
    p.append(f"<pre class='res {res_cls}'>{html.escape(body)}</pre>")

    p.append(
        f"<div class='foot'><b>exit</b> {r['exit_code']} &nbsp;·&nbsp; "
        f"<b>duration</b> {r['duration_s']}s &nbsp;·&nbsp; "
        f"<b>started</b> {html.escape(r['started'])} &nbsp;·&nbsp; "
        f"<b>rpc</b> https://studio.genlayer.com/api</div>"
    )
    p.append("</div></body></html>")
    return "".join(p)


def wrapped_lines(text: str, chars: int) -> int:
    total = 0
    for line in text.split("\n"):
        total += max(1, math.ceil(len(line) / chars)) if line else 1
    return total


def estimate_height(r: dict, body: str) -> int:
    h = 170
    if r.get("orig"):
        h += 30 + wrapped_lines(r["orig"], 140) * 22 + 16
    h += 30 + wrapped_lines(r["cmd"], 125) * 26 + 16
    if r.get("env"):
        h += 30 + len(r["env"]) * 23 + 16
    if r.get("note"):
        h += 30 + wrapped_lines(r["note"], 130) * 23 + 16
    if is_write(r) and r["output"].strip():
        h += 30 + 6 * 26 + 16
    h += 30 + wrapped_lines(body, 145) * 22 + 50
    return h + 200


def screenshot(src: Path, dst: Path, height: int) -> bool:
    cmd = [
        "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        "--virtual-time-budget=3000",
        f"--window-size={WIDTH},{height}",
        f"--screenshot={dst}", f"file://{src.resolve()}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not dst.exists():
        print(f"    chrome failed: {(proc.stderr or proc.stdout)[-400:]}", file=sys.stderr)
        return False
    return True


def _row_has_content(im, y: int) -> bool:
    w, _ = im.size
    return any(
        sum(abs(a - b) for a, b in zip(im.getpixel((x, y)), PAGE_BG)) > 18
        for x in range(0, w, 13)
    )


def was_clipped(path: Path) -> bool:
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        return _row_has_content(rgb, rgb.size[1] - 1)


def trim(path: Path) -> None:
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        bottom = h
        for y in range(h - 1, -1, -1):
            if _row_has_content(im, y):
                bottom = y
                break
        top = 0
        for y in range(0, h):
            if _row_has_content(im, y):
                top = y
                break
        im.crop((0, max(0, top - 6), w, min(h, bottom + 40))).save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="render a single seq, e.g. 07")
    args = ap.parse_args()

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)

    data = json.loads((OUT / "index.json").read_text())
    results = data["results"]
    if args.only:
        results = [r for r in results if r["seq"] == args.only]

    failures = []
    for r in results:
        status, label = classify(r)
        body = elide(r["output"].rstrip("\n")) or "(no output)"
        hp = HTML_DIR / f"{r['seq']}.html"
        hp.write_text(build_html(r, status, label))
        dst = PNG_DIR / f"{r['seq']}.png"

        height = estimate_height(r, body)
        ok = False
        for _ in range(5):
            if screenshot(hp, dst, height):
                if not was_clipped(dst):
                    ok = True
                    break
                print(f"    clipped at {height}px, retrying", file=sys.stderr)
            height += 900
        if not ok:
            failures.append(r["seq"])
            continue
        trim(dst)
        print(f"  {r['seq']}.png  {label}", flush=True)

    if failures:
        print(f"FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\n{len(results)} images -> {PNG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
