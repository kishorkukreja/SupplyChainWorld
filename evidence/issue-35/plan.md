# Issue #35 plan: static supplier-allocation rules 1.1

Objective: implement owner decisions A1 to A7 as schema/rules version 1.1 beside the frozen 1.0, with versioned fixtures, hand calculations, regression tests and a provisional-values table for re-review.

Approach
- New modules only: `schemas_v11.py`, `verification_v11.py`, `solvers_v11.py`. v1.0 code, fixtures and evidence untouched. No `dynamic_v2*` file touched.
- Checker independent of the solver; a separate test enumerates every quantity vector with no production imports.
- 22 fixtures in `fixtures/reference_cases_v1_1/`: ref-01 to ref-10 re-tuned, ref-11 to ref-22 new (late credit, safety stock, three concentration measures, tolerance, estimated path, two escalate paths, varying fixed charge, rounding difference, shelf-life cap).
- Provisional values table generated from the fixtures by script; a test fails on drift.

Decisions applied: A1 safety stock plus late inbound credit in a tolerance window; A2 three measures declared per task; A3 tolerance band, exact gap still reported, non-cost metrics separate; A4 request first, estimate under the approval limit for non-critical parts, else escalate, never zero; A5 table-driven fixed charge, rounding removed, exact Decimal; A6 flagged MOQ excess, shelf-life cap; A7 re-tuned cases.

Status wording: implemented and tested; practitioner-reviewed: no, awaiting re-review. No model-ability claims. No paid calls.
