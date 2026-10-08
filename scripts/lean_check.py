#!/usr/bin/env python3
"""Check every recorded certificate in Lean 4.

For each record with a certificate and no Lean result yet (new submissions
and, on a manual run, older records), this renders the problem's Lean file,
runs `lean` on it, and stores the result in the record:

    "lean": {"status": "verified" | "failed", "method": "kernel" | "native",
             "toolchain": ..., "axioms": [...], "statement": ..., "checked_at": ...}

The kernel proof is tried first; if it runs out of time, the compiled check
(`native_decide`) is used and labelled as such. A refuted certificate stays
refuted: only timeouts fall back. When `lean` is not installed the records are
left untouched, so local runs and tests stay offline.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_board  # noqa: E402
from mathathome import lean, problems  # noqa: E402

OUTCOME = ROOT / ".hub-outcome.json"
KERNEL_TIMEOUT = 300
NATIVE_TIMEOUT = 300


def run_lean(source: str, timeout: int) -> tuple[int, str] | None:
  """Run Lean on one file; None on timeout."""
  with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "Certificate.lean"
    path.write_text(source, encoding="utf-8")
    try:
      done = subprocess.run(["lean", str(path)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
      return None
    return done.returncode, done.stdout + done.stderr


def check(kind: str, certificate: dict, runner=run_lean) -> dict | None:
  rendered = lean.render(kind, certificate)
  if rendered is None:
    return None
  attempt = runner(rendered["source"], KERNEL_TIMEOUT if rendered["method"] == "kernel" else NATIVE_TIMEOUT)
  refuted = attempt is not None and attempt[0] != 0 and "is false" in attempt[1]
  if rendered["method"] == "kernel" and (attempt is None or (attempt[0] != 0 and not refuted)):
    # Out of time or kernel resources, not a refutation: use the compiled check.
    rendered = lean.render(kind, certificate, prefer_native=True)
    attempt = runner(rendered["source"], NATIVE_TIMEOUT)
  if attempt is None:
    result = {"status": "failed", "method": rendered["method"], "detail": "Lean timed out."}
  else:
    result = lean.interpret(attempt[0], attempt[1], rendered["method"])
  result.update({
    "toolchain": rendered["toolchain"],
    "statement": rendered["statement"],
    "consequence": rendered["consequence"],
    "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
  })
  return result


def pending(root: Path):
  for path in sorted((root / "data" / "records").glob("*/*.json")):
    try:
      record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
      continue
    if "lean" in record or not record.get("certificate_sha256"):
      continue
    cert_path = root / "data" / "certificates" / f"{record['certificate_sha256']}.json"
    if cert_path.is_file():
      yield path, record, json.loads(cert_path.read_text(encoding="utf-8"))


def main(root: Path = ROOT, runner=run_lean) -> int:
  if runner is run_lean and shutil.which("lean") is None:
    print("lean is not installed; skipping Lean checks")
    return 0
  checked = []
  for path, record, certificate in pending(root):
    problem = problems().get(record["shift"]["problem_id"])
    kind = (problem or {}).get("verifier", {}).get("kind")
    result = check(kind, certificate, runner) if kind else None
    if result is None:
      continue
    record["lean"] = result
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    checked.append((record, result))
    print(record["shift"]["id"], lean.summary(result))
  if checked:
    build_board.build(root)
  if OUTCOME.exists():
    outcome = json.loads(OUTCOME.read_text(encoding="utf-8"))
    for record, result in checked:
      if outcome.get("issue") == record.get("issue") and outcome.get("action") == "record":
        line = lean.summary(result)
        if result["status"] == "verified":
          outcome["message"] += f" {line}: Lean {result['toolchain'].split(':')[-1]} proved that {result['statement']}."
          outcome["labels"] = list(dict.fromkeys((outcome.get("labels") or []) + ["lean-verified"]))
        else:
          outcome["message"] += f" {line}: {result.get('detail', 'the Lean check did not pass')}"
    OUTCOME.write_text(json.dumps(outcome), encoding="utf-8")
  return 0


if __name__ == "__main__":
  sys.exit(main())
