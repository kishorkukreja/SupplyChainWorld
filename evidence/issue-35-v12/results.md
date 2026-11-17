# Issue #35 results: static rules 1.2

Command: `PYTHONPATH=src python -m unittest discover -s tests` (raw output in `tests.log`): **345 tests, OK.** The 301 earlier tests are untouched and pass; 44 are new (`tests/test_reference_cases_v1_2.py`: 7, independent enumeration with no production imports; `tests/test_static_v12.py`: 37, production schema, checker and solver, one group per rule, plus a table drift test).

## Status

| Question | Answer |
| --- | --- |
| Implemented | Yes: schema, checker, reference solver, heuristic, 33 fixtures, docs, table |
| Tested | Yes: hand calculations, independent enumeration, regression per rule |
| Practitioner-reviewed | **No. Not independent. Awaiting re-review.** The reviewer gave directions and ranges, no point values |
| Numeric values | All **PROVISIONAL, needs practitioner value** (docs/acceptance/static-v1.2-provisional-values.md) |
| Model ability | No claim. No model run, no paid call |

## Changes by rule

- C1: safety stock from service level, per-period demand std and lead time (z-table 90/95/97.5/99%), exact ceiling (ref-23: 9.8 gives 10; ref-24: exactly 49 stays 49); override kept; checker (Fraction) and solver (Decimal sqrt) agree over a grid.
- C2: late window 3 days, credit 50% (ref-01 at the 3-day edge, ref-11).
- C3: tolerance tiers by optimum / reference value (3% / 2% / 1%); edges at 49.00, 50.00, 499.00, 500.00 (ref-25, 16, 27, 26); schema rejects a looser tier for larger orders; exact gap still reported.
- C4: estimate allowed at or below 5,000.00 (ref-28 exactly 5,000.00); 5,000.40 escalates (ref-29); critical still escalates (ref-18); 5,200.00 escalates (ref-19).
- C5: MOQ excess needs the flag and, above 500.00 excess value, a granted approval reference (ref-31 with, ref-32 without: request approval and escalate, ref-33 exactly at the threshold: flag only).
- C6: ask first even when complete alternatives exist (ref-29, ref-30); where the estimate path covers a quote, award around remains allowed (ref-17, ref-28).
- C7: spend share is the default; quantity and per-item share only when the task declares them (ref-13, ref-14).
- C8: no rounding (ref-21, tolerance tiers set to 0% there).

## Known limits

- All numeric values and structural conventions need the reviewer; the MOQ approval threshold and tier constants were not given at all.
- The clarification-for-approval path does not test the excess value against the threshold in the checker.
- Approval is a visible granted record, not a workflow.
