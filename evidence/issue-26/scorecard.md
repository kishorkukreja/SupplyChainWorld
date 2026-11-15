# Three-policy scorecard (scripted baselines, synthetic fixtures)

| fixture | policy | delivered_on_time | delivered_total | ending_components | incremental_spend | service_penalties | comparison_cost | verifier_feasible | verifier_comparison_cost | replay_reproduced |
|---|---|---|---|---|---|---|---|---|---|---|
| s01-five-day | maintain | 4 | 12 | 0 | 0 | 120 | 120 | True | 120 | True |
| s01-five-day | expedite | 12 | 12 | 0 | 24 | 0 | 24 | True | 24 | True |
| s01-five-day | alternate | 12 | 12 | 8 | 40 | 0 | 40 | True | 40 | True |
| s01-fifteen-day-late-events | maintain | 4 | 12 | 0 | 0 | 200 | 200 | True | 200 | True |
| s01-fifteen-day-late-events | expedite | 12 | 12 | 0 | 24 | 0 | 24 | True | 24 | True |
| s01-fifteen-day-late-events | alternate | 12 | 12 | 8 | 40 | 0 | 40 | True | 40 | True |
