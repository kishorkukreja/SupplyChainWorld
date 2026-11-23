"""Fuzz tests for tracing: damaged records, odd environments, secrets planted in the record. Tracing must fail closed and quiet."""
import copy
import json
import unittest

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
from support import tracing_fixtures as tf
from support.fuzz import json_blobs

from supplychainworld import tracing as tr

PLANTED = ('sk-lf-PLANTED-1', 'pk-lf-PLANTED-2', 'sk-or-PLANTED-3', 'Bearer PLANTED.4')


class DamagedRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eps = tf.episodes()

    @settings(max_examples=60)
    @given(st.data())
    def test_a_damaged_record_gives_a_valid_plan_or_a_quiet_failure_and_never_a_crash_or_partial_send(self, data):
        _, raw, grade = copy.deepcopy(data.draw(st.sampled_from(self.eps)))
        target = data.draw(st.sampled_from([raw['transcript']['attempts'][0], raw['transcript'], raw['telemetry'], raw,
                                            grade, raw['manifest']]))
        keys = list(target)
        for key in data.draw(st.lists(st.sampled_from(keys), max_size=3)):
            if data.draw(st.booleans()):
                target.pop(key, None)
            else:
                target[key] = data.draw(json_blobs)
        client = tf.FakeClient()
        result = tr.trace_episode(raw, grade, client, propagate=tf.fake_propagate)
        if result['exported']:
            self.assertEqual(client.flushes, 1)
        else:
            self.assertEqual(result['reason'], 'error')
            self.assertEqual(client.flushes, 0)
            self.assertTrue(set(result) <= {'exported', 'reason', 'error_class'})

    @given(st.sampled_from(PLANTED), st.sampled_from(['reason', 'tool_note', 'api_key']))
    def test_a_secret_planted_in_the_record_never_reaches_the_client(self, secret, where):
        _, raw, grade = copy.deepcopy(self.eps[0])
        a = raw['transcript']['attempts'][0]
        a['reason'] = 'oops ' + secret
        a['arguments'] = {'note': secret, 'api_key': secret}
        raw['telemetry']['calls'][0]['finish_reason'] = secret
        client = tf.FakeClient()
        self.assertTrue(tr.trace_episode(raw, grade, client, propagate=tf.fake_propagate)['exported'])
        sent = json.dumps([client.events, client.scores, tf.FakeClient.last_propagate], default=str)
        self.assertNotIn(secret, sent)
        self.assertNotIn('PLANTED', sent)

    def test_a_private_string_stops_the_export_and_nothing_is_sent(self):
        _, raw, grade = self.eps[0]
        client = tf.FakeClient()
        r = tr.trace_episode(raw, grade, client, private_strings=(raw['manifest']['system_prompt'][:40],),
                             propagate=tf.fake_propagate)
        self.assertEqual(r, {'exported': False, 'reason': 'error', 'error_class': 'TraceLeakError'})
        self.assertEqual((client.events, client.scores, client.flushes), ([], [], 0))


ENV_VALUES = st.one_of(st.none(), st.just(''), st.just('0'), st.just('1'), st.just('true'), st.text(max_size=6))


class Environment(unittest.TestCase):
    @given(st.fixed_dictionaries({}, optional={k: ENV_VALUES for k in (tr.ENABLE_ENV, *tr.REQUIRED_ENV)}))
    def test_tracing_is_on_only_for_the_exact_switch_and_all_three_settings(self, env):
        env = {k: v for k, v in env.items() if v is not None}
        made = []
        client = tr.tracing_client(env, factory=lambda **kw: made.append(kw) or object())
        should = env.get(tr.ENABLE_ENV) == '1' and all(env.get(k) for k in tr.REQUIRED_ENV)
        self.assertEqual(client is not None, should)
        self.assertEqual(len(made), 1 if should else 0)
        self.assertTrue(all(not any(s in str(kw) for s in env.values() if len(s) > 3) for kw in made) or not made)

    def test_the_default_is_off_with_the_real_environment_and_with_no_client(self):
        self.assertIsNone(tr.tracing_client({}))
        self.assertEqual(tr.trace_episode(None, None, None), {'exported': False, 'reason': 'tracing off'})


if __name__ == '__main__':
    unittest.main()
