# Per-metric comparison (no overall winner is declared)

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, reviewed: no, not independent (owner-practitioner round 2 changes applied).

Each table shows one scenario. "Best here" marks the policy (or tie) that is best on that metric alone.
Cost, service, tier impact, downstream impact and supply risk are never combined into one number.

## s03-sudden-5d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 18 | 32 | 56 | 44 | 36 | maintain |
| recovery_spend | cost | lower | 0 | 32 | 104 | 68 | 36 | maintain |
| expedite_spend | cost | lower | 0 | 32 | 0 | 16 | 36 | alternate_on_alert, maintain |
| alternate_spend | cost | lower | 0 | 0 | 104 | 52 | 0 | expedite_on_alert, maintain, staged_revisit |
| service_penalties | cost | lower | 18 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| otif_orders_met | service | higher | 0 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| on_time_units | service | higher | 4 | 12 | 12 | 12 | 12 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| unit_days_late | service | lower | 12 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| priority_weighted_unit_days_late | tier impact | lower | 60 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| cancelled_order_value | downstream impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 2 | 1 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.

## s03-warned-delayed-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 30 | 32 | 104 | 68 | 36 | maintain |
| recovery_spend | cost | lower | 0 | 32 | 104 | 68 | 36 | maintain |
| expedite_spend | cost | lower | 0 | 32 | 0 | 16 | 36 | alternate_on_alert, maintain |
| alternate_spend | cost | lower | 0 | 0 | 104 | 52 | 0 | expedite_on_alert, maintain, staged_revisit |
| service_penalties | cost | lower | 30 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| otif_orders_met | service | higher | 0 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| on_time_units | service | higher | 4 | 12 | 12 | 12 | 12 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| unit_days_late | service | lower | 20 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| priority_weighted_unit_days_late | tier impact | lower | 100 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| cancelled_order_value | downstream impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 2 | 1 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.

## s03-warned-no-delay-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 0 | 32 | 104 | 68 | 16 | maintain |
| recovery_spend | cost | lower | 0 | 32 | 104 | 68 | 16 | maintain |
| expedite_spend | cost | lower | 0 | 32 | 0 | 16 | 16 | alternate_on_alert, maintain |
| alternate_spend | cost | lower | 0 | 0 | 104 | 52 | 0 | expedite_on_alert, maintain, staged_revisit |
| service_penalties | cost | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| otif_orders_met | service | higher | 1 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| on_time_units | service | higher | 12 | 12 | 12 | 12 | 12 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| unit_days_late | service | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| priority_weighted_unit_days_late | tier impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| cancelled_order_value | downstream impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 2 | 1 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.

## s03-multitier-cancel-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 67 | 60 | 93 | 76 | 64 | expedite_on_alert |
| recovery_spend | cost | lower | 0 | 32 | 104 | 68 | 36 | maintain |
| expedite_spend | cost | lower | 0 | 32 | 0 | 16 | 36 | alternate_on_alert, maintain |
| alternate_spend | cost | lower | 0 | 0 | 104 | 52 | 0 | expedite_on_alert, maintain, staged_revisit |
| service_penalties | cost | lower | 67 | 28 | 13 | 8 | 28 | combo_on_alert |
| otif_orders_met | service | higher | 0 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| on_time_units | service | higher | 4 | 12 | 8 | 12 | 12 | combo_on_alert, expedite_on_alert, staged_revisit |
| unit_days_late | service | lower | 48 | 28 | 12 | 8 | 28 | combo_on_alert |
| priority_weighted_unit_days_late | tier impact | lower | 80 | 28 | 12 | 8 | 28 | combo_on_alert |
| cancelled_order_value | downstream impact | lower | 320 | 320 | 0 | 0 | 320 | alternate_on_alert, combo_on_alert |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 1 | 0 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.

## s03-alt-cheaper-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 78 | 98 | 62 | 74 | 102 | alternate_on_alert |
| recovery_spend | cost | lower | 0 | 32 | 104 | 68 | 36 | maintain |
| expedite_spend | cost | lower | 0 | 32 | 0 | 16 | 36 | alternate_on_alert, maintain |
| alternate_spend | cost | lower | 0 | 0 | 104 | 52 | 0 | expedite_on_alert, maintain, staged_revisit |
| service_penalties | cost | lower | 78 | 66 | 6 | 30 | 66 | alternate_on_alert |
| otif_orders_met | service | higher | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| on_time_units | service | higher | 4 | 4 | 8 | 8 | 4 | alternate_on_alert, combo_on_alert |
| unit_days_late | service | lower | 52 | 44 | 4 | 20 | 44 | alternate_on_alert |
| priority_weighted_unit_days_late | tier impact | lower | 260 | 220 | 20 | 100 | 220 | alternate_on_alert |
| cancelled_order_value | downstream impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 2 | 1 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.
