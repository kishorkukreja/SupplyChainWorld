# S01 v0.6 results

Nothing here is practitioner-reviewed and nothing claims model ability. All business numbers are PROVISIONAL, needs practitioner value.
These are software tests of synthetic rules. No live model call was made; the owner runs the model test later.

## In plain language

**What v0.6 is.** A new version of the S01 supplier-delay world, built beside v0.5. v0.1 to v0.5, their fixtures and the first
diagnostic's evidence (`evidence/issue-19`) were not touched, so the first diagnostic's recorded fingerprints still match.

**1. A fixed independent checker.** The v0.4 and v0.5 checkers have five known defects that could not be fixed in place (the first
diagnostic's manifest freezes that file). The new checker, `dynamic_verifier_v6`, imports no simulator code and fixes all five:

| Defect | What was wrong | Now |
|---|---|---|
| D2 | the "day opening" records and their order were never checked; a forged, deleted, duplicated or moved one passed | every opening record is checked against the checker's own ledger, in order |
| D3 | only part of each recorded state was compared | the whole state is compared, key by key and type by type, including the schema and runtime version |
| D4 | a record whose details or state was not a mapping made the checker crash | reported as malformed, no crash |
| D5 | a broken scenario (orders, tiers) made it crash instead of giving the documented scenario error | always the documented `ScenarioError` |
| D6 | a broken action log made it crash | reported as malformed, no crash |

Exact-once purchases (S01.4): in v0.2 to v0.5 a purchase sent without an `action_id` could be repeated and executed twice. In v0.6 a
purchase sent without an id gets a key built from its day, choice and quantity, and the same purchase repeated the same day is refused.
Two identical lots on purpose need two distinct ids. The `auto-` prefix is reserved. (Chosen over rejecting a missing id because the
scripted policies and the first diagnostic harness never send ids; rejecting would have changed what they do.)

Same mutation and garbage-history campaign as the audit (`mutation-fuzz-summary.md`):

| | v0.5 checker (before) | v0.6 checker (after) |
|---|---|---|
| tampered histories tried | 4174 | 4169 |
| accepted although tampered | 1801 | 0 |
| crashes on tampered histories | 0 | 0 |
| crashes on garbage histories (of 1000) | 311 | 0 |
| garbage accepted as a complete, feasible episode | 0 | 0 |
| damaged scenarios that crash instead of the documented error | 1 | 0 |
| forged scorecards rejected | 500 of 500 | 500 of 500 |
| forged action logs rejected | 487 of 487 | 484 of 484 |

The v0.6 checker has a last-resort guard that turns an unexpected error into "malformed record" (never into feasible). It fired 0 times
in the fuzz campaign, so the zero crash count is not hiding behind it.

**2. A conventions block in what the agent sees (S01.3).** The world now states, in `rules.conventions`, from the world itself: receipts
that arrive at day opening can be used the same day; production completes at the close of the day; shipping starts from the due day,
at close; due orders are served by tier weight (highest first) then order id; the unit of the penalty rate (percent-type rates are in
basis points, 150 = 1.5 percent per day; the other two types are whole USD per unit, once or per day); the cap; cancellation; the
exact-once rule. Each fact is a plain sentence and a machine-readable value, and the same sentences are built into the model prompt.
The early-warning boundary is unchanged: the block depends only on visible parameters, and twin scenarios still look identical until the
firm notice.

An assessor that reads only the agent view (conventions included, no defaults, and it refuses to run if the block is missing)
computes units at risk, shortfall per order, earliest delivery, penalties and spend. After the firm notice they equal the independent
checker exactly, for generated scenarios (Hypothesis) and for every fixture, day and recovery option. Before the notice only a range is
knowable, by design, and the range brackets the truth. Reading a stated convention differently changes the answer on a fixture, so the
block does real work. The rules-in-prompt test (PR #47 pattern) now maps every v0.6 refusal reason to a stated sentence.

**3. Demonstration packet, page and browser test.** `scripts/run_dynamic_demo_v6.py` regenerates `evidence/s01-v06/` (timeline, ledgers,
scorecards, per-metric comparison, checks, replay, one experience record with no private answers, gate report, `report.html`).
A real-browser test opens the page (freshly generated and the committed one), compares titles, the 25 scorecard rows, 65 per-metric
rows, the conventions list, the experience record, the gate table and all 479 timeline entries with the source JSON, finds no console
errors, and a real screenshot is saved at `screenshots/s01-v06-report.png` (viewed; it renders). A determinism test regenerates the
packet and compares every file byte for byte with the committed one. The 25 hand-worked ledgers come from
`scripts/generate_hand_ledgers_v06.py` (imports nothing from the project); the simulator, the v0.6 checker and the ledgers agree on all
25 episodes; replay and the leak scan pass on all 25.

The experience record has a plain-language version (`experience-record.md`) and a structural readability check (sections present, a
plain line for every action, no raw internal ids or private fields). The check itself is tested on damaged records. **It does not show
that a person finds the record readable**; nobody has been asked.

## Tests

Full suite on this machine: 955 tests, OK, 12 skipped, 435 s (`tests.log`). The 12 skips are the old v0.4 and v0.5 tests that
need the checker fixes and stay skipped there; none is skipped for v0.6. New for v0.6: 115 tests (property and mutation 15, fuzz 19,
regressions 19, assessment 11, end to end 17, browser 4, fixtures and independence 12, rules in prompt and mocked 25-episode run 18).

## What remains a gap

- S01.3 is partial, not closed: before a firm notice only a range is knowable (kept on purpose); "units at risk" and "earliest delivery"
  are the assessor's own definitions, not fields of the world; no worked example per penalty type is shown in the view; and nobody has
  run a model, so whether a model reads the block correctly is untested.
- Readability of the experience record is checked structurally only.
- Exact-once without an id is a refusal of a same-day repeat; two different explicit ids with identical content are two deliberate purchases.
- G1 is partial (no separate test for a written visibility definition); G9 stays open by design (no practitioner review).
- The v0.4 and v0.5 checkers still have D2 to D6 (frozen); use v0.6 for anything that depends on the checker.
- The eval19-3 materials are a DRAFT and were not run (`docs/eval19-v3-draft.md`); the conventions block adds about 1,000 tokens to every
  observation, which the owner should check against the free models' context limits.
