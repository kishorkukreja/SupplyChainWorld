# Issue #3 implementation plan

Implements spec sections 3–6 and issue #3; prerequisite #2 is being authored concurrently. Domain and foundation agents explicitly agreed the world/submission JSON interface before implementation. Schema version is `1.0`. All work is provisional until #2 evidence is accepted.

Use Python 3.12 and pinned Pydantic 2.13.4 (available locally), with strict integral quantities, ISO dates, exact Decimal money, forbidden unknown fields, reference checks, and versioned world/task/action/result/trajectory/verification/export contracts. Add offline unittest checks and CI that installs dependencies then runs without provider access. Validate valid records and adversarial invalid records; document decisions in ADR 0001. No optimizer or checker business implementation belongs to this issue.
