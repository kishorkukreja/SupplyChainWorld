# Observable experience record: fixture-fifteen (15 days)

Agent: scripted baseline policy (not an LLM; carries no model-ability claim).
Shows only what the agent saw, the call it made, the outcome and the resulting events. No answer key, other policy or verifier output is included.

- step 1, day 1 (action): saw components=4, finished=0, delivered=0, notices=[]; called `release_production` {'quantity': 4} -> accepted
- step 2, day 1 (action): saw components=4, finished=0, delivered=0, notices=[]; called `advance_day` {} -> accepted
- step 3, day 2 (action): saw components=0, finished=4, delivered=0, notices=[]; called `release_production` {'quantity': 0} -> accepted
- step 4, day 2 (action): saw components=0, finished=4, delivered=0, notices=[]; called `advance_day` {} -> accepted
- step 5, day 3 (action): saw components=0, finished=4, delivered=0, notices=[]; called `release_production` {'quantity': 0} -> accepted
- step 6, day 3 (action): saw components=0, finished=4, delivered=0, notices=[]; called `advance_day` {} -> accepted
- step 7, day 4 (action): saw components=0, finished=4, delivered=0, notices=[]; called `release_production` {'quantity': 0} -> accepted
- step 8, day 4 (action): saw components=0, finished=4, delivered=0, notices=[]; called `advance_day` {} -> accepted
- step 9, day 5 (action): saw components=0, finished=4, delivered=0, notices=[]; called `release_production` {'quantity': 0} -> accepted
- step 10, day 5 (action): saw components=0, finished=4, delivered=0, notices=[]; called `advance_day` {} -> accepted
- step 11, day 6 (action): saw components=0, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `commit_recovery` {'choice': 'expedite'} -> accepted
- step 12, day 6 (action): saw components=0, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 13, day 6 (action): saw components=0, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 14, day 7 (action): saw components=0, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 15, day 7 (action): saw components=0, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 16, day 8 (action): saw components=8, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 4} -> accepted
- step 17, day 8 (action): saw components=8, finished=4, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 18, day 9 (action): saw components=4, finished=8, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 4} -> accepted
- step 19, day 9 (action): saw components=4, finished=8, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 20, day 10 (action): saw components=0, finished=12, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 21, day 10 (action): saw components=0, finished=12, delivered=0, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 22, day 11 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 23, day 11 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 24, day 12 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 25, day 12 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 26, day 13 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 27, day 13 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 28, day 14 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 29, day 14 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted
- step 30, day 15 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `release_production` {'quantity': 0} -> accepted
- step 31, day 15 (action): saw components=0, finished=0, delivered=12, notices=['Primary PO delayed from day 8 to day 12']; called `advance_day` {} -> accepted

Final scorecard: {'delivered_on_time': 12, 'delivered_total': 12, 'ending_components': 0, 'incremental_spend': 24, 'service_penalties': 0, 'comparison_cost': 24}
