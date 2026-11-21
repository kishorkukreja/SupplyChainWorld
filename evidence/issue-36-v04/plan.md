# Issue #36 round 3 plan: S01 dynamic family v0.4 (owner re-review)

Source: owner-practitioner re-review, round 3 (decisions relayed to the implementer). Reviewer is the project owner, **not independent**. All numbers are PROVISIONAL, needs practitioner value. Reviewed: no.

## Constraints
- v0.1, v0.2 and v0.3 files, static files, fixtures, tests and evidence are not edited. v0.4 is built in new `*_v4` modules and `fixtures/dynamic/v0.4/`, reusing v0.3 code by import (scenario validation, world machinery, runner, scripted policies).
- All earlier tests keep passing.
- Cost, service, tier impact, downstream impact and supply risk stay separate metrics; no overall best policy is declared.
- No model-ability claim. Scripted policies only.

## Changes applied
| Round 3 decision | Mechanism | Where |
|---|---|---|
| Compare premiums only: alternate incremental cost is its premium over the primary unit cost (USD 3 a unit on day 1), comparable with the expedite premium (USD 4) | `ScenarioV4.alternate_unit_cost` = `base x premium / 100` | `dynamic_v4.py`, verifier `offer` |
| Open question the reviewer has not answered: base cost and surplus of the alternate lot. Convention used: base cost of any recovery lot is cost-neutral; alternate-bought surplus earns no salvage | leftover components are presumed alternate-bought first; `eligible = ending - min(ending, alternate received)` | `OperationalWorldV4._salvage_split`, verifier `eligible` |
| Penalty cap 20% (was 10%); 1.5% a day on the undelivered part kept | fixture value `penalty_cap_pct` 20 | `fixtures/dynamic/v0.4/scenarios.json` |
| Carried forward | part-class salvage 60/0, later-day premiums, slow-lane scenario, percent basis, weights 5:1, cancel +6 days, qualitative hint, metric proxies | unchanged |
| Recovery budget | USD 40 (was 120) so the budget still binds for a full expedite plus a full alternate buy; not a reviewer value | fixtures |

## Verification approach
1. Fresh hand-worked ledgers for 25 episodes from `scripts/generate_hand_ledgers_v04.py` (imports no project code; AST test; a test that the committed JSON equals its output).
2. Independent verifier `dynamic_verifier_v4` imports no project code (AST test) and re-derives each ledger from commands.
3. Simulator, verifier and hand ledgers compared for all 25 episodes.
4. Adversarial tests carried from v0.3, plus: a simulator that credits alternate surplus, a simulator that charges the whole alternate price, a test that no policy can profit from buying surplus (salvage set to 100%, every alternate quantity 1 to 8, every fixture).
5. Replay of every episode on a fresh world; leak scan of every episode; warned twins observation-identical until the firm notice.

## Out of scope
Practitioner values, an LLM run, any ability claim, and the reviewer's answer to the unresolved alternate-lot convention.
