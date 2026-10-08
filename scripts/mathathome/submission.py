"""The public submission format shared by the app and the community hub.

A submission is one shift's public record: an allowlisted subset of the
report, the certificate if one was checked, a claim's statement and
fingerprint, and the donated time. It never contains chats, transcripts,
workspace files, usage readings, provider details or credentials. The app
builds it (``build``); the hub parses and validates it (``parse``/``validate``)
and treats every field as untrusted input.
"""

from __future__ import annotations

import hashlib
import json
import re

from . import scrub as scrub_mod

SCHEMA = "math-at-home/submission@1"
MARKER = "<!-- math-at-home:submission v1 -->"
MAX_BODY_BYTES = 60_000
MAX_CERTIFICATE_BYTES = 45_000
TEXT_LIMITS = {"title": 120, "summary": 1500, "learned": 3000, "next": 1500}
CLAIM_LIMITS = {"statement": 2000, "value": 200}
SHIFT_ID = re.compile(r"^s_\d{14}_[0-9a-f]{6}$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
VERDICTS = {"valid", "side_record", "record", "invalid", "unsupported", "pending_review", "confirmed", "refuted"}


class SubmissionError(ValueError):
  """A submission the hub refuses, with a reason safe to show publicly."""


def _clip(text, limit: int) -> str:
  text = text if isinstance(text, str) else ""
  text = " ".join(text.split()) if limit <= 200 else text.strip()
  return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def fingerprint(value) -> str:
  blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
  return hashlib.sha256(blob).hexdigest()


def build(*, shift: dict, report: dict, extras: list[dict], problem: dict, credit_name: str, app_version: str) -> dict:
  """The exact public submission for one finished shift (app side).

  ``report`` is the report contribution with its parsed ``details``;
  ``extras`` are its certificate/claim contributions, each with the parsed
  certificate or claim attached as ``payload``.
  """
  details = report.get("details") or {}
  payload: dict = {
    "schema": SCHEMA,
    "app_version": app_version,
    "credit_name": _clip(credit_name, 60),
    "shift": {
      "id": shift["id"],
      "problem_id": shift["problem_id"],
      "lane_id": shift.get("lane_id") or "",
      "started_at": shift.get("begun_at") or shift.get("created_at"),
      "minutes": round(float(shift.get("minutes") or 0.0), 1),
      "tokens": int((shift.get("tokens") or {}).get("total_tokens") or 0),
    },
    "report": {
      "title": _clip(report.get("title"), TEXT_LIMITS["title"]),
      "summary": _clip(report.get("summary"), TEXT_LIMITS["summary"]),
      "learned": _clip(details.get("learned"), TEXT_LIMITS["learned"]),
      "next": _clip(details.get("next"), TEXT_LIMITS["next"]),
    },
    "certificate": None,
    "certificate_sha256": None,
    "certificate_omitted": False,
    "local_verdict": None,
    "claim": None,
  }
  for item in extras:
    if item.get("kind") == "certificate" and isinstance(item.get("payload"), dict):
      blob = json.dumps(item["payload"], separators=(",", ":"))
      payload["certificate_sha256"] = fingerprint(item["payload"])
      payload["local_verdict"] = item.get("verdict")
      if len(blob.encode("utf-8")) <= MAX_CERTIFICATE_BYTES:
        payload["certificate"] = item["payload"]
      else:
        payload["certificate_omitted"] = True
    elif item.get("kind") == "claim" and isinstance(item.get("payload"), dict):
      claim = item["payload"]
      payload["claim"] = {
        "statement": _clip(claim.get("statement"), CLAIM_LIMITS["statement"]),
        "value": _clip(claim.get("value"), CLAIM_LIMITS["value"]),
        "fingerprint": item.get("fingerprint") or fingerprint(claim),
      }
  # Credentials and personal details never leave, whatever the agent wrote.
  cleaned, redactions = scrub_mod.scrub_tree({k: v for k, v in payload.items() if k != "certificate"})
  cleaned["certificate"] = payload["certificate"]
  if payload["certificate"] is not None and scrub_mod.find_credentials(json.dumps(payload["certificate"])):
    cleaned["certificate"] = None
    cleaned["certificate_omitted"] = True
    redactions += 1
  title = f"[submission] {problem['short']}: {cleaned['report']['title']}"[:150]
  body = render_body(cleaned, problem)
  return {"title": title, "body": body, "payload": cleaned, "redactions": redactions, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}


def render_body(payload: dict, problem: dict) -> str:
  report = payload["report"]
  lines = [
    MARKER,
    f"**Math@Home result: {problem['title']}**",
    "",
    report["summary"],
    "",
    "Shared from the Math@Home app. The hub re-checks certificates and records this automatically.",
    "",
    "```json",
    json.dumps(payload, ensure_ascii=False, indent=1),
    "```",
  ]
  return "\n".join(lines)


def parse(body: str) -> dict:
  """Extract the JSON submission from an issue body (hub side)."""
  if not isinstance(body, str) or MARKER not in body:
    raise SubmissionError("not a Math@Home submission")
  if len(body.encode("utf-8")) > MAX_BODY_BYTES + 8_000:
    raise SubmissionError("the submission is too large")
  match = re.search(r"```json\s*\n(.*?)\n```", body, re.S)
  if not match:
    raise SubmissionError("the submission has no JSON block")
  try:
    data = json.loads(match.group(1))
  except ValueError as exc:
    raise SubmissionError(f"the JSON block is not valid ({exc.msg})") from None
  if not isinstance(data, dict):
    raise SubmissionError("the JSON block must be an object")
  return data


def _string(value, limit: int, name: str, required: bool = False) -> str:
  if value is None and not required:
    return ""
  if not isinstance(value, str) or (required and not value.strip()):
    raise SubmissionError(f"{name} must be text")
  if len(value) > limit:
    raise SubmissionError(f"{name} is longer than {limit} characters")
  return value.strip()


def validate(data: dict, known_problems: set[str]) -> dict:
  """Strictly normalize an untrusted submission (hub side)."""
  if data.get("schema") != SCHEMA:
    raise SubmissionError("unknown submission schema")
  allowed = {"schema", "app_version", "credit_name", "shift", "report", "certificate",
             "certificate_sha256", "certificate_omitted", "local_verdict", "claim"}
  extra = sorted(set(data) - allowed)
  if extra:
    raise SubmissionError(f"unexpected fields: {', '.join(extra)[:80]}")
  shift = data.get("shift")
  if not isinstance(shift, dict):
    raise SubmissionError("shift is required")
  shift_id = shift.get("id")
  if not isinstance(shift_id, str) or not SHIFT_ID.match(shift_id):
    raise SubmissionError("shift.id is malformed")
  problem_id = shift.get("problem_id")
  if problem_id not in known_problems:
    raise SubmissionError("unknown problem")
  minutes = shift.get("minutes")
  if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 <= minutes <= 150:
    raise SubmissionError("shift.minutes must be between 0 and 150")
  tokens = shift.get("tokens", 0)
  if isinstance(tokens, bool) or not isinstance(tokens, int) or not 0 <= tokens <= 50_000_000:
    raise SubmissionError("shift.tokens is out of range")
  report = data.get("report")
  if not isinstance(report, dict):
    raise SubmissionError("report is required")
  normalized = {
    "app_version": _string(data.get("app_version"), 20, "app_version"),
    "credit_name": _string(data.get("credit_name"), 60, "credit_name"),
    "shift": {
      "id": shift_id,
      "problem_id": problem_id,
      "lane_id": _string(shift.get("lane_id"), 40, "shift.lane_id"),
      "started_at": _string(shift.get("started_at"), 40, "shift.started_at"),
      "minutes": round(float(minutes), 1),
      "tokens": tokens,
    },
    "report": {
      "title": _string(report.get("title"), TEXT_LIMITS["title"], "report.title", required=True),
      "summary": _string(report.get("summary"), TEXT_LIMITS["summary"], "report.summary", required=True),
      "learned": _string(report.get("learned"), TEXT_LIMITS["learned"], "report.learned"),
      "next": _string(report.get("next"), TEXT_LIMITS["next"], "report.next"),
    },
    "certificate": None,
    "certificate_sha256": None,
    "claim": None,
  }
  certificate = data.get("certificate")
  if certificate is not None:
    if not isinstance(certificate, dict):
      raise SubmissionError("certificate must be an object")
    if len(json.dumps(certificate, separators=(",", ":")).encode("utf-8")) > MAX_CERTIFICATE_BYTES:
      raise SubmissionError("certificate is too large")
    normalized["certificate"] = certificate
    normalized["certificate_sha256"] = fingerprint(certificate)
  elif isinstance(data.get("certificate_sha256"), str) and FINGERPRINT.match(data["certificate_sha256"]):
    normalized["certificate_sha256"] = data["certificate_sha256"]
  claim = data.get("claim")
  if claim is not None:
    if not isinstance(claim, dict):
      raise SubmissionError("claim must be an object")
    claim_fp = claim.get("fingerprint")
    normalized["claim"] = {
      "statement": _string(claim.get("statement"), CLAIM_LIMITS["statement"], "claim.statement", required=True),
      "value": _string(claim.get("value"), CLAIM_LIMITS["value"], "claim.value"),
      "fingerprint": claim_fp if isinstance(claim_fp, str) and FINGERPRINT.match(claim_fp) else None,
    }
  return normalized
