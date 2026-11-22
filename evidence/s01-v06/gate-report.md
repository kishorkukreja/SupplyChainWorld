# S01 v0.6 gate report

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, practitioner review: none (owner review only, not independent).

Regenerate: `PYTHONPATH=src python scripts/run_dynamic_demo_v6.py --out evidence/s01-v06`. Output is deterministic.

| Gate | Status | Evidence |
|---|---|---|
| G1 Coherent initial world | Evidence produced, unreviewed | Initial observation (state, contract terms by order, tier rules, salvage rate, budget, the conventions block, tool definitions, schema and runtime version) recorded per episode in transcripts.json. |
| G2 Actual time progression | Evidence produced, unreviewed | Every episode logs day_open then day_close for each day 1..horizon (5 and 10) and ends with episode_complete. |
| G3 Executed disruption, signal and recovery | Evidence produced, unreviewed | Sudden scenarios show only a firm notice; warned scenarios show a possible-delay signal first and a firm notice later that either confirms a delay or confirms on-time arrival. Commitments change lot timing and create distinct lots (see timeline.txt). |
| G4 Consequential state changes (hand ledgers) | Evidence produced, unreviewed | The independent v0.6 per-day ledger equals the hand-worked ledgers for all 25 episodes (received, produced, shipped, stock, delivered, penalties, spend, cancellations) and passes conservation checks. The hand ledgers come from scripts/generate_hand_ledgers_v06.py, which imports no project code. |
| G5 Per-metric scorecards (hand metrics) | Evidence produced, unreviewed | Per-metric scorecards (cost, service, tier impact, downstream, supply risk) equal the hand-worked per-episode metrics. Same initial world and disruption per scenario across the five declared policies. |
| G6 Independent checking | Evidence produced, unreviewed | dynamic_verifier_v6 re-derives each episode from commands and imports no simulator code (AST test). Corruption cases per episode: forged scorecard, premature receipt, wrong penalty, deleted close, duplicate commitment, repeated id-less purchase, over-budget combination, forged opening state, deleted opening record, forged horizon and version fields, non-mapping details, malformed scenario, malformed action log, leaked signal (warned scenarios), forged pass flags. |
| G7 Failure behavior | Evidence produced, unreviewed | Through the tool interface: hidden-state probe, duplicate action id, the same purchase repeated without an id, a reserved id, over-budget combination, overcapacity, duplicate release, closed offer window, production without material. Each rejection leaves state unchanged and stays auditable. Premature receipt, wrong penalty and leaked signals are proven at checker level. |
| G8 Replay and no-leak | Evidence produced, unreviewed | Each transcript replays from recorded calls with identical state sequence and scorecard. All observations in all 25 episodes (conventions block included) pass the private-answer and outcome-leak scan; warned-and-delayed and warned-and-no-delay episodes are observation-identical until the firm notice. |
| G9 Honest demonstration | Partial: labels stated; practitioner review none | Labels and limitations published. No practitioner review has occurred (owner review only, not independent); the gate cannot be called passed. |

Implemented: yes. Tested: yes (automated, synthetic fixtures). Practitioner-reviewed: no.

No model-ability claim. No overall best policy is declared. The warned scenarios use an authored hint value that is not calibrated.
