# Per-metric scorecards (scripted baselines, synthetic scenarios)

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, reviewed: no, not independent (owner-practitioner round 2 changes applied).

| fixture | policy | net_cost | recovery_spend | expedite_spend | alternate_spend | service_penalties | otif_orders_met | on_time_units | unit_days_late | priority_weighted_unit_days_late | cancelled_order_value | pending_inbound_units | primary_reliance_pct | ending_cover_days_floor | salvage_credit | cancelled_units | verifier_feasible | matches_hand_ledger | replay_reproduced |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s03-sudden-5d | maintain | 18 | 0 | 0 | 0 | 18 | 0 | 4 | 12 | 60 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-sudden-5d | expedite_on_alert | 32 | 32 | 32 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-sudden-5d | alternate_on_alert | 56 | 104 | 0 | 104 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 50 | 2 | 48 | 0 | True | True | True |
| s03-sudden-5d | combo_on_alert | 44 | 68 | 16 | 52 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 66 | 1 | 24 | 0 | True | True | True |
| s03-sudden-5d | staged_revisit | 36 | 36 | 36 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-warned-delayed-10d | maintain | 30 | 0 | 0 | 0 | 30 | 0 | 4 | 20 | 100 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-warned-delayed-10d | expedite_on_alert | 32 | 32 | 32 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-warned-delayed-10d | alternate_on_alert | 104 | 104 | 0 | 104 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 50 | 2 | 0 | 0 | True | True | True |
| s03-warned-delayed-10d | combo_on_alert | 68 | 68 | 16 | 52 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 66 | 1 | 0 | 0 | True | True | True |
| s03-warned-delayed-10d | staged_revisit | 36 | 36 | 36 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-warned-no-delay-10d | maintain | 0 | 0 | 0 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-warned-no-delay-10d | expedite_on_alert | 32 | 32 | 32 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-warned-no-delay-10d | alternate_on_alert | 104 | 104 | 0 | 104 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 50 | 2 | 0 | 0 | True | True | True |
| s03-warned-no-delay-10d | combo_on_alert | 68 | 68 | 16 | 52 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 66 | 1 | 0 | 0 | True | True | True |
| s03-warned-no-delay-10d | staged_revisit | 16 | 16 | 16 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-multitier-cancel-10d | maintain | 67 | 0 | 0 | 0 | 67 | 0 | 4 | 48 | 80 | 320 | 0 | 100 | 0 | 0 | 4 | True | True | True |
| s03-multitier-cancel-10d | expedite_on_alert | 60 | 32 | 32 | 0 | 28 | 1 | 12 | 28 | 28 | 320 | 0 | 100 | 0 | 0 | 4 | True | True | True |
| s03-multitier-cancel-10d | alternate_on_alert | 93 | 104 | 0 | 104 | 13 | 1 | 8 | 12 | 12 | 0 | 0 | 50 | 1 | 24 | 0 | True | True | True |
| s03-multitier-cancel-10d | combo_on_alert | 76 | 68 | 16 | 52 | 8 | 1 | 12 | 8 | 8 | 0 | 0 | 66 | 0 | 0 | 0 | True | True | True |
| s03-multitier-cancel-10d | staged_revisit | 64 | 36 | 36 | 0 | 28 | 1 | 12 | 28 | 28 | 320 | 0 | 100 | 0 | 0 | 4 | True | True | True |
| s03-alt-cheaper-10d | maintain | 78 | 0 | 0 | 0 | 78 | 0 | 4 | 52 | 260 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-alt-cheaper-10d | expedite_on_alert | 98 | 32 | 32 | 0 | 66 | 0 | 4 | 44 | 220 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
| s03-alt-cheaper-10d | alternate_on_alert | 62 | 104 | 0 | 104 | 6 | 0 | 8 | 4 | 20 | 0 | 0 | 50 | 2 | 48 | 0 | True | True | True |
| s03-alt-cheaper-10d | combo_on_alert | 74 | 68 | 16 | 52 | 30 | 0 | 8 | 20 | 100 | 0 | 0 | 66 | 1 | 24 | 0 | True | True | True |
| s03-alt-cheaper-10d | staged_revisit | 102 | 36 | 36 | 0 | 66 | 0 | 4 | 44 | 220 | 0 | 0 | 100 | 0 | 0 | 0 | True | True | True |
