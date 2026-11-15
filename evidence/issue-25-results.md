# Issue #25 implementation evidence

## Implemented

[`src/supplychainworld/dynamic_verifier.py`](../src/supplychainworld/dynamic_verifier.py) exposes `verify_episode(scenario, history, horizon_days=..., scorecard=None, actions=None)` and returns a report with `feasible`, `violations` (code, day, message), a derived per-day `ledger`, observed `metrics`, separate `outcome` quality figures and any ignored self-reported status keys. It does not import the simulator or the scripted baselines (an AST test enforces this), keeps its own copy of the fixture defaults and re-implements the written rules: receipts at opening, notice, one recovery commitment by the deadline within budget, one release per day within capacity, available material and the 12-unit order, close-of-day production and shipment from the due day, penalty per undelivered unit at each close from the due day, and episode end at the configured horizon.

Checks: component and finished-goods conservation and non-negative stock computed directly from claimed states; receipt day and quantity; notice day; each command's legality and whether the record's accepted flag agrees; rejected commands leave the ledger unchanged; per-close production, shipments, states, cumulative penalty and spend; final comparison cost; scorecard against the derived values; optional action-log agreement. Missing, extra and reordered business events are reported. Unobserved metrics (on-time delivery before the due day closes, receipts after the horizon, outcome of an unfinished episode) are `None`, distinct from an observed zero.

## Tested

Hand-worked per-day ledgers are in [`fixtures/dynamic/verifier-hand-ledgers.json`](../fixtures/dynamic/verifier-hand-ledgers.json) for the five-day and fifteen-day fixtures under maintain/expedite/alternate; the verifier's derived ledger equals them day by day (costs 120/24/40 and 200/24/40). Other tests cover short horizons (2 days, and 9 days of the fifteen-day fixture), truncated records, no-disruption operation, a hand-driven slower-production episode that is feasible but costlier, legal rejected commands, and the adversarial cases: premature receipt (including a day-12 receipt claimed on day 11), extra or missing receipt, production over capacity, without material and beyond the order, duplicate recovery commitment and duplicate release, late, premature and over-budget recovery, incorrect scorecard and penalty, tampered states/shipments/phases/arrival dates/deleted closes, forged `passed` flags, and a simulator whose penalty rate was sabotaged (its own scorecard says 60, the verifier derives 120 and rejects it).

Actual local command: `PYTHONPATH=src python -m unittest discover -s tests -v` under Python 3.13.18. All 60 tests passed (39 existing, 21 new). See [raw output](issue-25-tests.log).

## Not claimed

- Practitioner review: none. Fixture quantities, penalty schedule and rules are provisional engineering assumptions.
- The verifier checks a recorded trace against the written rules; it does not prove the simulator correct in general, and its notice text and event structure are matched to the current history format. It checks one synthetic one-item scenario family; this is not a generalization, model-performance or training-improvement claim.
- Event replay from raw agent commands through the issue #24 runner, hostile-agent isolation, and the full scenario gate (#26) are separate work. No screenshots were produced; the raw log is supplied instead. No paid model call, teacher data or fine-tuning was used.
- Receipt, notice and cost checks assume the history is a complete record. A trace that omits a command is reported as a missing or mismatched event, not silently accepted.
