#!/usr/bin/env python3
"""Aggregate every community record into docs/data/board.json.

The board is the single public read model: the web page and every Math@Home
install read it. It holds only what submitters chose to publish.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mathathome import catalog, problems  # noqa: E402

FINDING_VERDICTS = ("record", "side_record", "valid", "pending_review", "confirmed")
DISCOVERY_VERDICTS = ("record", "side_record", "confirmed")
MAX_FEED = 100
MAX_RECENT = 500
MAX_CONTRIBUTORS = 500


def _when(record: dict) -> datetime:
  try:
    return datetime.fromisoformat(record["recorded_at"]).astimezone(UTC)
  except (KeyError, ValueError):
    return datetime(1970, 1, 1, tzinfo=UTC)


def _public(record: dict) -> dict:
  shift = record["shift"]
  return {
    "when": record["recorded_at"],
    "login": record["login"],
    "name": record.get("credit_name") or "",
    "problem_id": shift["problem_id"],
    "lane_id": shift.get("lane_id", ""),
    "title": record["report"]["title"],
    "summary": record["report"]["summary"],
    "verdict": record["verdict"],
    "value": record.get("value"),
    "detail": record.get("detail", ""),
    "points": record["points"]["total"],
    "issue_url": record.get("issue_url"),
    "lean": _lean(record),
  }


def _lean(record: dict) -> dict | None:
  result = record.get("lean")
  if not isinstance(result, dict):
    return None
  return {"status": result.get("status"), "method": result.get("method"), "toolchain": result.get("toolchain")}


def _better(problem: dict, candidate, current) -> bool:
  if current is None:
    return True
  try:
    return float(candidate) > float(current)
  except (TypeError, ValueError):
    return False



def _live_source(problem: dict) -> dict | None:
  """Where the page can read a record that moves faster than the catalog (public data only)."""
  config = problem.get("live_record") or {}
  if config.get("kind") != "integer-mult-bounds" or not config.get("repo") or not config.get("path"):
    return None
  return {
    "kind": config["kind"],
    "raw": f"https://raw.githubusercontent.com/{config['repo']}/{config.get('branch', 'main')}/{config['path']}",
    "page": f"https://github.com/{config['repo']}",
    "tracker": config.get("tracker"),
  }

def build(root: Path = ROOT, now: datetime | None = None) -> dict:
  now = now or datetime.now(UTC)
  records = []
  folder = root / "data" / "records"
  if folder.is_dir():
    for path in sorted(folder.glob("*/*.json")):
      try:
        records.append(json.loads(path.read_text(encoding="utf-8")))
      except (OSError, ValueError):
        continue
  records.sort(key=_when, reverse=True)
  windows = {"7d": now - timedelta(days=7), "30d": now - timedelta(days=30), "all": None}

  people: dict[str, dict] = {}
  for record in records:
    key = record["login"].lower()
    person = people.setdefault(key, {
      "login": record["login"],
      "name": record.get("credit_name") or "",
      "points": {"7d": 0, "30d": 0, "all": 0},
      "minutes": {"7d": 0.0, "30d": 0.0, "all": 0.0},
      "shifts": 0,
      "tokens": 0,
      "verified": 0,
      "discoveries": 0,
      "pending_claims": 0,
      "last_active": record["recorded_at"],
    })
    when = _when(record)
    for window, since in windows.items():
      if since is None or when >= since:
        person["points"][window] += record["points"]["total"]
        person["minutes"][window] += float(record["shift"]["minutes"])
    person["shifts"] += 1
    person["tokens"] += int(record["shift"].get("tokens") or 0)
    person["verified"] += 1 if record["verdict"] in ("valid", "side_record", "record") else 0
    person["discoveries"] += 1 if record["verdict"] in DISCOVERY_VERDICTS else 0
    person["pending_claims"] += 1 if record["verdict"] == "pending_review" else 0
  contributors = sorted(people.values(), key=lambda p: (-p["points"]["all"], p["login"].lower()))[:MAX_CONTRIBUTORS]
  for person in contributors:
    person["minutes"] = {k: round(v, 1) for k, v in person["minutes"].items()}

  catalog_problems = problems()
  problem_view = {}
  for pid, problem in catalog_problems.items():
    mine = [r for r in records if r["shift"]["problem_id"] == pid]
    best = None
    for record in mine:
      if record["verdict"] in ("valid", "side_record", "record") and _better(problem, record.get("value"), best and best["value"]):
        best = {"value": record.get("value"), "login": record["login"], "when": record["recorded_at"], "verdict": record["verdict"]}
    problem_view[pid] = {
      "id": pid,
      "rank": problem["rank"],
      "title": problem["title"],
      "short": problem["short"],
      "tier": problem["tier"],
      "known": problem["known"],
      "record": problem["record"],
      "summary": (problem.get("significance") or {}).get("summary"),
      "live_record": _live_source(problem),
      "shifts": len(mine),
      "contributors": len({r["login"].lower() for r in mine}),
      "minutes": round(sum(float(r["shift"]["minutes"]) for r in mine), 1),
      "best": best,
    }

  board = {
    "schema": "math-at-home/board@1",
    "generated_at": now.isoformat(timespec="seconds"),
    "catalog_as_of": catalog().get("as_of"),
    "totals": {
      "contributors": len(people),
      "shifts": len(records),
      "minutes": round(sum(float(r["shift"]["minutes"]) for r in records), 1),
      "tokens": sum(int(r["shift"].get("tokens") or 0) for r in records),
      "verified": sum(1 for r in records if r["verdict"] in ("valid", "side_record", "record")),
      "discoveries": sum(1 for r in records if r["verdict"] in DISCOVERY_VERDICTS),
      "lean_verified": sum(1 for r in records if (r.get("lean") or {}).get("status") == "verified"),
    },
    "contributors": contributors,
    "findings": [_public(r) for r in records if r["verdict"] in FINDING_VERDICTS][:MAX_FEED],
    "feed": [_public(r) for r in records][:MAX_FEED],
    "problems": sorted(problem_view.values(), key=lambda p: p["rank"]),
    "recent_records": [
      {"shift_id": r["shift"]["id"], "login": r["login"], "verdict": r["verdict"],
       "points": r["points"]["total"], "issue_url": r.get("issue_url"), "recorded_at": r["recorded_at"],
       "lean": _lean(r)}
      for r in records[:MAX_RECENT]
    ],
  }
  out = root / "docs" / "data" / "board.json"
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(board, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
  return board


if __name__ == "__main__":
  build()
  print("board rebuilt")
