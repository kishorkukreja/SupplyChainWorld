import json
from pathlib import Path
import unittest
from supplychainworld.schemas import Task, World
from supplychainworld.environment import ProcurementEnvironment, TOOLS, render_artifacts

ROOT = Path(__file__).resolve().parents[1]


def environment(case='ref-01'):
    fixture = json.loads((ROOT / 'fixtures' / 'reference_cases' / (case + '.json')).read_text())
    world = World.model_validate(fixture['world'])
    task = Task(task_id=case, world_id=case, lineage=case, split='development',
                request=fixture['request'], visible_artifacts=list(render_artifacts(world)),
                permitted_tools=TOOLS, expected_outcome=fixture['expected']['submission']['kind'],
                clarification_policy=({'quotes.A.component.variable_freight': 'record_and_escalate'}
                                      if case == 'ref-09' else {}))
    return ProcurementEnvironment(world, task), fixture


def action(env, tool, args=None, request_id=None):
    return {'tool_name': tool, 'arguments': args or {},
            'request_id': request_id or 'r' + str(len(env.audit_log)),
            'state_version': env.observe()['state_version']}


class EnvironmentTests(unittest.TestCase):
    def test_artifact_and_query_consistency_and_sanitization(self):
        env, _ = environment()
        observation = env.observe()
        self.assertNotIn('expected_outcome', observation)
        self.assertNotIn('optimal_cost', json.dumps(observation))
        queried = env.step(action(env, 'quotes')).observation['records']
        rendered = env.step(action(env, 'read_artifact', {'name': 'quotes.json'}))
        self.assertEqual(queried, json.loads(rendered.observation['content']))
        self.assertNotIn('expected', rendered.observation['content'])
        for name in ('../expected.json', '/etc/passwd', 'expected', 'ref-01.json'):
            before = env.audit_log
            self.assertEqual(env.step(action(env, 'read_artifact', {'name': name})).error.code, 'artifact_denied')
            self.assertEqual(before, env.audit_log)

    def test_invalid_actions_never_mutate(self):
        env, _ = environment()
        invalid = [action(env, 'quotes', {'unexpected': 1}),
                   action(env, 'submit_award', {'kind': 'award', 'allocations': [], 'claimed_total_cost': 1.5, 'evidence': []}),
                   action(env, 'python', {'code': 'open("expected")'}),
                   action(env, 'request_clarification', {'field': 'secret', 'reason': 'need it'}),
                   {'tool_name': 'quotes', 'arguments': {}, 'request_id': 'bad', 'state_version': 99},
                   {'tool_name': 'quotes', 'arguments': {}, 'request_id': 'bad', 'state_version': 0, 'extra': 'bad'}]
        for value in invalid:
            before = (env.observe(), env.audit_log, env.submission)
            self.assertIsNotNone(env.step(value).error)
            self.assertEqual(before, (env.observe(), env.audit_log, env.submission))

    def test_award_termination_reset_and_replay(self):
        env, fixture = environment()
        initial = env.observe()
        env.step(action(env, 'requirements'))
        response = env.step(action(env, 'submit_award', fixture['expected']['submission']))
        self.assertEqual(response.observation['status'], 'submitted')
        log = env.audit_log
        self.assertTrue(env.observe()['terminated'])
        self.assertEqual(env.step(action(env, 'quotes')).error.code, 'episode_terminated')
        self.assertEqual(log, env.audit_log)
        self.assertTrue(env.replay(log))
        self.assertEqual(log, env.audit_log)
        log[0]['action']['tool_name'] = 'quotes'
        self.assertNotEqual(log, env.audit_log)
        self.assertEqual(initial, env.reset('ref-01', 1))
        self.assertEqual([], env.audit_log)
        self.assertIsNone(env.submission)

    def test_explicit_missing_field_clarification_and_exception(self):
        env, fixture = environment('ref-09')
        response = env.step(action(env, 'request_clarification',
                                   {'field': 'quotes.A.component.variable_freight', 'reason': 'Cost unknown'}))
        self.assertEqual(response.observation['status'], 'escalation_required')
        self.assertNotIn('value', response.observation)
        self.assertFalse(env.observe()['terminated'])
        result = env.step(action(env, 'submit_exception', fixture['expected']['submission']))
        self.assertIsNone(result.error)
        self.assertTrue(env.observe()['terminated'])
        self.assertTrue(env.replay(env.audit_log))

    def test_infeasible_exception_is_recorded_without_oracle(self):
        env, fixture = environment('ref-10')
        result = env.step(action(env, 'submit_exception', fixture['expected']['submission']))
        self.assertEqual('submitted', result.observation['status'])
        self.assertNotIn('accepted', result.observation)
        self.assertTrue(env.observe()['terminated'])

    def test_sessions_and_returned_values_are_isolated(self):
        first, _ = environment()
        second, _ = environment()
        result = first.step(action(first, 'quotes'))
        result.observation['records'].clear()
        self.assertTrue(first.audit_log[0]['result']['observation']['records'])
        self.assertEqual(0, second.observe()['state_version'])
        obs = second.observe()
        obs['tools'].clear()
        self.assertTrue(second.observe()['tools'])

    def test_duplicate_request_and_replay_tampering(self):
        env, _ = environment()
        env.step(action(env, 'quotes', request_id='once'))
        result = env.step(action(env, 'quotes', request_id='once'))
        self.assertEqual('duplicate_request', result.error.code)
        events = env.audit_log
        events[0]['result']['observation'] = {'tampered': True}
        with self.assertRaisesRegex(ValueError, 'diverged'):
            env.replay(events)


if __name__ == '__main__':
    unittest.main()
