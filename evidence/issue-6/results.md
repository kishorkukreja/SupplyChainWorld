# Issue 6 verification results

Implemented `src/supplychainworld/environment.py` and `tests/test_environment.py` against the agreed issue 3 typed contracts. The issue 6 execution plan is [../issue-6-plan.md](../issue-6-plan.md).

Executed offline on 2026-11-02:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_environment.py -v
```

Result: **7 tests passed**. Tests execute public reference worlds and cover world-derived artifact/query consistency; observation sanitization; denied traversal and hidden-answer artifact names; malformed, stale, duplicate and unauthorized actions; invalid commercial float values; no state/audit mutation on invalid actions; award and exception terminal state; reset isolation; defensive copies; explicit known-missing-field clarification escalation; deterministic audit replay and rejection of a changed replay result.

The environment does not issue purchase orders or decide correctness. A submitted infeasibility claim is recorded for the independent checker. It receives World and Task records, never expected answers or construction truth. Its agent tool dispatcher offers only named queries, exact catalog artifact reads, clarification and submission. It has no filesystem, network, eval, private solver or grader tool.

Scope: fixed world reset records a seed but does not generate variants; generation is downstream. The only supported clarification policy is `record_and_escalate`, with no invented commercial response. Validation errors do not alter state or accepted-event audit history; runner-level trajectories may additionally record rejected attempts. Replay covers accepted state transitions with deterministic simulated business dates and no wall-clock fields.
