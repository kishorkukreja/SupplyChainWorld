"""End-to-end tracing: real mocked-model episodes -> real adapter, runner, checker and replay -> trace plan -> client calls.
Part A uses a fake client. Part B uses the real Langfuse SDK with an in-memory span exporter: no network and no keys (dummy
values only, host on a closed local port). Part B is skipped only when `langfuse` is not installed."""
import copy
import inspect
import json
import unittest

import support  # noqa: F401
from support import tracing_fixtures as tf

from supplychainworld import tracing as tr

try:
    import langfuse
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
except ImportError:  # the `trace` extra is not installed
    langfuse = None


class WithFakeClient(unittest.TestCase):
    def test_every_episode_is_sent_as_one_agent_with_ordered_children_and_scores_then_flushed_once(self):
        for policy, raw, grade in tf.episodes():
            client = tf.FakeClient()
            res = tr.trace_episode(raw, grade, client, run_label='e2e', propagate=tf.fake_propagate)
            self.assertTrue(res['exported'], policy)
            root, *kids = client.events
            self.assertEqual(root['kw']['as_type'], 'agent')
            self.assertEqual(root['kw']['trace_context'], {'trace_id': res['trace_id']})
            self.assertEqual(root['updates'][0]['output']['status'], 'complete')
            self.assertEqual([k['kw']['as_type'] for k in kids if k['kw']['as_type'] == 'tool'].__len__(),
                             len(raw['transcript']['attempts']))
            seqs = [k['kw']['metadata']['seq'] for k in kids]
            self.assertEqual(seqs, sorted(seqs))
            for k in kids:
                if k['kw']['as_type'] == 'generation':
                    self.assertEqual(k['kw']['model'], raw['model'])
                    self.assertTrue(k['kw']['usage_details'])
            self.assertEqual(client.flushes, 1)
            ids = [s['score_id'] for s in client.scores]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(all(s['trace_id'] == res['trace_id'] for s in client.scores))
            self.assertEqual(tf.FakeClient.last_propagate['session_id'], 'e2e')

    def test_what_is_sent_matches_the_saved_run_and_the_checker_verdict(self):
        _, raw, grade = tf.episodes()[3]
        client = tf.FakeClient()
        tr.trace_episode(raw, grade, client, propagate=tf.fake_propagate)
        tools = [e['kw'] for e in client.events if e['kw']['as_type'] == 'tool']
        for sent, a in zip(tools, raw['transcript']['attempts']):
            self.assertEqual(sent['input'], a['arguments'])
            self.assertEqual(sent['output']['accepted'], a['accepted'])
        scores = {s['name']: s['value'] for s in client.scores}
        self.assertEqual(scores['verifier_feasible'], int(grade['verifier_feasible']))
        self.assertEqual(scores['metric_net_cost'], grade['metrics']['net_cost'])

    def test_off_by_default_nothing_is_built_or_sent(self):
        client = tr.tracing_client({})
        self.assertIsNone(client)
        self.assertEqual(tr.trace_episode(*tf.episodes()[0][1:], client)['reason'], 'tracing off')


@unittest.skipIf(langfuse is None, 'langfuse not installed (pip install -e ".[trace]")')
class WithRealSdkOffline(unittest.TestCase):
    def test_the_calls_we_make_fit_the_installed_sdk_signatures(self):
        _, raw, grade = tf.episodes()[0]
        client = tf.FakeClient()
        tr.trace_episode(raw, grade, client, propagate=tf.fake_propagate)
        sig = inspect.signature(Langfuse.start_as_current_observation)
        for e in client.events:
            sig.bind(None, **e['kw'])
        score_sig = inspect.signature(Langfuse.create_score)
        for s in client.scores:
            score_sig.bind(None, **s)
        inspect.signature(langfuse.propagate_attributes).bind(**tf.FakeClient.last_propagate)

    def test_a_real_sdk_records_the_agent_generation_tool_tree_with_our_trace_id(self):
        _, raw, grade = tf.episodes()[0]
        plan = tr.build_trace_plan(raw, grade, run_label='sdk')
        exporter = InMemorySpanExporter()
        client = Langfuse(public_key='pk-lf-dummy', secret_key='sk-lf-dummy', base_url='http://127.0.0.1:9', timeout=1,
                          span_exporter=exporter)
        tr.export_plan(dict(copy.deepcopy(plan), scores=[]), client)
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1 + len(plan['children']))
        attrs = [dict(s.attributes) for s in spans]
        types = [a.get('langfuse.observation.type') for a in attrs]
        self.assertEqual(sorted(types), sorted(['agent'] + [c['type'] for c in plan['children']]))
        self.assertTrue(all(format(s.context.trace_id, '032x') == plan['trace_id'] for s in spans))
        self.assertTrue(all(a.get('session.id') == 'sdk' for a in attrs))
        dumped = json.dumps(attrs, default=str)
        self.assertNotIn('sk-lf-dummy', dumped)


if __name__ == '__main__':
    unittest.main()
