# Supplier-delay engineering fixtures and baseline traces

Issue #23 provides deterministic multi-day situations, not an LLM training dataset. The public [inputs](../fixtures/dynamic/supplier-delay-inputs.json) and independently hand-calculated [expected ledgers](../fixtures/dynamic/supplier-delay-expected.json) are separate. Never expose the expected file to a model being evaluated. These public engineering fixtures must not be used as sealed evaluation tasks.

`SupplierDelayScenario` parameterizes the one-item world: stock, demand, capacity, due day, notice/arrival/deadline dates and dollar amounts. `OperationalWorld(horizon_days=5)` retains the existing API and defaults. Day-open order is scheduled receipts, an internal pre-notice snapshot, any notice due that day, then the visible action phase. With `disruption_enabled=False` the original PO arrives as promised and no delay notice/recovery offers appear. State and scenario schema/runtime versions are explicit and validated; other versions are rejected.

The scripted `run_baseline` policy sees only `world.observation()`: current state, disclosed notice, public business rules and recovery offers after the notice. It chooses its assigned policy only after that notice and releases the largest currently feasible daily lot. It does not read the future event schedule, expected ledger or reference optimizer. Internal Python objects are not hostile-code sandboxed; this observation contract is not a security boundary against untrusted in-process code.

Run from repository root:

```sh
PYTHONPATH=src python scripts/run_supplier_delay_baselines.py --output /tmp/supplier-delay-traces.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

The first input has a five-day horizon with the day-one notice and day-three due date. The second has 15 days, notice day 6, original/expedited/alternate arrival day 8, delayed primary receipt day 12 and customer due day 10. The later date is an actual scheduled event, not merely a longer end time. Since the due-date assessments occur on days 10, 11 and 12 before fulfillment, the maintain policy incurs $200 in penalties (8+8+4 units at $10); expedite costs $24 and alternate supply costs $40, with 8 unused components left at day 15.

Every policy shares the same initial observation, source world, decision deadline and exogenous notice. Recovery effects alter event schedules as specified. Horizon controls when the simulation terminates; future event dates may be outside the horizon, and a due date beyond the horizon leaves on-time delivery unobserved (`null`).

The configuration supports only proactive supplier notices before the originally promised receipt, with recovery committed before that original receipt. A notice on or after the promised arrival, late discovery of a missing delivery, and recovery after that arrival are not supported. These would require additional modeled event and decision rules; they must not be approximated by changing only the horizon.

The synthetic fixture and fixed penalty/event rules are working assumptions pending practitioner review. Policies and tests do not establish generalization, benchmark validity, model ability or training gains. Independent dynamic checking (#25), secure agent integration/replay (#24), and the full scenario demonstration (#26) remain open.
