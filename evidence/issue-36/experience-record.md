# Observable experience record: s02-warned-delayed-10d (10 days)

Agent: scripted baseline policy (not an LLM; carries no model-ability claim). Values: PROVISIONAL, needs practitioner value; reviewed: no.
Shows only what the agent saw, the call it made, the outcome and the resulting events. No answer key, other policy or verifier output.

- step 1, day 1: components=4, finished=0, delivered=0, signals=[60], notices=[]; called `commit_recovery` {'choice': 'expedite', 'quantity': 4} -> accepted
- step 2, day 1: components=4, finished=0, delivered=0, signals=[60], notices=[]; called `release_production` {'quantity': 4} -> accepted
- step 3, day 1: components=4, finished=0, delivered=0, signals=[60], notices=[]; called `advance_day` {} -> accepted
- step 4, day 2: components=4, finished=4, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `commit_recovery` {'choice': 'expedite', 'quantity': 4} -> accepted
- step 5, day 2: components=4, finished=4, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 4} -> accepted
- step 6, day 2: components=4, finished=4, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 7, day 3: components=4, finished=8, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 4} -> accepted
- step 8, day 3: components=4, finished=8, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 9, day 4: components=0, finished=12, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 10, day 4: components=0, finished=12, delivered=0, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 11, day 5: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 12, day 5: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 13, day 6: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 14, day 6: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 15, day 7: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 16, day 7: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 17, day 8: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 18, day 8: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 19, day 9: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 20, day 9: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted
- step 21, day 10: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `release_production` {'quantity': 0} -> accepted
- step 22, day 10: components=0, finished=0, delivered=12, signals=[60], notices=['Primary PO delayed from day 3 to day 6']; called `advance_day` {} -> accepted

Final scorecard: {"schema": "dyn-scorecard-2", "cost": {"recovery_spend": 28, "service_penalties": 0, "salvage_credit": 0, "net_cost": 28}, "service": {"otif_orders_met": 1, "orders_total": 1, "on_time_units": 12, "ordered_units": 12, "delivered_total": 12, "cancelled_units": 0, "unit_days_late": 0, "orders": [{"order_id": "O1", "tier": "key", "ordered": 12, "otif": true, "on_time_units": 12, "delivered": 12, "cancelled": 0, "unit_days_late": 0, "days_short": 0, "penalty": 0}]}, "tier_impact": {"by_tier": {"key": {"orders": 1, "otif_orders_met": 1, "ordered": 12, "on_time_units": 12, "delivered": 12, "cancelled": 0, "unit_days_late": 0, "penalties": 0}}, "priority_weighted_unit_days_late": 0}, "downstream": {"cancelled_units": 0, "cancelled_order_value": 0, "undelivered_at_end": 0}, "supply_risk": {"ending_components": 0, "pending_inbound_units": 0, "ending_cover_days_floor": 0, "primary_reliance_pct": 100, "recovery_commitments": 2, "unused_recovery_budget": 12}, "values_status": "PROVISIONAL, needs practitioner value; not reviewed by a practitioner"}
