# Issue #5 solver evidence

Implementation: `src/supplychainworld/solvers.py`; tests: `tests/test_solvers.py`. Foundation and domain contracts were explicitly agreed before implementation. Uses Pydantic World without alternate schema; no checker logic imported by solver.

Executed 2026-11-02:

```console
PYTHONPATH=src python -m unittest discover -s tests -p test_solvers.py -v
Ran 7 tests in 0.006s
OK
```

The ten-case test compares status and objective against independently authored hand calculations, then sends every final submission to the independent `verification.verify` checker. Additional tests cover tied optimal allocations and a valid alternate, supplier subtotal rounding, zero-spend concentration, zero state/time budgets, partial search with no incumbent, timeout preserving a feasible incumbent, and heuristic failure without false infeasibility.

An additional executed Python loop loaded each fixture with `World.model_validate`, called `solve_reference` and `solve_heuristic`, and printed:

| Case | Reference status | Cost USD | Tree nodes | Greedy status | Cost USD |
|---|---|---:|---:|---|---:|
| ref-01 | optimal | 8.00 | 21 | feasible | 8.00 |
| ref-02 | optimal | 8.00 | 21 | feasible | 9.00 |
| ref-03 | optimal | 6.00 | 11 | feasible | 10.00 |
| ref-04 | optimal | 8.00 | 6 | feasible | 8.00 |
| ref-05 | optimal | 8.00 | 21 | feasible | 8.00 |
| ref-06 | optimal | 4.00 | 21 | error | — |
| ref-07 | optimal | 4.04 | 21 | feasible | 4.04 |
| ref-08 | optimal | 4.00 | 9 | feasible | 4.00 |
| ref-09 | clarification_required | — | 0 | clarification_required | — |
| ref-10 | infeasible | — | 10 | error | — |

Reference enumeration lazily traverses integral legal order domains, pruning quantities above each item's explicit excess allowance. Costs use Decimal and round supplier landed subtotals to cents HALF_UP, charging supplier fixed fee once. Concentration includes fixed fees and uses rounded landed supplier spend. Only completed enumeration yields optimal/infeasible. Timeout retains its incumbent if any, with conservative zero lower bound; without an incumbent, `submission()` raises rather than fabricating an exception supported by neither business evidence nor the submission schema. Complete optimal search sets lower bound equal to optimum. Missing eligible commercial terms request clarification.

Limits: defaults are 5 seconds / 1,000,000 visited search-tree nodes. Enumeration grows exponentially and is only a reference oracle for small synthetic instances, not a production optimizer. Limits are checked between nodes, not preemptively within a single arithmetic operation. Recursive depth grows with eligible quote count; recursion exhaustion returns unresolved error, never infeasible. Invalid/nonfinite limits return error. Heuristic greedily orders variable unit costs; it can miss fixed-fee savings, order-multiple combinations and concentration-feasible splits. Its error status means construction failed, not operational infeasibility. No paid optimizer, model run, practitioner signoff, scalability benchmark or training benefit is claimed.
