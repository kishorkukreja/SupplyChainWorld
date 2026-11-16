# Issue #35 results

Command: `PYTHONPATH=src python -m unittest discover -s tests` (raw output in `tests.log`): **301 tests, OK.** Before this change the suite had 266 tests; 35 are new (`tests/test_reference_cases_v1_1.py`: 5, independent enumeration with no production imports; `tests/test_static_v11.py`: 30, production checker, solver, schema, one per rule plus a table drift test). All 266 earlier tests are untouched and pass.

## Status

| Question | Answer |
| --- | --- |
| Implemented | Yes: schema, checker, reference solver, heuristic, 22 fixtures, docs, table |
| Tested | Yes: hand calculations, independent enumeration of every quantity vector, regression per rule |
| Practitioner-reviewed | **No. Awaiting re-review.** The owner-practitioner review is not independent and confirmed no number |
| Numeric values | All **PROVISIONAL, needs practitioner value** (docs/acceptance/static-v1.1-provisional-values.md) |
| Model ability | No claim. No model run, no paid call |

## Cases

22 fixtures in `fixtures/reference_cases_v1_1/`: ref-01 to ref-10 re-tuned v1.0 diagnostics, ref-11 to ref-22 new. Table in `docs/task-families/supplier-allocation-v1.1.md`. Every case has a hand calculation, expected submission, at least one known wrong submission, and an alternative valid answer (required for ref-01 to ref-10).

## Findings by rule

- A1: net requirement with safety stock and floor-rounded late credit inside a tolerance window (ref-01, 03, 10, 11, 12). Window edge, zero tolerance and held stock covered.
- A2: spend, quantity and per-item share, each declared per task; ref-13 passes under quantity share and fails under spend share (ref-06, 13, 14, 15).
- A3: equivalent-to-optimal band (absolute or fractional, inclusive edge) with exact gap reported; reliability and lead-time metrics reported separately (ref-02, 04, 16, 17).
- A4: estimated path (ref-17) and escalation for critical (ref-18) and high-value (ref-19) parts; ref-09 has no last known value; zero never substituted.
- A5: table-driven fixed charge by units and by goods value (ref-20); rounding removed. ref-21: v1.0 rounding yields 4.01 through a split artifact while 1.1 yields exact 4.0164, shown by running both checkers and solvers on the same numbers.
- A6: flagged MOQ excess justified only when the exact quantity is unreachable (ref-08); shelf-life cap binds inside an explicit allowance (ref-22).

## Known limits

- Provisional values and structural conventions (listed in the table) need the reviewer.
- The v1.1 stack is not wired into the environment, generation or dynamic modules; those still use 1.0.
- The solver is exhaustive enumeration for tiny instances; the heuristic is greedy and unproven.
- Where any eligible quote has a missing term and a feasible award exists from complete or permitted-estimate quotes, the solver returns that award; 1.0 always returned a clarification.
