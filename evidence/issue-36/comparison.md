# Per-metric comparison (no overall winner is declared)

ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, practitioner-reviewed: no.

Each table shows one scenario. "Best here" marks the policy (or tie) that is best on that metric alone.
Cost, service, tier impact, downstream impact and supply risk are never combined into one number.

## s02-sudden-5d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 120 | 24 | 24 | 24 | 28 | alternate_on_alert, combo_on_alert, expedite_on_alert |
| recovery_spend | cost | lower | 0 | 24 | 40 | 32 | 28 | maintain |
| service_penalties | cost | lower | 120 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| otif_orders_met | service | higher | 0 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| on_time_units | service | higher | 4 | 12 | 12 | 12 | 12 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| unit_days_late | service | lower | 12 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| priority_weighted_unit_days_late | tier impact | lower | 36 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| cancelled_order_value | downstream impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 2 | 1 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.

## s02-warned-delayed-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 50 | 24 | 24 | 24 | 28 | alternate_on_alert, combo_on_alert, expedite_on_alert |
| recovery_spend | cost | lower | 0 | 24 | 40 | 32 | 28 | maintain |
| service_penalties | cost | lower | 50 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| otif_orders_met | service | higher | 0 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| on_time_units | service | higher | 4 | 12 | 12 | 12 | 12 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| unit_days_late | service | lower | 20 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| priority_weighted_unit_days_late | tier impact | lower | 60 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| cancelled_order_value | downstream impact | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 0 | 0 | 2 | 1 | 0 | alternate_on_alert |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.

## s02-warned-no-delay-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 0 | 24 | 24 | 24 | 12 | maintain |
| recovery_spend | cost | lower | 0 | 24 | 40 | 32 | 12 | maintain |
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

## s02-multitier-cancel-10d

| metric | dimension | better | maintain | expedite_on_alert | alternate_on_alert | combo_on_alert | staged_revisit | best here |
|---|---|---|---|---|---|---|---|---|
| net_cost | cost | lower | 64 | 48 | 56 | 48 | 52 | combo_on_alert, expedite_on_alert |
| recovery_spend | cost | lower | 0 | 24 | 40 | 32 | 28 | maintain |
| service_penalties | cost | lower | 72 | 24 | 24 | 16 | 24 | combo_on_alert |
| otif_orders_met | service | higher | 0 | 1 | 1 | 1 | 1 | alternate_on_alert, combo_on_alert, expedite_on_alert, staged_revisit |
| on_time_units | service | higher | 4 | 12 | 8 | 12 | 12 | combo_on_alert, expedite_on_alert, staged_revisit |
| unit_days_late | service | lower | 32 | 12 | 12 | 8 | 12 | combo_on_alert |
| priority_weighted_unit_days_late | tier impact | lower | 48 | 12 | 12 | 8 | 12 | combo_on_alert |
| cancelled_order_value | downstream impact | lower | 160 | 80 | 0 | 0 | 80 | alternate_on_alert, combo_on_alert |
| pending_inbound_units | supply risk | lower | 0 | 0 | 0 | 0 | 0 | alternate_on_alert, combo_on_alert, expedite_on_alert, maintain, staged_revisit |
| primary_reliance_pct | supply risk | lower | 100 | 100 | 50 | 66 | 100 | alternate_on_alert |
| ending_cover_days_floor | supply risk | higher | 1 | 0 | 1 | 0 | 0 | alternate_on_alert, maintain |

Best on every metric: none. No policy is best on every metric; different metrics favour different policies. No overall winner is declared. Weighing cost against service, tier, downstream and supply-risk impact is a practitioner decision.
