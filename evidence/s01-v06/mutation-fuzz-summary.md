# S01 v0.6: mutation and fuzz summary, before (v0.5 checker) and after (v0.6 checker)

Nothing here is practitioner-reviewed and nothing claims model ability. These are software tests of synthetic rules.
Same campaign as `evidence/s01-audit/mutation-fuzz-summary.md` (same seeds, operators, generators and counting rules,
run by `scripts/s01_v06_summary.py` through `scripts/s01_audit_summary.py`). Deterministic. Regenerate:
`PYTHONPATH=src python scripts/s01_v06_summary.py`.

## Before and after in plain numbers

| measure | v0.5 checker (before) | v0.6 checker (after) |
|---|---|---|
| tampered recorded histories tried | 4174 | 4169 |
| rejected by the checker | 2373 | 4169 |
| accepted although tampered (survived) | 1801 | 0 |
| checker crashes on tampered histories | 0 | 0 |
| forged scorecards rejected | 500 of 500 | 500 of 500 |
| forged action logs rejected | 487 of 487 | 484 of 484 |
| garbage histories fed to the checker | 1000 | 1000 |
| checker crashes on garbage histories | 311 | 0 |
| garbage accepted as complete and feasible | 0 | 0 |
| damaged scenarios that crash the checker (instead of the documented ScenarioError) | 1 | 0 |
| malformed tool calls refused with state unchanged | 1000 of 1000 (changed: 0) | 1000 of 1000 (changed: 0) |

Same campaign, small difference in the v0.5 garbage-crash count (311 here, 321 in the audit summary): Hypothesis derandomizes from the test function, so the generated garbage differs slightly between the two scripts; the counting rules are identical. Honesty note on the crash count. The v0.6 checker has a last-resort guard: if an unexpected error escapes while it reads a recorded history it reports the history as malformed instead of crashing. In this campaign that guard fired on 0 of 1016 v0.6 checker calls during the fuzz section. Those were rejections, never a feasible verdict; a nonzero number means some garbage shape is rejected by the guard and not by a named check.

## Result against the requirement

* Every v0.6 history mutant rejected: YES (4169 of 4169).
* Zero checker crashes: YES.

Survivors v0.5: swap_adjacent on opening_before_notice x153; drop on opening_before_notice x152; duplicate on day_open x151; shift_day on day_open x146; drop on day_open x145; shift_day on opening_before_notice x143; duplicate on opening_before_notice x132; flip_accepted on day_open x130; flip_accepted on opening_before_notice x114; swap_adjacent on day_close x99; change_number on opening_before_notice x72; change_number on day_open x69

## History mutation detail (committed fixtures x declared policies)

A mutant is counted only if it changes what the record means (see tests/support/mutations.py).

| version | episodes | mutants | killed | survived | neutral (not counted) | verifier crashes |
|---|---|---|---|---|---|---|
| v0.5 | 25 | 4174 | 2373 | 1801 | 663 | 0 |
| v0.6 | 25 | 4169 | 4169 | 0 | 688 | 0 |

## Fuzz detail (1000 generated inputs per row, Hypothesis, derandomize)

| version | malformed tool calls | rejected | state changed | crashes | damaged scenarios | refused cleanly by simulator | accepted by simulator | scenario crashes | verifier scenario crashes | garbage histories | verifier history crashes | garbage accepted as complete+feasible |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v0.5 | 1000 | 1000 | 0 | 0 | 1000 | 994 | 6 | 0 | 1 | 1000 | 311 | 0 |
| v0.6 | 1000 | 1000 | 0 | 0 | 1000 | 994 | 6 | 0 | 0 | 1000 | 0 | 0 |
