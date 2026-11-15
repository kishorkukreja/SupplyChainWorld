# Issue #22 implementation plan

Goal: implement the minimum operational state and time engine for the supplier-delay scenario specified in `docs/acceptance/dynamic-supplier-delay-v0.1.md` on main. Its numbers are provisional synthetic assumptions; practitioner review is pending.

1. Represent inventory, finished goods, customer deliveries, purchase-order arrival events, production releases, budget, penalties and a scenario-configured positive day horizon.
2. Process the day-one delay, recovery commitments, daily production, shipping, assessments and receipts in declared chronological order.
3. Reject invalid and duplicate actions without mutating operational state, while recording attempts.
4. Exercise all three five-day hand-worked policy ledgers, longer 10- and 15-day runs, edge conditions and deterministic reset.
5. Preserve actual logs and ledgers for review. Separate independent verification, agent-tool integration and end-to-end experience admission remain issues #24–#26.
