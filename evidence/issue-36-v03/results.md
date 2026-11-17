# Issue #36 round 2 results: S01 dynamic family v0.3

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies on synthetic scenarios. No LLM was run and nothing here is a model-ability claim. Reviewed: no, not independent.

## Status
- Implemented: yes (every re-review change, see `plan.md`).
- Tested: yes. Full suite 387 tests, OK (301 existing plus 86 new). Raw output: `tests.log`.
- 25 episodes (5 scenarios x 5 policies): simulator, independent verifier and the hand ledgers agree on every one; every episode replays exactly and passes the leak scan.
- Practitioner-reviewed: **no.** The changes await the reviewer's re-review (owner-practitioner, not independent).

## Regenerate
- Evidence: `PYTHONPATH=src python scripts/run_dynamic_demo_v3.py --out evidence/issue-36-v03`
- Hand ledgers: `python scripts/generate_hand_ledgers_v03.py` (`--check` compares with the committed file; a test does this). The script imports no project code.
- Tests: `PYTHONPATH=src python -m unittest discover -s tests -v`. Output is deterministic.

## Scenario by policy summary
Net cost is only the total of the cost block (expedite spend + alternate spend + penalties - salvage). It is shown beside, not instead of, the other metrics. Full per-metric tables: `scorecard.md`, `comparison.md`.

| Scenario | Policy | Expedite spend | Alternate spend | Penalties | Salvage | Net cost | OTIF met | Cancelled units | Unit-days late | Primary reliance % | Cover days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sudden 5d | maintain | 0 | 0 | 18 | 0 | 18 | 0/1 | 0 | 12 | 100 | 0 |
| sudden 5d | expedite on alert | 32 | 0 | 0 | 0 | 32 | 1/1 | 0 | 0 | 100 | 0 |
| sudden 5d | alternate on alert | 0 | 104 | 0 | 48 | 56 | 1/1 | 0 | 0 | 50 | 2 |
| sudden 5d | combo on alert | 16 | 52 | 0 | 24 | 44 | 1/1 | 0 | 0 | 66 | 1 |
| sudden 5d | staged revisit | 36 | 0 | 0 | 0 | 36 | 1/1 | 0 | 0 | 100 | 0 |
| warned, delayed 10d (custom) | maintain | 0 | 0 | 30 | 0 | 30 | 0/1 | 0 | 20 | 100 | 0 |
| warned, delayed 10d (custom) | expedite on alert | 32 | 0 | 0 | 0 | 32 | 1/1 | 0 | 0 | 100 | 0 |
| warned, delayed 10d (custom) | alternate on alert | 0 | 104 | 0 | 0 | 104 | 1/1 | 0 | 0 | 50 | 2 |
| warned, delayed 10d (custom) | combo on alert | 16 | 52 | 0 | 0 | 68 | 1/1 | 0 | 0 | 66 | 1 |
| warned, delayed 10d (custom) | staged revisit | 36 | 0 | 0 | 0 | 36 | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d (custom) | maintain | 0 | 0 | 0 | 0 | 0 | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d (custom) | expedite on alert | 32 | 0 | 0 | 0 | 32 | 1/1 | 0 | 0 | 100 | 0 |
| warned, no delay 10d (custom) | alternate on alert | 0 | 104 | 0 | 0 | 104 | 1/1 | 0 | 0 | 50 | 2 |
| warned, no delay 10d (custom) | combo on alert | 16 | 52 | 0 | 0 | 68 | 1/1 | 0 | 0 | 66 | 1 |
| warned, no delay 10d (custom) | staged revisit | 16 | 0 | 0 | 0 | 16 | 1/1 | 0 | 0 | 100 | 0 |
| multi-tier cancel 10d | maintain | 0 | 0 | 67 | 0 | 67 | 0/2 | 4 | 48 | 100 | 0 |
| multi-tier cancel 10d | expedite on alert | 32 | 0 | 28 | 0 | 60 | 1/2 | 4 | 28 | 100 | 0 |
| multi-tier cancel 10d | alternate on alert | 0 | 104 | 13 | 24 | 93 | 1/2 | 0 | 12 | 50 | 1 |
| multi-tier cancel 10d | combo on alert | 16 | 52 | 8 | 0 | 76 | 1/2 | 0 | 8 | 66 | 0 |
| multi-tier cancel 10d | staged revisit | 36 | 0 | 28 | 0 | 64 | 1/2 | 4 | 28 | 100 | 0 |
| slow expedite lane 10d | maintain | 0 | 0 | 78 | 0 | 78 | 0/1 | 0 | 52 | 100 | 0 |
| slow expedite lane 10d | expedite on alert | 32 | 0 | 66 | 0 | 98 | 0/1 | 0 | 44 | 100 | 0 |
| slow expedite lane 10d | alternate on alert | 0 | 104 | 6 | 48 | 62 | 0/1 | 0 | 4 | 50 | 2 |
| slow expedite lane 10d | combo on alert | 16 | 52 | 30 | 24 | 74 | 0/1 | 0 | 20 | 66 | 1 |
| slow expedite lane 10d | staged revisit | 36 | 0 | 66 | 0 | 102 | 0/1 | 0 | 44 | 100 | 0 |

## Which recovery is cheapest on which metric (new numbers, no overall winner)
The reviewer's ranges change the cost relationship from v0.2. v0.2 priced alternate at about 1.7x expedite per unit; v0.3 prices it at about 3.3x on day 1 (USD 13 against USD 4), because an alternate unit costs base plus premium and the primary lot still arrives and is still paid. Read per metric:

- **Recovery spend:** expedite is the cheapest recovery in every scenario (whole lot USD 32 against USD 104). Maintain spends nothing.
- **Net cost:** doing nothing is cheapest in the sudden 5d, warned-delayed and warned-no-delay scenarios, because the penalty cap (10% of order value) and the 1.5% a day rate make the penalty small beside the recovery premiums. Expedite on alert is cheapest in the multi-tier scenario (60 against 67 for maintain, 64 staged, 76 combo, 93 alternate). Alternate on alert is cheapest in the slow-expedite-lane scenario (62 against 74 combo, 78 maintain, 98 expedite, 102 staged), where the expedite lane arrives only one day earlier than the delayed lot.
- **Service (OTIF, unit-days late):** in the three short scenarios all four recovery policies tie (OTIF met, zero late). In the multi-tier scenario combo has the fewest late unit-days (8) and, with alternate, the only zero cancellations. In the slow-lane scenario alternate has the fewest late unit-days (4 against 44 for expedite); no policy meets the order on time.
- **Downstream impact (cancelled order value):** alternate and combo avoid the cancellation of 4 standard-tier units (USD 320) in the multi-tier scenario; maintain, expedite and staged do not.
- **Supply risk:** alternate has the lowest primary reliance (50%) and the most ending cover (2 days), at the price of surplus stock.
- **Salvage sensitivity:** the alternate advantage depends on the part class. The slow-lane scenario is a standard part (USD 6 salvage on the 8 surplus units, USD 48). With a custom part (salvage 0) the alternate net cost is 110, above expedite (98) and maintain (78); a test asserts this.

The table is per-metric by design. No policy is best on every metric in any scenario, and no overall best policy is declared.

## What changed in outcomes against v0.2
- Under v0.2 numbers, reacting to a warned delay saved money against doing nothing. Under the reviewer's percent penalty with a cap, it does not on net cost (maintain 30 against expedite 32 in the warned-delayed scenario); it still wins on OTIF and lateness. This follows from the chosen finished-good value (USD 100 against a USD 10 component) and the unconfirmed cap, both PROVISIONAL.
- The warned-no-delay twin is still the case where maintain is cheapest (0) and every reactive policy spends 16 to 104 for no service gain.
- Signal: the level `medium` is identical in both twins, and a paired test shows the observation streams are identical until the firm notice.

## Evidence index
| File | Content |
|---|---|
| `plan.md` | scope, design, verification approach |
| `timeline.txt` | chronological actions and events for all 25 episodes |
| `state-ledger.csv`, `state-ledger.json` | per-day ledger rows (independent verifier derivation) |
| `scorecard.md`, `scorecard.json` | per-metric scorecards, flat and full blocks |
| `comparison.md`, `comparison.json` | per-metric comparison with trade-off flags |
| `checks.json` | verifier results, hand-ledger match, corruption cases, rejection probes, leak scan, paired-signal check |
| `replay.json`, `replay.log` | replay command and per-episode results |
| `experience-record.json`, `.md` | one observable record (warned and delayed, staged revisit), scanned for private answers |
| `transcripts.json` | full runner transcripts for all 25 episodes |
| `gate-report.md`, `report.html` | gate table and a rendered summary |
| `tests.log` | full unittest run |

Hand ledgers: `fixtures/dynamic/v0.3/hand-ledgers.json`, produced by `scripts/generate_hand_ledgers_v03.py`.

## Limits
- All values are provisional and unreviewed; the cost ordering depends on authored choices (finished-good value, cap, salvage, lead times in the slow-lane scenario).
- The slow-lane scenario was authored so that alternate is clearly cheaper; its expedite lead time is not a reviewer value.
- Open reviewer questions are listed in `docs/acceptance/dynamic-v0.3-provisional-values.md` section 3, notably whether an alternate buy is priced in full (this build) or only as a premium.
- G9 (honest demonstration) stays open until the reviewer re-reviews.
