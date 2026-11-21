# Issue #36 round 3 results: S01 dynamic family v0.4

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies on synthetic scenarios. No LLM was run and nothing here is a model-ability claim. Reviewed: no, not independent.

## Status
- Implemented: yes (every round 3 decision, see `plan.md`).
- Tested: yes. Full suite 529 tests, OK. Raw output: `tests.log`.
- 25 episodes (5 scenarios x 5 policies): simulator, independent verifier and the hand ledgers agree on every one; every episode replays exactly and passes the leak scan.
- Practitioner-reviewed: **no.**

## UNRESOLVED ASSUMPTION (needs the reviewer)
Under "compare premiums only" the base cost of the alternate lot and the surplus it creates are unanswered. v0.4 treats the base purchase cost of any recovery lot as cost-neutral (excluded for every policy) and gives alternate-bought surplus no salvage. All salvage credits are therefore USD 0 in the fixtures. See `docs/acceptance/dynamic-v0.4-provisional-values.md`.

## Changed from v0.3
Alternate unit cost is the premium only (USD 3 a unit on day 1, was USD 13); alternate-bought surplus earns no salvage (v0.3 credited it at 60%); penalty cap 20% (was 10%); recovery budget USD 40 (was USD 120, not a reviewer value). Service, tier, downstream and supply-risk metrics are identical to v0.3 because only prices and salvage changed; only the cost block moved. The 20% cap never binds in any scripted episode (largest cumulative penalty on one order is USD 78 against USD 240), and the USD 40 budget never blocks a scripted policy.

## Regenerate
- Evidence: `PYTHONPATH=src python scripts/run_dynamic_demo_v4.py --out evidence/issue-36-v04`
- Hand ledgers: `python scripts/generate_hand_ledgers_v04.py` (`--check` compares with the committed file; a test does this). The script imports no project code.
- Tests: `PYTHONPATH=src python -m unittest discover -s tests -v`. Output is deterministic.

## Scenario by policy summary
Net cost is only the total of the cost block (expedite spend + alternate spend + penalties - salvage), shown as `v0.4 (v0.3)`. It sits beside, not instead of, the other metrics. Full per-metric tables: `scorecard.md`, `comparison.md`.

| Scenario | Policy | Expedite spend | Alternate spend | Penalties | Salvage | Net cost v0.4 (v0.3) | OTIF met | Cancelled units | Unit-days late | Primary reliance % | Cover days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sudden 5d | maintain | 0 | 0 | 18 | 0 | 18 (18) | 0/1 | 0 | 12 | 100 | 0 |
| sudden 5d | expedite on alert | 32 | 0 | 0 | 0 | 32 (32) | 1/1 | 0 | 0 | 100 | 0 |
| sudden 5d | alternate on alert | 0 | 24 | 0 | 0 | 24 (56) | 1/1 | 0 | 0 | 50 | 2 |
| sudden 5d | combo on alert | 16 | 12 | 0 | 0 | 28 (44) | 1/1 | 0 | 0 | 66 | 1 |
| sudden 5d | staged revisit | 36 | 0 | 0 | 0 | 36 (36) | 1/1 | 0 | 0 | 100 | 0 |
| warned, delayed 10d (custom) | maintain | 0 | 0 | 30 | 0 | 30 (30) | 0/1 | 0 | 20 | 100 | 0 |
| warned, delayed 10d (custom) | expedite on alert | 32 | 0 | 0 | 0 | 32 (32) | 1/1 | 0 | 0 | 100 | 0 |
| warned, delayed 10d (custom) | alternate on alert | 0 | 24 | 0 | 0 | 24 (104) | 1/1 | 0 | 0 | 50 | 2 |
| warned, delayed 10d (custom) | combo on alert | 16 | 12 | 0 | 0 | 28 (68) | 1/1 | 0 | 0 | 66 | 1 |
| warned, delayed 10d (custom) | staged revisit | 36 | 0 | 0 | 0 | 36 (36) | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d (custom) | maintain | 0 | 0 | 0 | 0 | 0 (0) | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d (custom) | expedite on alert | 32 | 0 | 0 | 0 | 32 (32) | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d (custom) | alternate on alert | 0 | 24 | 0 | 0 | 24 (104) | 1/1 | 0 | 0 | 50 | 2 |
| warned, no delay 10d (custom) | combo on alert | 16 | 12 | 0 | 0 | 28 (68) | 1/1 | 0 | 0 | 66 | 1 |
| warned, no delay 10d (custom) | staged revisit | 16 | 0 | 0 | 0 | 16 (16) | 1/1 | 0 | 0 | 100 | 0 |
| multi-tier cancel 10d | maintain | 0 | 0 | 67 | 0 | 67 (67) | 0/2 | 4 | 48 | 100 | 0 |
| multi-tier cancel 10d | expedite on alert | 32 | 0 | 28 | 0 | 60 (60) | 1/2 | 4 | 28 | 100 | 0 |
| multi-tier cancel 10d | alternate on alert | 0 | 24 | 13 | 0 | 37 (93) | 1/2 | 0 | 12 | 50 | 1 |
| multi-tier cancel 10d | combo on alert | 16 | 12 | 8 | 0 | 36 (76) | 1/2 | 0 | 8 | 66 | 0 |
| multi-tier cancel 10d | staged revisit | 36 | 0 | 28 | 0 | 64 (64) | 1/2 | 4 | 28 | 100 | 0 |
| slow expedite lane 10d | maintain | 0 | 0 | 78 | 0 | 78 (78) | 0/1 | 0 | 52 | 100 | 0 |
| slow expedite lane 10d | expedite on alert | 32 | 0 | 66 | 0 | 98 (98) | 0/1 | 0 | 44 | 100 | 0 |
| slow expedite lane 10d | alternate on alert | 0 | 24 | 6 | 0 | 30 (62) | 0/1 | 0 | 4 | 50 | 2 |
| slow expedite lane 10d | combo on alert | 16 | 12 | 30 | 0 | 58 (74) | 0/1 | 0 | 20 | 66 | 1 |
| slow expedite lane 10d | staged revisit | 36 | 0 | 66 | 0 | 102 (102) | 0/1 | 0 | 44 | 100 | 0 |

## Findings by metric (no overall winner is declared)
- **Recovery spend:** alternate is cheaper than expedite in every scenario (USD 24 against USD 32 for a full lot; combo USD 28). Maintain is lowest (USD 0).
- **Net cost:** alternate on alert is cheaper than expedite on alert in all 5 scenarios. The lowest net cost overall is maintain in 2 scenarios (sudden 5d, warned no delay), alternate on alert in 2 (warned delayed, slow lane) and combo on alert in 1 (multi-tier cancel, USD 36 against USD 37 for alternate).
- **Does maintain still win on net cost?** In 2 of 5 scenarios (in v0.3 it won in 3: sudden 5d, warned delayed, warned no delay). It no longer wins the warned-and-delayed scenario because a full alternate buy (USD 24) is below the delay penalty (USD 30).
- **Service (OTIF, unit-days late):** where a delay occurs in the short scenarios every acting policy ties at 0 unit-days late and maintain is worse; in multi-tier cancel combo on alert is lowest (8), and in the slow-lane scenario alternate on alert is lowest (4) while no policy meets OTIF. Unchanged from v0.3.
- **Tier impact and downstream impact:** alternate and combo avoid the cancellation in the multi-tier scenario (cancelled order value 0); expedite and staged revisit do not. Unchanged from v0.3.
- **Supply risk:** alternate lowers primary reliance to 50% and leaves the most ending cover, but those surplus components earn no salvage under the convention.
- Trade-offs between cost and the other metrics are flagged in `comparison.md`. This is a result of provisional numbers and an unresolved convention, not a recommendation.
