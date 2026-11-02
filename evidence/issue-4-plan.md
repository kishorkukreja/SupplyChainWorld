# Issue #4 independent verification plan

Implements spec.md §§3, 5–7. Dependency #3 schema API and #2 case semantics are being explicitly coordinated before dependent implementation. No solver model-building or optimization implementation will be imported.

1. Recompute net requirements using usable stock and on-time committed inbound; validate unique integral item/supplier allocations, units, eligibility, capacities, MOQ, multiples and explicit excess allowances.
2. Recompute Decimal line amounts, rounded half-up per line to cents, variable freight and once-per-selected-supplier fixed charges under the agreed business playbook. Check supplied cost and hard budget/concentration constraints.
3. Verify expected outcome separately from economic quality. Clarification must name a genuinely missing permitted field; infeasibility must carry independently verifiable capacity evidence, never a timeout claim. Reference bounds are only used for objective gaps.
4. Exercise known-invalid submissions, ties, rounding, fixed fees, units, duplicates, exception evidence and ID invariance. Record actual test commands/results after implementation.

Review status: synthetic engineering validation only; practitioner/domain signoff remains pending.
