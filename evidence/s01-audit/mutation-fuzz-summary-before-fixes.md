# S01 audit: mutation and fuzz summary (before fixes)

Seeded and deterministic. Regenerate: `PYTHONPATH=src python scripts/s01_audit_summary.py`.

## History mutation (committed fixtures x declared policies, independent verifier)

A mutant is counted only if it changes what the record means; accepted zero-unit releases, rejected-command
records and unknown record kinds are "neutral" (see tests/support/mutations.py). Killed = verifier reports a violation.

| version | episodes | mutants | killed | survived | neutral (not counted) | verifier crashes | scorecard forgeries killed | action-log forgeries killed |
|---|---|---|---|---|---|---|---|---|
| v0.1 | 6 | 1022 | 589 | 433 | 140 | 0 | 120/120 | 117/117 |
| v0.2 | 20 | 3297 | 1992 | 1305 | 564 | 0 | 400/400 | 386/386 |
| v0.3 | 25 | 4155 | 2425 | 1730 | 676 | 0 | 500/500 | 479/479 |
| v0.4 | 25 | 4142 | 2400 | 1742 | 689 | 0 | 500/500 | 480/480 |
| v0.5 | 25 | 4174 | 2373 | 1801 | 663 | 0 | 500/500 | 487/487 |

Survivors v0.1: flip_accepted on day_open x37; swap_adjacent on day_close x37; shift_day on opening_before_notice x36; duplicate on day_open x35; drop on day_open x34; shift_day on day_open x30; duplicate on opening_before_notice x30; drop on opening_before_notice x29; swap_adjacent on opening_before_notice x29; flip_accepted on opening_before_notice x26; swap_adjacent on day_open x21; change_number on day_open x17

Survivors v0.2: shift_day on opening_before_notice x122; duplicate on day_open x111; shift_day on day_open x106; drop on opening_before_notice x103; swap_adjacent on opening_before_notice x101; drop on day_open x99; flip_accepted on day_open x97; flip_accepted on opening_before_notice x97; duplicate on opening_before_notice x91; swap_adjacent on day_close x74; swap_far on opening_before_notice x47; change_number on day_open x47

Survivors v0.3: flip_accepted on day_open x152; drop on day_open x149; drop on opening_before_notice x135; shift_day on opening_before_notice x134; flip_accepted on opening_before_notice x134; duplicate on opening_before_notice x133; swap_adjacent on opening_before_notice x132; duplicate on day_open x128; shift_day on day_open x111; swap_adjacent on day_close x87; change_number on day_open x80; change_number on opening_before_notice x68

Survivors v0.4: flip_accepted on day_open x155; shift_day on day_open x150; drop on day_open x148; flip_accepted on opening_before_notice x141; drop on opening_before_notice x139; duplicate on day_open x125; swap_adjacent on opening_before_notice x125; shift_day on opening_before_notice x123; duplicate on opening_before_notice x117; swap_adjacent on day_close x94; change_number on opening_before_notice x72; swap_far on day_open x63

Survivors v0.5: swap_adjacent on opening_before_notice x153; drop on opening_before_notice x152; duplicate on day_open x151; shift_day on day_open x146; drop on day_open x145; shift_day on opening_before_notice x143; duplicate on opening_before_notice x132; flip_accepted on day_open x130; flip_accepted on opening_before_notice x114; swap_adjacent on day_close x99; change_number on opening_before_notice x72; change_number on day_open x69

## Fuzz campaign (1000 generated inputs per row and version, Hypothesis, derandomize)

| version | malformed tool calls | rejected | state changed | crashes | damaged scenarios | refused cleanly by simulator | accepted by simulator | scenario crashes | verifier scenario crashes | garbage histories | verifier history crashes | garbage accepted as complete+feasible |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v0.1 | 1000 | 1000 | 0 | 0 | 1000 | 950 | 50 | 0 | 0 | 1000 | 286 | 0 |
| v0.2 | 1000 | 1000 | 0 | 0 | 1000 | 992 | 8 | 0 | 3 | 1000 | 321 | 0 |
| v0.3 | 1000 | 1000 | 0 | 0 | 1000 | 991 | 9 | 0 | 1 | 1000 | 321 | 0 |
| v0.4 | 1000 | 1000 | 0 | 0 | 1000 | 991 | 9 | 0 | 1 | 1000 | 321 | 0 |
| v0.5 | 1000 | 1000 | 0 | 0 | 1000 | 994 | 6 | 0 | 1 | 1000 | 321 | 0 |

## Hypothesis example budget of the audit tests (ci profile)

Total examples requested per run: None.

| module | Hypothesis tests | examples requested |
|---|---|---|

