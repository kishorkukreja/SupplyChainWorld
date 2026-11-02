#!/usr/bin/env python3
"""Independent public-fixture and multi-item fixed-charge regression review."""
import copy
from decimal import Decimal
import json
from pathlib import Path

from supplychainworld.schemas import World
from supplychainworld.schemas import Task
from supplychainworld.environment import ProcurementEnvironment, TOOLS, render_artifacts
from supplychainworld.solvers import solve_reference
from supplychainworld.verification import verify

root = Path(__file__).resolve().parents[1]
cases = [json.loads(p.read_text()) for p in sorted((root / 'fixtures/reference_cases').glob('*.json'))]
assert len(cases) == 10
for case in cases:
    world = World.model_validate(case['world'])
    expected = case['expected']
    result = verify(world, expected['submission'])
    assert result.accepted, (case['case_id'], result)
    if expected['optimal_cost'] is not None:
        assert result.independent_cost == Decimal(expected['optimal_cost'])
    for wrong in case['known_wrong']:
        assert not verify(world, wrong['submission']).accepted, (case['case_id'], wrong)
    assert case['review']['practitioner_signoff'] is False
    task = Task(task_id=case['case_id'], world_id=world.world_id,
                lineage=case['case_id'], split='development', request=case['request'],
                visible_artifacts=list(render_artifacts(world)), permitted_tools=TOOLS,
                expected_outcome=expected['submission']['kind'],
                clarification_policy=({'quotes.A.component.variable_freight':'record_and_escalate'}
                                      if case['case_id'] == 'ref-09' else {}))
    env = ProcurementEnvironment(world, task)
    response = env.step({'tool_name':'submit_award' if expected['submission']['kind'] == 'award' else 'submit_exception',
                         'arguments':expected['submission'], 'request_id':'review-submit', 'state_version':0})
    assert response.error is None
    assert env.replay(env.audit_log)
    assert verify(world, env.submission).accepted
    initial = env.reset(task.task_id, world.seed)
    assert initial['state_version'] == 0 and not initial['terminated'] and not env.audit_log
    print(f"{case['case_id']}: schema valid; expected accepted; known wrong rejected; practitioner review pending")

world = copy.deepcopy(cases[1]['world'])
world['items'][0]['demand'] = 1
second = copy.deepcopy(world['items'][0]); second['item_id'] = 'second'
world['items'].append(second)
world['suppliers'] = [world['suppliers'][0]]
world['quotes'] = [world['quotes'][0]]
quote = copy.deepcopy(world['quotes'][0]); quote['item_id'] = 'second'
world['quotes'].append(quote)
submission = {'kind':'award', 'allocations':[
    {'supplier_id':'A','item_id':'component','quantity':1},
    {'supplier_id':'A','item_id':'second','quantity':1}],
    'claimed_total_cost':'7.00','evidence':['Two public synthetic item lines; one selected supplier.']}
assert verify(World.model_validate(world), submission).accepted
solved = solve_reference(World.model_validate(world))
assert solved.status == 'optimal' and solved.total_cost == Decimal('7.00')
submission['claimed_total_cost'] = '12.00'
assert not verify(world, submission).accepted
print('Multi-item fixed charge: 1 + 1 + 5 = 7; doubled fee 12 rejected')
print('All 10 expected submissions recorded, replayed, independently verified and reset through environment.')
print('Reference solver independently agrees with multi-item total 7.00.')
print('Independent review completed: public synthetic cases only; no practitioner endorsement or environment/privacy guarantee.')
