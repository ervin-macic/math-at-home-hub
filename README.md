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
   certificate with the same checkers the app uses, scores it, writes
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
