# Issue #24 plan

## Objective

Expose the S01 operational world to an agent through explicit tools, and run it in an observable multi-day loop that keeps a chronological, replayable record of every attempt. Scenarios and numbers remain the synthetic, unvalidated assumptions from #22/#23. No paid model calls, no live ERP writes.

## Plan

1. Add an additive module `src/supplychainworld/agent_runner.py`. The existing `dynamic.py` and `baselines.py` are not modified.
2. Tool layer with authority classes (read, commit, advance): `read_state`, `read_recovery_offers`, `read_scorecard` (after completion only), `commit_recovery`, `release_production`, `advance_day`. The agent view shows the configured horizon, current simulated day and phase, visible state and rules, tool definitions and the recovery deadline once offers are visible. Deadlines and budget are enforced by the world, which stays the authority on state.
3. Runner records every attempt (accepted or rejected) with day, tool, arguments, outcome, category, visible state before and after, state changes and newly produced events. Agent exceptions and attempt budgets end the run with the history preserved.
4. Reject hidden-state probes (tool names, sections and arguments that name scenario, future schedule, history, reset and similar), unknown tools, unexpected arguments, ungranted authority, reused action ids, repeated commitments, invalid quantities and choices, late or over-budget recovery, production without material, and actions after completion. Rejections never change operational state.
5. `replay(transcript, world_factory)` re-runs the recorded calls on a fresh world and requires identical views, outcomes, state changes, final state and scorecard.
6. Tests for each rejection case, five-day and fifteen-day horizons, recovery changing actual future receipts, replay and tamper detection, failure-history retention.

## Limits

This is an information and authority boundary for in-process policies. It is not hostile-code isolation: Python code in the same process could inspect the world object. Independent verification (#25) and the full scenario gate (#26) are separate.
