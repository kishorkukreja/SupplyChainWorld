"""Property tests for the Langfuse trace plan (src/supplychainworld/tracing.py). No network, no keys, mocked episodes only."""
import json
import unittest

from hypothesis import given, strategies as st

import support  # noqa: F401
from support import tracing_fixtures as tf
from support.fuzz import json_blobs

from supplychainworld import tracing as tr

SECRETS = st.sampled_from(['sk-lf-abc123', 'pk-lf-zzz-9', 'sk-or-v1-deadbeef', 'Bearer abc.def-ghi'])


def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)
    else:
        yield obj


class SanitizeProperties(unittest.TestCase):
    @given(json_blobs, SECRETS)
    def test_secret_strings_and_credential_keys_never_survive_and_the_result_is_stable(self, blob, secret):
        dirty = {'note': 'x ' + secret + ' y', 'api_key': 'whatever', 'Authorization': secret, 'inner': [blob, secret]}
        clean = tr.sanitize(dirty)
        text = json.dumps(clean)
        self.assertNotIn(secret, text)
        self.assertFalse({'api_key', 'authorization'} & {str(k).lower() for k in walk(clean) if isinstance(k, str)})
        self.assertEqual(tr.sanitize(clean), clean)

    @given(st.text(min_size=4, max_size=30))
    def test_an_explicit_secret_is_removed_from_every_string(self, secret):
        self.assertNotIn(secret, json.dumps(tr.sanitize({'a': ['pre ' + secret + ' post'], 'b': secret}, (secret,))))


class PlanProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eps = tf.episodes()

    def test_every_plan_is_json_deterministic_and_has_one_tool_observation_per_attempt(self):
        for policy, raw, grade in self.eps:
            a = tr.build_trace_plan(raw, grade, run_label='r1')
            self.assertEqual(a, tr.build_trace_plan(raw, grade, run_label='r1'), policy)
            json.dumps(a)
            tools = [c for c in a['children'] if c['type'] == 'tool']
            gens = [c for c in a['children'] if c['type'] == 'generation']
            self.assertEqual(len(tools), len(raw['transcript']['attempts']))
            self.assertEqual(len(gens), min(len(raw['telemetry']['calls']), len(tools)))
            self.assertEqual(a['root']['type'], 'agent')
            self.assertEqual(len(a['trace_id']), 32)

    def test_generations_use_openai_messages_stable_names_and_matching_tool_call_ids(self):
        for policy, raw, grade in self.eps:
            plan = tr.build_trace_plan(raw, grade)
            attempts = raw['transcript']['attempts']
            for c in plan['children']:
                self.assertIn(c['name'], ('choose-action', 'apply-tool-call'), policy)
                if c['type'] == 'generation':
                    msg = c['output']
                    self.assertEqual(msg['role'], 'assistant')
                    call = msg['tool_calls'][0]
                    self.assertIsInstance(call['function']['arguments'], str)
                    json.loads(call['function']['arguments'])
                    self.assertEqual(call['id'], 'call-%s' % c['metadata']['seq'])
                    roles = [m['role'] for m in c['input']]
                    self.assertEqual(roles[:2], ['system', 'user'])
                    self.assertLessEqual(roles.count('assistant'), 8)
                    # every tool result in the shown window answers a tool call that is also shown
                    shown = {t['id'] for m in c['input'] if m['role'] == 'assistant' for t in m['tool_calls']}
                    self.assertTrue({m['tool_call_id'] for m in c['input'] if m['role'] == 'tool'} <= shown)
                else:
                    self.assertEqual(c['metadata']['tool_call_id'], 'call-%s' % c['metadata']['seq'])
            self.assertEqual(len([c for c in plan['children'] if c['type'] == 'tool']), len(attempts))

    def test_trace_ids_follow_the_run_not_the_export(self):
        ids = set()
        for _, raw, grade in self.eps:
            ids.add(tr.build_trace_plan(raw, grade, run_label='r1')['trace_id'])
            self.assertNotEqual(tr.trace_id_for(raw, 'r1'), tr.trace_id_for(raw, 'r2'))
        self.assertGreater(len(ids), 1)

    def test_scores_are_one_per_checker_fact_with_unique_names_and_valid_types(self):
        for _, raw, grade in self.eps:
            scores = tr.build_trace_plan(raw, grade)['scores']
            names = [s['name'] for s in scores]
            self.assertEqual(len(names), len(set(names)))
            for s in scores:
                self.assertIn(s['data_type'], ('BOOLEAN', 'NUMERIC'))
                if s['data_type'] == 'BOOLEAN':
                    self.assertIn(s['value'], (0, 1))
                if s['name'].startswith('metric_'):
                    self.assertIn('PROVISIONAL', s['comment'])
            self.assertEqual({s['name']: s['value'] for s in scores}['verifier_feasible'], int(grade['verifier_feasible']))

    def test_the_private_world_state_is_never_read(self):
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError('tracing touched raw[world]')
        for _, raw, grade in self.eps[:5]:
            raw['world'] = Poison()
            tr.build_trace_plan(raw, grade)

    @given(st.data())
    def test_any_private_string_present_in_the_plan_is_refused(self, data):
        _, raw, grade = data.draw(st.sampled_from(self.eps))
        text = json.dumps(tr.build_trace_plan(raw, grade))
        start = data.draw(st.integers(0, len(text) - 12))
        piece = text[start:start + data.draw(st.integers(6, 12))]
        if piece.strip():
            with self.assertRaises(tr.TraceLeakError) as ctx:
                tr.build_trace_plan(raw, grade, private_strings=(piece,))
            self.assertNotIn(piece, str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
