# Issue #2 results

Implemented docs/task-families/supplier-allocation.md and ten fixtures/reference_cases/ref-01.json through ref-10.json. Every case includes a visible request/world, expected behavior, hand calculation, known wrong submission and explicit pending practitioner review. Reference 05 includes a valid alternative tie. Reference 07 exercises exact fractional-cent inputs against a binding budget.

Verification executed in /workspace/SupplyChainWorld:

```text
$ python -m unittest discover -s tests -p test_reference_cases.py -v
test_all_ten_hand_results_and_wrong_submissions (test_reference_cases.ReferenceCases.test_all_ten_hand_results_and_wrong_submissions) ... ok

Ran 1 test in 0.006s
OK
```

The independent test enumerates integer quote quantities using no production imports, confirms the eight hand-costed optima and alternative, finds no feasible allocation for capacity case 10, checks the missing freight premise for case 09, and rejects all ten wrong awards. Hand calculations and enumerator are separate from the production solver implementation; both were authored by this agent, so this is not a substitute for external domain review. No practitioner endorsement exists. Screenshots are captured separately by the proof agent.
