# Issue #25 plan

## Objective

Add an independent checker for the S01 supplier-delay episodes (scenario gates G5 to G8 in the [scenario contract](../docs/acceptance/dynamic-supplier-delay-v0.1.md)). It must verify component and finished-goods conservation, event timing, receipts, capacity, customer shipments, budget and cost across the configured horizon, including end-of-horizon and events after day 5, without trusting the simulator's own results.

## Plan

1. Write a verifier module that does not import `dynamic.py` or `baselines.py`. It takes a plain scenario mapping, the recorded event history and optional claimed scorecard and action log.
2. Re-derive a ledger from the recorded commands with an independent implementation of the written rules. Compare it with the claimed receipts, notice, command acceptance, daily closes, states, penalties and final cost. Separately run conservation invariants on the claimed states.
3. Separate feasibility from quality: a legal but costlier episode is feasible, its cost is reported under `outcome`. Quantities the configured horizon never observed (for example on-time delivery when the due day is past the horizon) are `None`, not zero. Self-reported pass flags are ignored and listed.
4. Hand-work per-day ledgers for both fixtures and all three policies (`fixtures/dynamic/verifier-hand-ledgers.json`) and compare the verifier ledger with them.
5. Add adversarial tests: premature receipt, production beyond capacity, material or order quantity, incorrect cost, duplicate commitment, late/premature/over-budget recovery, state and event tampering, forged pass flags and a simulator with a deliberately wrong penalty rule.

## Scope

Additive: new module, fixture file and tests. `dynamic.py` and `baselines.py` are unchanged. Issue #24 (tool and runner interface) and #26 (scenario flexibility gate) remain separate. The checker covers only this one-item synthetic fixture and its provisional rules; no live ERP, paid model call, teacher data or fine-tuning is involved.
