# Issue #36 results: S01 dynamic family v0.2

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies on synthetic scenarios. No LLM was run and nothing here is a model-ability claim.

## Status
- Implemented: yes (findings S1 to S7, see `plan.md`).
- Tested: yes. Full suite 266 tests, OK (202 existing plus 64 new). Raw output: `tests.log`.
- Practitioner-reviewed: **no.** The repair awaits the reviewer's re-review (owner-practitioner, not independent).

## Regenerate
`PYTHONPATH=src python scripts/run_dynamic_demo_v2.py --out evidence/issue-36` then `PYTHONPATH=src python -m unittest discover -s tests -v`. Output is deterministic.

## Scenario by policy summary (net cost and the other separate metrics are in `scorecard.md`)
Net cost is only the total of the cost block (spend + penalties - salvage). It is shown beside, not instead of, the other metrics.

| Scenario | Policy | Net cost | OTIF orders met | Cancelled units | Unit-days late | Primary reliance % | Cover days |
|---|---|---|---|---|---|---|---|
| sudden 5d | maintain | 120 | 0/1 | 0 | 12 | 100 | 0 |
| sudden 5d | expedite on alert | 24 | 1/1 | 0 | 0 | 100 | 0 |
| sudden 5d | alternate on alert | 24 | 1/1 | 0 | 0 | 50 | 2 |
| sudden 5d | combo on alert | 24 | 1/1 | 0 | 0 | 66 | 1 |
| sudden 5d | staged revisit | 28 | 1/1 | 0 | 0 | 100 | 0 |
| warned, delayed 10d | maintain | 50 | 0/1 | 0 | 20 | 100 | 0 |
| warned, delayed 10d | expedite on alert | 24 | 1/1 | 0 | 0 | 100 | 0 |
| warned, delayed 10d | alternate on alert | 24 | 1/1 | 0 | 0 | 50 | 2 |
| warned, delayed 10d | combo on alert | 24 | 1/1 | 0 | 0 | 66 | 1 |
| warned, delayed 10d | staged revisit | 28 | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d | maintain | 0 | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d | expedite on alert | 24 | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d | alternate on alert | 24 | 1/1 | 0 | 0 | 50 | 2 |
| warned, no delay 10d | combo on alert | 24 | 1/1 | 0 | 0 | 66 | 1 |
| warned, no delay 10d | staged revisit | 12 | 1/1 | 0 | 0 | 100 | 0 |
| multi-tier cancel 10d | maintain | 64 | 0/2 | 8 | 32 | 100 | 1 |
| multi-tier cancel 10d | expedite on alert | 48 | 1/2 | 4 | 12 | 100 | 0 |
| multi-tier cancel 10d | alternate on alert | 56 | 1/2 | 0 | 12 | 50 | 1 |
| multi-tier cancel 10d | combo on alert | 48 | 1/2 | 0 | 8 | 66 | 0 |
| multi-tier cancel 10d | staged revisit | 52 | 1/2 | 4 | 12 | 100 | 0 |

## What the per-metric comparison shows (no overall winner is declared)
- In every scenario no policy is best on every metric (`comparison.md`, `comparison.json`).
- Warned and delayed: acting on the signal avoids a USD 50 penalty and a late order. The signal alone does not reveal whether the delay will come (the paired scenario is observation-identical until the firm notice), so the same policy spends the same money when the delay never comes.
- Warned and no delay: maintain has the lowest cost (0); every reactive policy spends 12 to 40 for no service gain. This is the dilemma the signal creates, and the agent cannot assume a delay.
- Multi-tier: the standard tier loses units to cancellation under maintain, expedite and staged revisit; the key tier backlogs and is served first. Alternate and combo avoid cancellation (cancelled order value 0) at different spend and supply-risk profiles. Which trade is right is a practitioner decision.

## Evidence index
| File | Content |
|---|---|
| `plan.md` | scope, design, verification approach |
| `timeline.txt` | chronological actions and events for all 20 episodes |
| `state-ledger.csv`, `state-ledger.json` | per-day ledger rows (independent verifier derivation) |
| `scorecard.md`, `scorecard.json` | per-metric scorecards, flat and full blocks |
| `comparison.md`, `comparison.json` | per-metric comparison with trade-off flags |
| `checks.json` | verifier results, hand-ledger match, corruption cases, rejection probes, leak scan |
| `replay.json`, `replay.log` | replay command and per-episode results |
| `experience-record.json`, `.md` | one observable record (warned and delayed, staged revisit), scanned for private answers |
| `transcripts.json` | full runner transcripts for all 20 episodes |
| `gate-report.md`, `report.html` | gate table and a rendered summary |
| `tests.log` | full unittest run |

## Checks performed
- Hand-worked ledgers (`fixtures/dynamic/v0.2/hand-ledgers.json`) were written before any code output was inspected. The simulator, the independent verifier and the hand work agreed on all 20 episodes (per-day ledgers and per-episode metrics, including per-tier rows).
- The verifier imports only `dataclasses` (AST test). It was exercised with: duplicate commitment, over-budget combination, premature receipt and recovery, recovery after the window, oversized quantities, wrong penalty, a simulator with a wrong contract term, state and inventory tampering, forged cancellation, forged scorecard and pass flags, and three forms of leaked early signal.
- Every episode replays from recorded calls on a fresh world with identical state sequence and scorecard.
- All agent observations in all 20 episodes pass the private-answer and outcome-leak scan. The warned-and-delayed and warned-and-no-delay scenarios are observation-identical until the firm notice for every policy.
- Parity: whole-lot commitments on the sudden 5-day scenario reproduce the v0.1 costs 120, 24 and 40 before salvage (test).

## Limitations
- Every value is provisional and unreviewed. The review confirmed no number.
- The warned hint (60) is authored, not calibrated. It is the same in the delayed and no-delay variants by design.
- The scorecard proxies for OTIF, downstream impact and supply risk are assumptions, listed in `docs/acceptance/dynamic-v0.2-provisional-values.md`.
- Premature receipt and wrong penalty are shown at verifier level, not through agent tools. No hostile-agent sandbox exists (the runner boundary is for well-behaved in-process policies).
- No 15-day scenario was built; horizons are 5 and 10 days.
- The v0.1 demo, fixtures, tests and evidence are unchanged.
