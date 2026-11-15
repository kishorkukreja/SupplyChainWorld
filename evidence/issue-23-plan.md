# Issue #23 plan

## Objective

Turn the supplier-delay sketch into explicit public engineering fixtures and observable scripted baselines for five-day and genuinely later-event fifteen-day operating situations. Exercise actual dynamic transitions over time; preserve the previous default engine API. Scenarios and numbers are synthetic, unvalidated assumptions, not practitioner-approved training data.

## Plan

1. Parameterize the existing one-item engine's scenario quantities, event dates, due date, production capacity, recovery options and penalty rules. Preserve `OperationalWorld()` and `OperationalWorld(horizon_days=...)` as the original five-day fixture. Define and validate clock/event semantics before writing policies.
2. Create explicitly versioned fixture inputs and separately stored hand-calculated expected ledgers. A fifteen-day fixture must make the notice, recovery and arrival occur after day five; a horizon-only extension is insufficient.
3. Implement three policies that use public observations and the same inputs, not the expected ledger or hidden future event schedule. Execute deterministic episodes and capture every action, notice, receipt, state, cost and daily close.
4. Independently verify initial/policy-identical observations, event timing, daily quantities, costs, dates, nonnegative inventory, allowed actions and exact expected outcomes. Retain existing unit tests and regression compatibility.
5. Publish sanitized actual test logs and runnable command. No LLM/teacher dataset is generated, no paid calls, no practitioner signoff claimed. Capture actual screenshots if the available environment permits; do not manufacture them.

## Scope and prerequisite

PR #27 is merged; issue #22 is still open. Treat dependent interface changes as provisional until its acceptance evidence is reconciled. Independent dynamic verification (#25), a secure agent interface/replay (#24), general scenario flexibility and the complete scenario acceptance gate (#26) remain separate. This work is not a production simulator.
