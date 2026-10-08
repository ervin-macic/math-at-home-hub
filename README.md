# Math@Home community board

The public ledger for [Math@Home](https://github.com/ervin-macic/math-at-home),
a Möbius app in which volunteers lend their AI subscription's spare capacity to
open math problems.

**Live board: https://ervin-macic.github.io/math-at-home-hub/**

It shows who has donated the most AI time and points, what they have found
(machine-checked certificates, records, and claims awaiting review), and how
the community stands on each problem.

## How results get here

1. A volunteer's Math@Home runs a time-boxed shift on their own Möbius, on
   their own subscription, with their consent.
2. They choose to share a finished shift. The app shows exactly what will be
   public; one tap asks their own Möbius agent to open an issue here **from
   their own GitHub account**. That account is the credit: nobody can submit
   in someone else's name.
3. The **Record submissions** workflow reads the issue as data, re-checks any
   certificate with the same checkers the app uses, proves it in Lean 4, scores it, writes
   `data/records/<login>/<shift>.json`, rebuilds `docs/data/board.json`, and
   replies on the issue.

## What is public, and what never is

Public, by the volunteer's choice: their GitHub login and credit name, the
problem, the shift's report (title, summary, what was learned, next steps),
any certificate or claim, and the donated time and token count.

Never shared: chats or transcripts, workspace files, usage readings, provider
or account details, and credentials. The app redacts anything that looks like
a key, token, password, email address or local path before a submission is
even shown for approval. As a second line of defence, this hub rejects any
submission that still looks like it contains a credential and blanks its text
on GitHub.

## How results are verified

Every result on the board says which of these it has passed:

- **Built-in checker.** Certificates (a grid configuration, a set of words, a
  residue set) are checked with exact arithmetic by the app on the
  contributor's Möbius, and checked again here by `scripts/ingest.py`.
- **Lean 4 proof.** `scripts/lean_check.py` restates each certificate as a
  Lean 4 theorem (core Lean, toolchain `leanprover/lean4:v4.34.1`) and has
  Lean prove it. *Kernel* means `decide +kernel`: Lean's kernel computed the
  proof, with no extra axioms. *Compiled check* means `native_decide`, used
  only when the kernel would take too long; it also trusts Lean's compiler,
  and `#print axioms` shows that. Lean proves the certificate's defining
  property (for example "150 distinct points of the 75 × 75 grid, no three
  collinear"). A headline bound that depends on a classical theorem
  (Shannon capacity, Ruzsa's construction) is cited, not formalized.
- **Claims.** Proof sketches and computations that no checker covers are
  listed as awaiting review and earn record points only after independent
  confirmation.
- **Attribution.** Each result is credited to the person whose AI agent found
  it: the GitHub account that opened the issue, with a timestamp and a SHA-256
  fingerprint.

## Scoring

| Contribution | Points |
|---|---|
| Shift report (at most 12 a day count) | 10 |
| Certificate that passes a checker | 25 |
| Machine-checked side-quest record | 100 × tier |
| Machine-checked record | 500 × tier |
| Donated AI time (up to 120 minutes a shift) | 1 per 5 minutes |

A certificate already submitted by anyone earns no result points again. Claims
(proofs and constructions no checker covers) are listed as awaiting review and
earn record points only once confirmed.

## Maintenance

- `scripts/mathathome/` is a copy of the app's checkers, catalogue, submission
  format and scrubber, refreshed by the app's `tools/sync_hub.py`.
- To remove a record, delete its file under `data/records/` and run the
  workflow manually; the board is rebuilt from the records alone.
- Tests: `python -m unittest discover -s tests -v`.
