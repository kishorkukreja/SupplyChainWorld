# Issue #36 plan: extend the S01 dynamic scenario family (REPAIR-17b)

Source: owner-practitioner review (not independent), findings S1 to S7. Decision: repair, then re-review. All numbers are PROVISIONAL, needs practitioner value.

## Constraints
- Do not edit or delete the S01 v0.1 fixture, tests or evidence. Build v0.2 beside it and reuse v0.1 code only by import.
- The existing 202 tests must keep passing.
- Report cost, service, tier impact, downstream impact and supply risk as separate metrics. Declare no overall best policy.
- No model-ability claim. Scripted policies only.

## Design
| Finding | Mechanism | Where |
|---|---|---|
| S1/S4 separate metrics | Five scorecard blocks, no single score; per-metric comparison with trade-off flags | `dynamic_v2.OperationalWorldV2.scorecard`, `dynamic_demo_v2.compare_policies` |
| S2 penalty contract | Per-order term: percent of value, fixed per unit (once), per unit per day | `dynamic_v2.close_day` |
| S3 salvage | Credit for components left at the end of the horizon | `dynamic_v2.close_day` |
| S5 tiers | Tier weight orders shipments; tier rule is backlog or cancel after a day | `dynamic_v2.close_day` |
| S6 combined/revisited recovery | Repeatable `commit_recovery(choice, quantity)`, rate card by day, one budget, commit ids execute once | `dynamic_v2.choose_recovery`, `agent_runner_v2` |
| S7 sudden and warned | Optional signal with a hint and fixed text; firm notice later confirms delay or on-time | `dynamic_v2._open_day` |

New files: `src/supplychainworld/{dynamic_v2,agent_runner_v2,dynamic_verifier_v2,dynamic_demo_v2}.py`, `fixtures/dynamic/v0.2/{scenarios,hand-ledgers}.json`, `scripts/run_dynamic_demo_v2.py`, `docs/acceptance/dynamic-v0.2-provisional-values.md`, four new test files, this folder.

## Verification approach
1. Hand-work the ledgers per scenario and policy first (20 episodes), store them in `hand-ledgers.json`.
2. Independent verifier `dynamic_verifier_v2` imports no simulator code (AST test) and re-derives each ledger from commands.
3. Compare simulator, verifier and hand ledgers; investigate any mismatch.
4. Adversarial tests: duplicate commitment, over-budget combination, premature receipt and recovery, wrong penalty, tampering, forged scorecard, leaked early signal.
5. Replay every episode on a fresh world; scan observations for private answers; check the warned pair is observation-identical until the firm notice.

## Scenarios and declared policies
Scenarios: sudden 5d; warned and delayed 10d; warned and no delay 10d; multi-tier with cancellation 10d (sudden).
Policies (scripted, read only the visible view): maintain; expedite on alert; alternate on alert; combo on alert (half expedite plus half alternate); staged revisit (half expedite on alert, rest after the delay is confirmed, at the later price).

## Out of scope
A 15-day variant was not built; the 10-day horizon already separates the late-event cases. Practitioner values, an LLM run and any ability claim are out of scope.
