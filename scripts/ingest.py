#!/usr/bin/env python3
"""Turn one GitHub issue into a Math@Home community record.

    python scripts/ingest.py process   # judge the triggering issue, write data
    python scripts/ingest.py notify    # reply on the issue (after data is pushed)

Everything in an issue is untrusted. The issue body is parsed as data only:
nothing in it is executed or interpolated into a shell. Certificates are
re-checked with the same checkers the app uses. The author is the issue's
GitHub account, so nobody can submit in someone else's name. A body that
looks like it contains a credential is blanked on GitHub and rejected, so a
mistake cannot stay public.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_board  # noqa: E402
from mathathome import points_rules, problems, scrub, submission, verify  # noqa: E402

OUTCOME = ROOT / ".hub-outcome.json"
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
DAILY_REPORTS = 12
MAX_TIME_MINUTES = 120


def now_iso() -> str:
  return datetime.now(UTC).isoformat(timespec="seconds")


def record_path(root: Path, login: str, shift_id: str) -> Path:
  return root / "data" / "records" / login.lower() / f"{shift_id}.json"


def existing_records(root: Path):
  folder = root / "data" / "records"
  if not folder.is_dir():
    return
  for path in sorted(folder.glob("*/*.json")):
    try:
      yield json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
      continue


def score(record: dict, root: Path) -> dict:
  rules = points_rules()
  tier = problems()[record["shift"]["problem_id"]]["tier"]
  day = record["recorded_at"][:10]
  same_day = sum(
    1 for item in existing_records(root)
    if item["login"].lower() == record["login"].lower() and item.get("recorded_at", "")[:10] == day
  )
  verdict = record["verdict"]
  result = {
    "valid": rules["certificate"],
    "side_record": rules["side_record_per_tier"] * tier,
    "record": rules["record_per_tier"] * tier,
  }.get(verdict, 0)
  if record.get("duplicate_certificate"):
    result = 0
  report_points = rules["report"] if same_day < DAILY_REPORTS else 0
  time_points = int(min(record["shift"]["minutes"], MAX_TIME_MINUTES) // rules["minutes_per_point"])
  return {"report": report_points, "time": time_points, "result": result, "total": report_points + time_points + result}


def process(issue: dict, root: Path, recorded_at: str | None = None) -> dict:
  """Judge one issue. Pure apart from reading existing records."""
  body = issue.get("body") or ""
  title = issue.get("title") or ""
  number = issue.get("number")
  if submission.MARKER not in body:
    return {"action": "ignore", "issue": number}
  user = issue.get("user") or {}
  login = user.get("login") or ""
  if user.get("type") == "Bot" or not LOGIN.match(login):
    return {"action": "ignore", "issue": number}
  if scrub.find_credentials(body) or scrub.find_credentials(title):
    return {
      "action": "redact",
      "issue": number,
      "message": (
        "This submission looked like it contained a credential (a key, token or password), "
        "so its text has been removed and it was not recorded. Please rotate that credential, "
        "then share the result again from the Math@Home app."
      ),
    }
  try:
    data = submission.validate(submission.parse(body), set(problems()))
  except submission.SubmissionError as exc:
    return {"action": "reject", "issue": number, "message": f"Not recorded: {exc}."}
  shift_id = data["shift"]["id"]
  if record_path(root, login, shift_id).exists():
    return {"action": "duplicate", "issue": number, "message": "This shift is already on the board."}

  problem = problems()[data["shift"]["problem_id"]]
  verdict, detail, value = "report", "Shift report recorded.", None
  duplicate_of = None
  if data["certificate"] is not None:
    for item in existing_records(root):
      if item.get("certificate_sha256") == data["certificate_sha256"]:
        duplicate_of = item["login"]
        break
    outcome = verify.check(problem, data["certificate"])
    verdict = {"record": "record", "side_record": "side_record", "valid": "valid", "unsupported": "unchecked"}.get(
      outcome["status"], "invalid",
    )
    detail, value = outcome["detail"], outcome.get("value")
  elif data["claim"] is not None:
    verdict, detail = "pending_review", "Claim recorded; it needs an independent replay and review."
    value = data["claim"]["value"] or None
  elif data["certificate_sha256"]:
    verdict, detail = "unchecked", "The certificate was too large to attach, so the hub could not check it."

  record = {
    "version": 1,
    "login": login,
    "credit_name": data["credit_name"],
    "issue": number,
    "issue_url": issue.get("html_url"),
    "submitted_at": issue.get("created_at"),
    "recorded_at": recorded_at or now_iso(),
    "app_version": data["app_version"],
    "shift": data["shift"],
    "report": data["report"],
    "verdict": verdict,
    "detail": detail,
    "value": value,
    "certificate_sha256": data["certificate_sha256"],
    "claim": data["claim"],
    "duplicate_certificate": duplicate_of,
  }
  record["points"] = score(record, root)
  note = f" The same certificate was already submitted by @{duplicate_of}, so it earns no result points." if duplicate_of else ""
  message = f"Recorded on the Math@Home board: {detail}{note} Points: +{record['points']['total']}."
  return {
    "action": "record",
    "issue": number,
    "record": record,
    "certificate": data["certificate"],
    "message": message,
    "labels": ["recorded"] + (["verified"] if verdict in ("valid", "side_record", "record") else [])
              + (["discovery"] if verdict in ("side_record", "record") else []),
  }


def write(outcome: dict, root: Path) -> None:
  if outcome["action"] != "record":
    return
  record = outcome["record"]
  path = record_path(root, record["login"], record["shift"]["id"])
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
  if outcome.get("certificate") is not None and record.get("certificate_sha256"):
    cert = root / "data" / "certificates" / f"{record['certificate_sha256']}.json"
    cert.parent.mkdir(parents=True, exist_ok=True)
    cert.write_text(json.dumps(outcome["certificate"], separators=(",", ":")) + "\n", encoding="utf-8")
  build_board.build(root)


def _github(method: str, path: str, body: dict | None = None) -> None:
  token = os.environ["GITHUB_TOKEN"]
  repo = os.environ["GITHUB_REPOSITORY"]
  request = urllib.request.Request(
    f"https://api.github.com/repos/{repo}{path}",
    data=json.dumps(body).encode("utf-8") if body is not None else None,
    method=method,
    headers={
      "Authorization": f"Bearer {token}",
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
  )
  with urllib.request.urlopen(request, timeout=20):
    pass


def notify(outcome: dict) -> None:
  number = outcome.get("issue")
  if outcome["action"] == "ignore" or not isinstance(number, int):
    return
  if outcome["action"] == "redact":
    _github("PATCH", f"/issues/{number}", {
      "title": "Submission removed",
      "body": "The text of this submission was removed because it looked like it contained a credential.",
    })
  _github("POST", f"/issues/{number}/comments", {"body": outcome["message"]})
  labels = outcome.get("labels") or (["rejected"] if outcome["action"] in ("redact", "reject") else ["duplicate"])
  _github("POST", f"/issues/{number}/labels", {"labels": labels})
  _github("PATCH", f"/issues/{number}", {
    "state": "closed",
    "state_reason": "completed" if outcome["action"] == "record" else "not_planned",
  })


def main() -> int:
  phase = sys.argv[1] if len(sys.argv) > 1 else "process"
  if phase == "process":
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
    issue = event.get("issue")
    if not isinstance(issue, dict):
      build_board.build(ROOT)  # manual run: just rebuild the board
      OUTCOME.write_text(json.dumps({"action": "ignore"}), encoding="utf-8")
      return 0
    outcome = process(issue, ROOT)
    write(outcome, ROOT)
    OUTCOME.write_text(json.dumps({k: v for k, v in outcome.items() if k != "certificate"}), encoding="utf-8")
    print(outcome["action"], outcome.get("message", ""))
    return 0
  if phase == "notify":
    if OUTCOME.exists():
      notify(json.loads(OUTCOME.read_text(encoding="utf-8")))
    return 0
  print("usage: ingest.py process|notify", file=sys.stderr)
  return 2


if __name__ == "__main__":
  sys.exit(main())
