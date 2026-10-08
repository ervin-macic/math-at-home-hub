"""Built-in certificate checkers.

Each checker takes the problem's ``verifier`` spec and the submitted
certificate and returns ``{"status", "value", "detail"}`` where status is one
of ``record``, ``side_record``, ``valid``, ``invalid`` or ``unsupported``.
Only these checkers can award record points without a review: a claim that no
checker covers waits for an independent confirmation.
"""

from __future__ import annotations

from . import c7, no3line, sqdiff

CHECKERS = {
  "no_three_in_line": no3line.check,
  "c7_independent_set": c7.check,
  "square_difference_modulus": sqdiff.check,
}


def supports(problem: dict) -> bool:
  return problem.get("verifier", {}).get("kind") in CHECKERS


def check(problem: dict, certificate) -> dict:
  spec = problem.get("verifier", {})
  checker = CHECKERS.get(spec.get("kind"))
  if checker is None:
    return {
      "status": "unsupported",
      "value": None,
      "detail": "This problem has no automatic checker; submit a claim for review instead.",
    }
  if not isinstance(certificate, dict):
    return {"status": "invalid", "value": None, "detail": "The certificate must be a JSON object."}
  try:
    return checker(spec, certificate)
  except (TypeError, ValueError, OverflowError) as exc:
    return {"status": "invalid", "value": None, "detail": f"Malformed certificate: {exc}"}
