# What the agent saw and did

Agent: scripted baseline policy (not an LLM; carries no model-ability claim). Values: PROVISIONAL, needs practitioner value; practitioner review: none.

This page shows only what the agent could see, the call it made and the outcome. Nothing from the checker, from other policies or from the scenario's future is included.

## The situation

A small plant runs for 10 simulated days. It has a daily production capacity of 4 units and a recovery budget of USD 40. Customer orders: O1 is 12 units due on day 4 in the key tier.

## The rules the agent was told

- Each day has three steps: at day opening lots arrive and any signal or notice appears; then you act (commit recovery, release production); then advance_day closes the day, in this order: production completes, goods ship, penalties and cancellations are assessed.
- A lot whose arrival_day is today has already arrived when you act: its units are in component_on_hand at day opening and a release made today can use them.
- A release made today is built at the close of today: the components leave component_on_hand and the finished goods enter finished_on_hand at that close, before shipping, so they can ship at the same close.
- An order is shipped only from the close of its due_day on, and at every close after that while it is still open; goods are never shipped before the due day, even if they are on hand.
- At each close the due orders are served in this sequence: highest tier weight first, then order_id in ascending text order; each takes the smaller of the finished goods still on hand and its undelivered units.
- on_time_units of an order are the units delivered by the close of its due_day; units shipped later are delivered but not on time.
- A penalty is assessed at each close for every open order whose due_day is today or earlier and that still has undelivered units after that close's shipping; each daily amount is rounded down to whole USD.
- For penalty_type percent_of_value, penalty_rate is in basis points (one hundredth of one percent, so 150 means 1.5 percent): each late day costs undelivered units x unit_value x penalty_rate / 10000.
- For penalty_type fixed_per_unit, penalty_rate is whole USD per undelivered unit, charged once, at the close of the due_day only.
- For penalty_type per_unit_per_day, penalty_rate is whole USD per undelivered unit for each day the order is still short, from its due_day on.
- penalty_cap_pct, when not null, is a whole percent of the full order value (quantity x unit_value): the penalties of one order add up to at most that; null means no cap.
- A cancel_after tier cancels the undelivered units of an order at the close of the day due_day + cancel_days_after_due, after that day's shipping and penalty; cancelled units are never delivered and cost no further penalty; a backlog tier never cancels.
- A lot arrives at the opening of its arrival_day. An expedited lot takes the arrival_day of the offer; a lot bought from the alternate supplier arrives on the arrival_day of the offer row for the day it was bought; the primary lot keeps its shown arrival_day unless a firm notice changes it.
- A commit_recovery sent without an action_id is given a key built from the day, the choice and the quantity: the same purchase repeated on the same day without a distinct action_id is refused, and the prefix auto- is reserved. Send distinct action_ids to buy identical lots on purpose.
- Until a firm notice is shown, a lot shows its promised arrival_day and a possible-delay signal gives only a level: what you see then is a plan, not a promise.

## Day by day

- Step 1. Situation: day 1 of 10; 4 components and 0 finished goods on hand; 0 units delivered so far; a possible-delay signal at level medium. Chose to buy 4 units by expedite. Done.
- Step 2. Situation: day 1 of 10; 4 components and 0 finished goods on hand; 0 units delivered so far; a possible-delay signal at level medium. Chose to release 4 units into production. Done.
- Step 3. Situation: day 1 of 10; 4 components and 0 finished goods on hand; 0 units delivered so far; a possible-delay signal at level medium. Chose to close day 1 and move on. Done.
- Step 4. Situation: day 2 of 10; 4 components and 4 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to buy 4 units by expedite. Done.
- Step 5. Situation: day 2 of 10; 4 components and 4 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 4 units into production. Done.
- Step 6. Situation: day 2 of 10; 4 components and 4 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 2 and move on. Done.
- Step 7. Situation: day 3 of 10; 4 components and 8 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 4 units into production. Done.
- Step 8. Situation: day 3 of 10; 4 components and 8 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 3 and move on. Done.
- Step 9. Situation: day 4 of 10; 0 components and 12 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 10. Situation: day 4 of 10; 0 components and 12 finished goods on hand; 0 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 4 and move on. Done.
- Step 11. Situation: day 5 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 12. Situation: day 5 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 5 and move on. Done.
- Step 13. Situation: day 6 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 14. Situation: day 6 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 6 and move on. Done.
- Step 15. Situation: day 7 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 16. Situation: day 7 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 7 and move on. Done.
- Step 17. Situation: day 8 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 18. Situation: day 8 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 8 and move on. Done.
- Step 19. Situation: day 9 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 20. Situation: day 9 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 9 and move on. Done.
- Step 21. Situation: day 10 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to release 0 units into production. Done.
- Step 22. Situation: day 10 of 10; 0 components and 0 finished goods on hand; 12 units delivered so far; Primary PO delayed from day 3 to day 6. Chose to close day 10 and move on. Done.

## The result

1 of 1 orders were delivered in full on time. 12 units were delivered, 0 were cancelled, and 0 unit-days were late. Recovery spend was USD 36, late penalties USD 0, salvage credit USD 0, so the net cost was USD 36. All numbers are PROVISIONAL, needs practitioner value.

