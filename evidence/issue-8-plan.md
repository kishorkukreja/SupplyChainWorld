# Issue 8 plan

Implement spec sections 3, 5, 8 and 9 as deterministic structured generation, independently admitted using the reference solver and business checker. Read existing schema, solver, checker and reference fixtures before implementation. No paid calls or changes to schema contracts.

Dependency: issue 7 owns lineage assignment and overlap admission. Agree its interface before population expansion; lineages must be assigned to splits before variants exist. Generation will accept an explicit preassigned lineage/split and the smoke population will use split-specific ancestry. Public worlds/tasks and private construction/reference data remain separate objects.

Generate small multi-item, multi-supplier instances with controlled variants for inventory/inbound timing, eligibility, MOQ/multiples, fixed/variable freight, tight budget, concentration, allowed excess, missing commercial terms, and provable capacity shortfalls. Admission rejects unresolved solver outcomes, wrong task types, or independent checker failures. Record bounded retry/rejection counts and provenance. Verify repeatability, meaningful variation, expected outcome coverage, checker acceptance and cross-split ancestry rejection; document reproducible commands and actual results.
