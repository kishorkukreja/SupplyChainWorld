# Issue #35 plan: static supplier-allocation rules 1.2 (re-review round 2)

Objective: apply the owner-practitioner re-review of 2026-11-17 (docs/reviews/2026-11-17-practitioner-re-review-17.md, section "Static supplier allocation v1.1") as a new version 1.2 beside 1.0 and 1.1. The re-review is not independent and gave directions and ranges, not point values, so every number stays PROVISIONAL, needs practitioner value. Reviewed by a practitioner: no.

Approach
- New modules only: `schemas_v12.py`, `verification_v12.py`, `solvers_v12.py`; v1.0 and v1.1 code, fixtures, tests and evidence untouched. Unchanged helpers are imported from the 1.1 modules. No `*_v3` or dynamic file touched.
- Rules: C1 service-level safety stock with a fixed z-table, exact integer arithmetic (smallest s with s*s >= (z*std)^2*lead), override kept; C2 3-day late window; C3 tolerance tiers 3/2/1% keyed on optimum / reference value, monotone; C4 estimate at or below the 5,000.00 limit; C5 MOQ excess needs a flag and, above 500.00 excess value, a granted approval reference; C6 ask clarification first, never award around a gap the estimate path does not cover; C7 spend share default, other measures only when the task declares them; C8 no rounding.
- Fixtures: 22 re-tuned plus 11 new (service-level safety stock x2, tier x3, at-limit estimate, above-limit escalate, ask-first despite alternatives, MOQ approval with, without and at the threshold) built by `scripts/build_static_v12_fixtures.py`; hand calculation, known-wrong and alternative-valid answers in every case.
- Checker independent of solver; a test with no production imports enumerates every quantity vector and computes safety stock a third way.
- Provisional-values table generated from the fixtures with a "changed from v1.1" column; a test fails on drift.

Status wording: implemented and tested; practitioner-reviewed: no, not independent, awaiting re-review. No model-ability claims. No paid calls.
