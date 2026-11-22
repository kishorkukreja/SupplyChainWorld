"""Offline tests for the DRAFT harness materials `eval19_v3` (S01 v0.6). No network, no credentials, mocked transports only.

Updates the rules-in-prompt consistency pattern of test_eval19_v2 (PR #47) for v0.6: every refusal the v0.6 world or runner
can give maps to a stated rule, every mapped sentence is in the system prompt and in a tool description, the conventions the
agent sees in its observation are the same sentences the prompt states, and nothing in a prompt names an outcome class. Then
25 episodes (5 scenarios x 5 declared policies) are played by a mocked model through the real adapter path, the v0.6 runner,
simulator, independent checker, replay and leak scan. NO LIVE MODEL CALL is made anywhere here.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

import support  # noqa: F401
import test_eval19_v2 as t2
from supplychainworld import eval19 as ev1
from supplychainworld import eval19_v2 as ev2
from supplychainworld import eval19_v3 as ev3
from supplychainworld.agent_runner_v6 import (CONVENTION_RULE_IDS, POLICIES_V6, REJECTION_RULES_V6, RULES_V6, TOOL_RULES_V6,
                                              ObservableRunnerV6, rule_for_reason_v6)
from supplychainworld.dynamic_demo_v6 import factory, load_fixtures, run_episode
from supplychainworld.dynamic_v6 import CONVENTION_STATEMENTS
from supplychainworld.dynamic_verifier_v6 import OUTCOME_WORDS

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src/supplychainworld'
FIXTURES = {f['fixture_id']: f for f in load_fixtures()}
MODEL = t2.MODEL
ENFORCING_SOURCES_V6 = t2.ENFORCING_SOURCES + ('dynamic_v6.py', 'agent_runner_v6.py')
NOTICE_MARK = t2.NOTICE_MARK


def all_reasons_v6():
    found = {}
    for name in ENFORCING_SOURCES_V6:
        for r in t2.reasons_in((SRC / name).read_text()):
            found.setdefault(r, []).append(name)
    return found


class StatedRulesV6(unittest.TestCase):
    def test_the_scan_sees_the_new_v06_refusals(self):
        found = all_reasons_v6()
        for must in ('duplicate commitment: the same purchase was already made today',
                     'duplicate commitment: the action_id prefix auto- is reserved', 'recovery budget exceeded',
                     'production exceeds open customer demand'):
            self.assertIn(must, found)
        self.assertIn('dynamic_v6.py', found['duplicate commitment: the same purchase was already made today'])

    def test_every_enforced_refusal_in_v06_maps_to_a_stated_rule(self):
        for reason, files in all_reasons_v6().items():
            self.assertIsNotNone(rule_for_reason_v6(reason), f'{reason!r} ({files}) has no stated rule in REJECTION_RULES_V6')

    def test_every_mapped_rule_sentence_is_in_the_system_prompt_and_a_tool_description(self):
        descriptions = ' '.join(ev3.S01_DESCRIPTIONS_V3.values())
        for reason in all_reasons_v6():
            rule = rule_for_reason_v6(reason)
            self.assertIn(RULES_V6[rule], ev3.S01_SYSTEM_PROMPT_V3, reason)
            if rule != 'episode_closed':
                self.assertIn(RULES_V6[rule], descriptions, (reason, rule))

    def test_the_exact_once_rule_now_states_the_case_without_an_action_id(self):
        sentence = RULES_V6['once_only']
        for phrase in ('without a distinct action id', 'same purchase', 'reserved'):
            self.assertIn(phrase, sentence)
        self.assertNotIn('without a distinct', t2.RULES['once_only'])        # the v0.5 sentence did not say it

    def test_the_rules_that_are_consequences_not_refusals_are_the_shipping_penalty_salvage_and_convention_sentences(self):
        used = {rule for _, rule in REJECTION_RULES_V6}
        self.assertEqual(set(RULES_V6) - used, {'shipping', 'penalties_cancel', 'salvage'} | set(CONVENTION_RULE_IDS))

    def test_a_new_unmapped_refusal_would_be_caught(self):
        src = "class W:\n    def go(self):\n        return self._reject('x', {}, 'a brand new v0.6 rule nobody stated')\n"
        self.assertEqual(t2.reasons_in(src), ['a brand new v0.6 rule nobody stated'])
        self.assertIsNone(rule_for_reason_v6('a brand new v0.6 rule nobody stated'))

    def test_every_sentence_of_the_conventions_block_is_in_the_prompt_and_is_what_the_agent_sees(self):
        runner = ObservableRunnerV6(factory(FIXTURES['s06-multitier-cancel-10d'])())
        seen = runner.view()['rules']['conventions']['statements']
        self.assertEqual(seen, CONVENTION_STATEMENTS)
        for key, sentence in seen.items():
            self.assertIn(sentence, ev3.S01_SYSTEM_PROMPT_V3, key)
            self.assertEqual(RULES_V6['convention_' + key], sentence)
        self.assertIn('basis points', ev3.S01_SYSTEM_PROMPT_V3)

    def test_the_tool_schemas_the_model_receives_carry_the_same_sentences(self):
        defs = ObservableRunnerV6(factory(FIXTURES['s06-sudden-5d'])()).tool_definitions()
        tools = {t['function']['name']: t['function']['description'] for t in ev3.s01_tools(defs)}
        self.assertEqual(set(tools), set(TOOL_RULES_V6))
        for name, rules in TOOL_RULES_V6.items():
            for r in rules:
                self.assertIn(RULES_V6[r], tools[name], (name, r))
        commit = next(t for t in ev3.s01_tools(defs) if t['function']['name'] == 'commit_recovery')
        self.assertIn('action_id', commit['function']['parameters']['properties'])
        self.assertNotIn('action_id', commit['function']['parameters']['required'])

    def test_prompts_and_tools_never_name_an_outcome_class_or_a_private_marker(self):
        defs = ObservableRunnerV6(factory(FIXTURES['s06-sudden-5d'])()).tool_definitions()
        blob = (ev3.S01_SYSTEM_PROMPT_V3 + json.dumps(ev3.s01_tools(defs))).lower()
        for word in OUTCOME_WORDS:
            self.assertNotIn(word, blob)
        for marker in ev1.PRIVATE_MARKERS:
            self.assertNotIn(marker, blob)


class ScriptedCalls:
    """A fake model that plays a fixed list of tool calls (arguments as the model would send them)."""

    def __init__(self, calls):
        self.calls, self.bodies = list(calls), []

    def __call__(self, request):
        self.bodies.append(request['body'].decode())
        call = self.calls.pop(0) if self.calls else ('advance_day', {})
        return t2._reply(*call)


class MockedModelEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {}
        ids = [f['fixture_id'] for f in FIXTURES.values()]
        for policy in POLICIES_V6:
            for fid, fx in FIXTURES.items():
                base = t2.PolicyModel(policy)
                g = t2.guarded(base, private_strings=ids)
                g.model, g.phase = MODEL, 's01'
                raw = ev3.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
                cls.results[(fid, policy)] = (raw, ev3.grade_s01(fx, raw), g, base)

    def test_twenty_five_episodes_complete_feasible_replayed_and_clean(self):
        self.assertEqual(len(self.results), 25)
        for key, (raw, grade, g, _) in self.results.items():
            self.assertEqual(grade['status'], 'complete', key)
            self.assertTrue(grade['verifier_feasible'], (key, grade['hard_violation_codes']))
            self.assertTrue(grade['replay_reproduced'], (key, grade['replay_differences']))
            self.assertEqual(grade['observation_leaks'], [], key)
            self.assertEqual(grade['invalid_actions'], 0, key)
            self.assertEqual(g.leak_flags, [], key)
            self.assertIsNone(g.refused, key)

    def test_the_model_path_reaches_the_same_scorecard_as_the_direct_run_and_the_hand_ledgers(self):
        for (fid, policy), (raw, _, _, _) in self.results.items():
            direct = run_episode(FIXTURES[fid], policy)
            self.assertEqual(raw['transcript']['scorecard'], direct['scorecard'], (fid, policy))
            self.assertTrue(all(direct['hand'].values()), (fid, policy))

    def test_every_observation_the_model_saw_carries_the_opaque_label_and_the_conventions_block(self):
        for (fid, policy), (raw, _, _, _) in self.results.items():
            label = FIXTURES[fid]['scenario']['scenario_id']
            self.assertTrue(raw['observed'])
            for o in raw['observed']:
                self.assertEqual(o['state']['scenario_id'], label)
                self.assertEqual(o['rules']['conventions']['statements'], CONVENTION_STATEMENTS)

    def test_no_request_names_a_fixture_or_an_outcome_class_before_the_firm_notice(self):
        for (fid, policy), (_, _, _, base) in self.results.items():
            for body in base.bodies:
                low = body.lower()
                self.assertNotIn('s06-', low)
                if NOTICE_MARK not in body:
                    for word in OUTCOME_WORDS:
                        self.assertNotIn(word, low, (fid, policy, word))

    def test_the_paired_scenarios_send_byte_identical_requests_until_the_firm_notice(self):
        for policy in POLICIES_V6:
            a = self.results[('s06-warned-delayed-10d', policy)][3].bodies
            b = self.results[('s06-warned-no-delay-10d', policy)][3].bodies
            ka = next((i for i, t in enumerate(a) if NOTICE_MARK in t), len(a))
            kb = next((i for i, t in enumerate(b) if NOTICE_MARK in t), len(b))
            self.assertEqual(ka, kb)
            self.assertGreater(ka, 0)
            self.assertEqual(a[:ka], b[:kb], policy)

    def test_a_model_that_resends_the_same_purchase_without_an_id_is_refused_and_one_with_distinct_ids_is_not(self):
        fx = FIXTURES['s06-sudden-5d']
        buy = ('commit_recovery', {'choice': 'alternate', 'quantity': 1})
        keyed = lambda k: ('commit_recovery', {'choice': 'alternate', 'quantity': 1, 'action_id': k})  # noqa: E731
        for name, calls, accepted in (('without ids', [buy, buy], [True, False]),
                                      ('distinct ids', [keyed('lot-a'), keyed('lot-b')], [True, True]),
                                      ('the same id', [keyed('lot-a'), keyed('lot-a')], [True, False])):
            with self.subTest(case=name):
                model = ScriptedCalls(calls + [('advance_day', {})] * 5)
                g = t2.guarded(model, private_strings=[])
                g.model, g.phase = MODEL, 's01'
                raw = ev3.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
                commits = [a for a in raw['transcript']['attempts'] if a['tool'] == 'commit_recovery']
                self.assertEqual([a['accepted'] for a in commits[:2]], accepted)
                grade = ev3.grade_s01(fx, raw)
                self.assertTrue(grade['verifier_feasible'], grade['hard_violation_codes'])
                self.assertTrue(grade['replay_reproduced'], grade['replay_differences'])


class DraftManifest(unittest.TestCase):
    def test_the_draft_is_labelled_a_draft_with_no_model_call_and_a_zero_ceiling(self):
        m = ev3.draft_manifest()
        self.assertIn('DRAFT', m['status'])
        self.assertIn('no model call', m['status'])
        self.assertEqual(m['spend']['approved_ceiling_usd'], 0.0)
        self.assertEqual(m['s01_scenarios'], list(ev3.S01_ORDER_V6))
        self.assertEqual(set(m['s01_scenarios']), set(FIXTURES))
        self.assertEqual(m['prompts']['s01_system_prompt'], ev3.S01_SYSTEM_PROMPT_V3)
        body = {k: v for k, v in m.items() if k != 'manifest_sha256'}
        self.assertEqual(ev1.sha(body), m['manifest_sha256'])
        for rel, digest in m['harness_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest, rel)

    def test_the_draft_differs_from_the_eval19_2_prompt_and_leaves_the_frozen_first_run_alone(self):
        self.assertNotEqual(ev3.S01_SYSTEM_PROMPT_V3, ev2.S01_SYSTEM_PROMPT_V2)
        self.assertGreater(len(ev3.S01_SYSTEM_PROMPT_V3), len(ev2.S01_SYSTEM_PROMPT_V2))
        old = json.loads((ROOT / 'evidence/issue-19/manifest.json').read_text())
        for rel, digest in old['harness_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest, rel)
        self.assertNotIn('eval19_v3', ' '.join(old['harness_sha256']))

    def test_no_live_transport_is_ever_built_by_the_module(self):
        text = (SRC / 'eval19_v3.py').read_text()
        for forbidden in ('urllib_transport', 'urlopen', 'OPENROUTER', 'os.environ', 'requests'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
