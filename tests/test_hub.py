"""Offline tests for the community hub.  Run: python -m unittest discover -s tests -v"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import combinations
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_board  # noqa: E402
import ingest  # noqa: E402
import lean_check  # noqa: E402
from mathathome import problems, submission  # noqa: E402


def no3_solution(n: int) -> list[list[int]]:
  rows = list(combinations(range(1, n + 1), 2))
  chosen: list[tuple[int, int]] = []

  def ok(p) -> bool:
    for i in range(len(chosen)):
      for j in range(i + 1, len(chosen)):
        (x1, y1), (x2, y2) = chosen[i], chosen[j]
        if (x2 - x1) * (p[1] - y1) == (p[0] - x1) * (y2 - y1):
          return False
    return True

  def place(y: int) -> bool:
    if y > n:
      return True
    for a, b in rows:
      p, q = (a, y), (b, y)
      if ok(p):
        chosen.append(p)
        if ok(q):
          chosen.append(q)
          if place(y + 1):
            return True
          chosen.pop()
        chosen.pop()
    return False

  assert place(1)
  return [list(p) for p in chosen]


def make_body(shift_id="s_20261008013700_ab12cd", problem_id="no-three-in-line", certificate=None, summary="Tried a SAT encoding."):
  problem = problems()[problem_id]
  extras = []
  if certificate is not None:
    extras.append({"kind": "certificate", "payload": certificate, "verdict": "valid"})
  built = submission.build(
    shift={"id": shift_id, "problem_id": problem_id, "lane_id": "sat-75", "begun_at": "2026-10-08T00:37:00+00:00",
           "minutes": 28.0, "tokens": {"total_tokens": 1200000}},
    report={"title": "SAT run on n = 75", "summary": summary, "details": {"learned": "rot2 is slow.", "next": "Try ort1."}},
    extras=extras, problem=problem, credit_name="Ada", app_version="0.3.0",
  )
  return built


def issue(body, login="ada-l", number=7, title="[submission] test"):
  return {"number": number, "title": title, "body": body, "user": {"login": login, "type": "User"},
          "html_url": f"https://github.com/ervin-macic/math-at-home-hub/issues/{number}",
          "created_at": "2026-10-08T01:10:00Z"}


# Fake credentials, assembled at runtime so no credential-shaped literal sits in
# the repository (and secret scanners have nothing to flag).
FAKE_ANTHROPIC = "sk-" + "ant-api03-" + "AbCdEfGhIjKlMnOpQrStUvWx"
FAKE_GITHUB = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789"
FAKE_JWT = ".".join(["eyJ" + "hbGciOiJIUzI1NiJ9", "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0", "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"])


class IngestTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)

  def tearDown(self):
    self.tmp.cleanup()

  def record(self, outcome):
    ingest.write(outcome, self.root)
    return outcome

  def test_report_is_recorded_and_scored(self):
    outcome = self.record(ingest.process(issue(make_body()["body"]), self.root, "2026-10-08T01:11:00+00:00"))
    self.assertEqual(outcome["action"], "record")
    rec = outcome["record"]
    self.assertEqual((rec["login"], rec["verdict"]), ("ada-l", "report"))
    self.assertEqual(rec["points"], {"report": 10, "time": 5, "result": 0, "total": 15})
    board = json.loads((self.root / "docs" / "data" / "board.json").read_text())
    self.assertEqual(board["contributors"][0]["points"]["all"], 15)
    self.assertEqual(board["recent_records"][0]["shift_id"], "s_20261008013700_ab12cd")

  def test_certificate_is_rechecked(self):
    outcome = self.record(ingest.process(issue(make_body(certificate={"n": 6, "points": no3_solution(6)})["body"]), self.root))
    self.assertEqual(outcome["record"]["verdict"], "valid")
    self.assertEqual(outcome["record"]["points"]["result"], 25)
    self.assertIn("verified", outcome["labels"])
    bad = no3_solution(6)
    bad[0], bad[1] = [1, 1], [2, 2]
    rejected = ingest.process(issue(make_body(shift_id="s_20261008020000_000001", certificate={"n": 6, "points": bad})["body"]), self.root)
    self.assertEqual(rejected["record"]["verdict"], "invalid")
    self.assertEqual(rejected["record"]["points"]["result"], 0)

  def test_duplicates_earn_nothing(self):
    cert = {"n": 6, "points": no3_solution(6)}
    self.record(ingest.process(issue(make_body(certificate=cert)["body"]), self.root))
    again = ingest.process(issue(make_body(certificate=cert)["body"]), self.root)
    self.assertEqual(again["action"], "duplicate")
    copied = ingest.process(issue(make_body(shift_id="s_20261008020000_00000f", certificate=cert)["body"], login="copycat"), self.root)
    self.assertEqual(copied["record"]["duplicate_certificate"], "ada-l")
    self.assertEqual(copied["record"]["points"]["result"], 0)

  def test_credentials_are_blanked_and_rejected(self):
    body = make_body()["body"].replace("rot2 is slow.", "rot2 is slow. " + FAKE_ANTHROPIC)
    outcome = ingest.process(issue(body), self.root)
    self.assertEqual(outcome["action"], "redact")
    self.assertNotIn(FAKE_ANTHROPIC, json.dumps(outcome))
    jwt = make_body()["body"].replace("Tried", FAKE_JWT + " Tried")
    self.assertEqual(ingest.process(issue(jwt), self.root)["action"], "redact")

  def test_the_app_never_builds_a_body_with_credentials(self):
    built = make_body(summary=f"Used key {FAKE_ANTHROPIC} and token {FAKE_GITHUB} at /data/apps/42/workspace")
    self.assertGreaterEqual(built["redactions"], 3)
    self.assertNotIn(FAKE_ANTHROPIC, built["body"])
    self.assertNotIn(FAKE_GITHUB, built["body"])
    self.assertNotIn("/data/apps", built["body"])
    self.assertEqual(ingest.process(issue(built["body"]), self.root)["action"], "record")

  def test_rejects_and_ignores(self):
    self.assertEqual(ingest.process(issue("Just a question about the board"), self.root)["action"], "ignore")
    bot = issue(make_body()["body"])
    bot["user"]["type"] = "Bot"
    self.assertEqual(ingest.process(bot, self.root)["action"], "ignore")
    broken = submission.MARKER + "\n```json\n{not json}\n```"
    self.assertEqual(ingest.process(issue(broken), self.root)["action"], "reject")
    data = make_body()["payload"]
    data["shift"]["problem_id"] = "riemann"
    bad = submission.MARKER + "\n```json\n" + json.dumps(data) + "\n```"
    self.assertIn("unknown problem", ingest.process(issue(bad), self.root)["message"])
    data = make_body()["payload"]
    data["chat_transcript"] = "…"
    extra = submission.MARKER + "\n```json\n" + json.dumps(data) + "\n```"
    self.assertIn("unexpected fields", ingest.process(issue(extra), self.root)["message"])

  def test_daily_report_cap(self):
    for i in range(12):
      self.record(ingest.process(issue(make_body(shift_id=f"s_20261008{i:06d}_aaaaaa")["body"], number=i + 1), self.root, "2026-10-08T05:00:00+00:00"))
    thirteenth = ingest.process(issue(make_body(shift_id="s_20261008999999_bbbbbb")["body"]), self.root, "2026-10-08T06:00:00+00:00")
    self.assertEqual(thirteenth["record"]["points"]["report"], 0)

  def test_board_windows(self):
    now = datetime(2026, 10, 20, tzinfo=UTC)
    old = (now - timedelta(days=12)).isoformat(timespec="seconds")
    new = (now - timedelta(days=2)).isoformat(timespec="seconds")
    self.record(ingest.process(issue(make_body(shift_id="s_20261008010000_000001")["body"]), self.root, old))
    self.record(ingest.process(issue(make_body(shift_id="s_20261018010000_000002")["body"]), self.root, new))
    board = build_board.build(self.root, now=now)
    person = board["contributors"][0]
    self.assertEqual((person["points"]["7d"], person["points"]["30d"], person["points"]["all"]), (15, 30, 30))
    self.assertEqual(board["totals"]["shifts"], 2)
    self.assertEqual(len(board["problems"]), 6)


class NewProblemTests(unittest.TestCase):
  """Integer multiplication below n log n: claims only, with a live record source."""

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)

  def tearDown(self):
    self.tmp.cleanup()

  def test_claim_on_the_multiplication_problem_waits_for_review(self):
    problem = problems()["integer-multiplication"]
    built = submission.build(
      shift={"id": "s_20261009013700_ab12cd", "problem_id": problem["id"], "lane_id": "parameters",
             "begun_at": "2026-10-09T00:37:00+00:00", "minutes": 30.0, "tokens": {"total_tokens": 900000}},
      report={"title": "Parameter refinement of the paired-cube witness", "summary": "Re-optimised exact parameters.",
              "details": {"learned": "The margin is tight.", "next": "Try the bit branch."}},
      extras=[{"kind": "claim", "verdict": "pending_review",
               "payload": {"statement": "Refined parameters give a larger kappa.", "value": "4700000/10000000000"}}],
      problem=problem, credit_name="Ada", app_version="0.5.0",
    )
    outcome = ingest.process(issue(built["body"]), self.root, "2026-10-09T01:10:00+00:00")
    ingest.write(outcome, self.root)
    self.assertEqual(outcome["action"], "record")
    self.assertEqual(outcome["record"]["verdict"], "pending_review")
    self.assertEqual(outcome["record"]["points"]["result"], 0, "claims earn record points only after review")

  def test_board_lists_why_it_matters_and_the_live_source(self):
    board = build_board.build(self.root, now=datetime(2026, 10, 9, tzinfo=UTC))
    by_id = {p["id"]: p for p in board["problems"]}
    self.assertEqual([p["rank"] for p in board["problems"]], [1, 2, 3, 4, 5, 6])
    self.assertTrue(all(p["summary"] for p in board["problems"]))
    live = by_id["integer-multiplication"]["live_record"]
    self.assertEqual(live["raw"], "https://raw.githubusercontent.com/CrocSwap/integer-mult-bounds/main/certificates/selected-result.json")
    self.assertTrue(all(p["live_record"] is None for pid, p in by_id.items() if pid != "integer-multiplication"))


class LeanCheckTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)
    self.outcome = mock.patch.object(lean_check, "OUTCOME", self.root / ".hub-outcome.json")
    self.outcome.start()

  def tearDown(self):
    self.outcome.stop()
    self.tmp.cleanup()

  def record_certificate(self, cert, shift_id="s_20261008013700_ab12cd", number=7, problem_id="no-three-in-line"):
    body = make_body(shift_id=shift_id, problem_id=problem_id, certificate=cert)["body"]
    outcome = ingest.process(issue(body, number=number), self.root)
    ingest.write(outcome, self.root)
    (self.root / ".hub-outcome.json").write_text(json.dumps({k: v for k, v in outcome.items() if k != "certificate"}))
    return outcome

  def stored(self, shift_id="s_20261008013700_ab12cd"):
    return json.loads((self.root / "data" / "records" / "ada-l" / f"{shift_id}.json").read_text())

  def test_kernel_proof_is_recorded_on_record_board_and_reply(self):
    self.record_certificate({"n": 6, "points": no3_solution(6)})
    calls = []
    def runner(source, timeout):
      calls.append(source)
      return 0, "'MathAtHome.NoThreeInLine.certificate_valid' does not depend on any axioms"
    lean_check.main(self.root, runner)
    lean = self.stored()["lean"]
    self.assertEqual((lean["status"], lean["method"]), ("verified", "kernel"))
    self.assertIn("decide +kernel", calls[0])
    board = json.loads((self.root / "docs" / "data" / "board.json").read_text())
    self.assertEqual(board["totals"]["lean_verified"], 1)
    self.assertEqual(board["findings"][0]["lean"]["status"], "verified")
    self.assertEqual(board["recent_records"][0]["lean"]["method"], "kernel")
    outcome = json.loads((self.root / ".hub-outcome.json").read_text())
    self.assertIn("lean-verified", outcome["labels"])
    self.assertIn("Lean 4 ✓ (kernel)", outcome["message"])
    lean_check.main(self.root, runner)
    self.assertEqual(len(calls), 1, "already checked records are not re-run")

  def test_refutation_does_not_fall_back(self):
    bad = no3_solution(6)
    bad[0], bad[1] = [1, 1], [2, 2]
    self.record_certificate({"n": 6, "points": bad})
    calls = []
    def runner(source, timeout):
      calls.append(source)
      return 1, "Certificate.lean:31:56: error: Tactic `decide` proved that the proposition\n  valid n points = true\nis false"
    lean_check.main(self.root, runner)
    self.assertEqual(self.stored()["lean"]["status"], "failed")
    self.assertEqual(len(calls), 1)

  def test_timeout_falls_back_to_the_compiled_check(self):
    self.record_certificate({"modulus": 205, "residues": [0, 2, 8, 14, 77, 79, 85, 96, 103, 109, 111, 181]}, problem_id="furstenberg-sarkozy")
    answers = [None, (0, "'certificate_valid' depends on axioms: [certificate_valid._native.native_decide.ax_1_1]")]
    sources = []
    def runner(source, timeout):
      sources.append(source)
      return answers.pop(0)
    lean_check.main(self.root, runner)
    lean = self.stored()["lean"]
    self.assertEqual((lean["status"], lean["method"]), ("verified", "native"))
    self.assertIn("native_decide", sources[1])
    self.assertEqual(lean["axioms"], ["certificate_valid._native.native_decide.ax_1_1"])

  def test_real_lean_when_available(self):
    import shutil
    if shutil.which("lean") is None:
      self.skipTest("lean is not installed")
    self.record_certificate({"modulus": 205, "residues": [0, 2, 8, 14, 77, 79, 85, 96, 103, 109, 111, 181]}, problem_id="furstenberg-sarkozy")
    lean_check.main(self.root)
    lean = self.stored()["lean"]
    self.assertEqual((lean["status"], lean["method"], lean["axioms"]), ("verified", "kernel", []))


class VendoredCopyTests(unittest.TestCase):
  def test_matches_the_app_when_both_are_present(self):
    app = ROOT.parent
    pairs = {"catalog.json": "catalog.json", "engine/scrub.py": "scrub.py", "engine/submission.py": "submission.py",
             "engine/lean.py": "lean.py",
             "engine/verify/c7.py": "verify/c7.py", "engine/verify/no3line.py": "verify/no3line.py",
             "engine/verify/sqdiff.py": "verify/sqdiff.py"}
    if not (app / "engine").is_dir():
      self.skipTest("standalone hub checkout")
    for source, copy in pairs.items():
      self.assertEqual((app / source).read_bytes(), (ROOT / "scripts" / "mathathome" / copy).read_bytes(), source)


if __name__ == "__main__":
  unittest.main()
