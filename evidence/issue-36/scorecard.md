# Per-metric scorecards (scripted baselines, synthetic scenarios)

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, practitioner-reviewed: no.

| fixture | policy | net_cost | recovery_spend | service_penalties | otif_orders_met | on_time_units | unit_days_late | priority_weighted_unit_days_late | cancelled_order_value | pending_inbound_units | primary_reliance_pct | ending_cover_days_floor | salvage_credit | cancelled_units | verifier_feasible | matches_hand_ledger | replay_reproduced |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s02-sudden-5d | maintain | 120 | 0 | 120 | 0 | 4 | 12 | 36 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-sudden-5d | expedite_on_alert | 24 | 24 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-sudden-5d | alternate_on_alert | 24 | 40 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 50 | 2 | 16 | 0 | True | True | True |
| s02-sudden-5d | combo_on_alert | 24 | 32 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 66 | 1 | 8 | 0 | True | True | True |
| s02-sudden-5d | staged_revisit | 28 | 28 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-warned-delayed-10d | maintain | 50 | 0 | 50 | 0 | 4 | 20 | 60 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-warned-delayed-10d | expedite_on_alert | 24 | 24 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-warned-delayed-10d | alternate_on_alert | 24 | 40 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 50 | 2 | 16 | 0 | True | True | True |
| s02-warned-delayed-10d | combo_on_alert | 24 | 32 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 66 | 1 | 8 | 0 | True | True | True |
| s02-warned-delayed-10d | staged_revisit | 28 | 28 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-warned-no-delay-10d | maintain | 0 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-warned-no-delay-10d | expedite_on_alert | 24 | 24 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-warned-no-delay-10d | alternate_on_alert | 24 | 40 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 50 | 2 | 16 | 0 | True | True | True |
| s02-warned-no-delay-10d | combo_on_alert | 24 | 32 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 66 | 1 | 8 | 0 | True | True | True |
| s02-warned-no-delay-10d | staged_revisit | 12 | 12 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s02-multitier-cancel-10d | maintain | 64 | 0 | 72 | 0 | 4 | 32 | 48 | 160 | 0 | 100 | 1 | 8 | 8 | True | True | True |
| s02-multitier-cancel-10d | expedite_on_alert | 48 | 24 | 24 | 1 | 12 | 12 | 12 | 80 | 0 | 100 | 0 | 0 | 4 | True | True | True |
| s02-multitier-cancel-10d | alternate_on_alert | 56 | 40 | 24 | 1 | 8 | 12 | 12 | 0 | 0 | 50 | 1 | 8 | 0 | True | True | True |
| s02-multitier-cancel-10d | combo_on_alert | 48 | 32 | 16 | 1 | 12 | 8 | 8 | 0 | 0 | 66 | 0 | 0 | 0 | True | True | True |
| s02-multitier-cancel-10d | staged_revisit | 52 | 28 | 24 | 1 | 12 | 12 | 12 | 80 | 0 | 100 | 0 | 0 | 4 | True | True | True |
