"""Offline tests for the next-run harness `eval19_v2` (issue #19 fixes). No network, no credentials, mocked transports only.

Covers the three fixes end to end through the same entry points the live run uses (guard, adapter agent, observable
runner, independent verifier, replay, leak scan, strict grader), plus the rule that the first run record stays valid.
"""
import ast
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from supplychainworld import eval19 as ev1
from supplychainworld import eval19_v2 as ev2
from supplychainworld import llm_adapter as la
from supplychainworld import schemas_v121 as strict
from supplychainworld.agent_runner_v5 import (POLICIES_V5, REJECTION_RULES, RULES, TOOL_RULES, ObservableRunnerV5,
                                              rule_for_reason, scripted_policy_v5)
from supplychainworld.dynamic_demo_v5 import factory, load_fixtures, run_episode
from supplychainworld.dynamic_verifier_v5 import OUTCOME_WORDS

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src/supplychainworld'
FIXTURES = {f['fixture_id']: f for f in load_fixtures()}
CASES = ev2.load_static_cases()
SELECTED = ev2.select_static_cases(CASES)
MODEL = 'test/mock-model:free'
# The observation travels inside a JSON string, so its quotes are escaped in the request body.
NOTICE_MARK = 'notices\\": [{'


# --------------------------------------------------------------------------- mocked model transports

def _reply(tool, args):
    msg = {'role': 'assistant', 'content': None,
           'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': tool, 'arguments': json.dumps(args)}}]}
    body = {'choices': [{'message': msg, 'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}}
    return 200, {}, json.dumps(body).encode()


class PolicyModel:
    """A fake model: plays a declared scripted policy, reading only the latest observation in the request it receives."""

    def __init__(self, policy):
        self.policy, self.agents, self.bodies = policy, {}, []

    def __call__(self, request):
        text = request['body'].decode()
        self.bodies.append(text)
        body = json.loads(text)
        msgs = body['messages']
        initial = msgs[1]['content']
        agent = self.agents.setdefault((body['model'], initial), scripted_policy_v5(self.policy))
        last = next((json.loads(m['content']) for m in reversed(msgs) if m['role'] == 'tool'), None)
        obs = last if last is not None else json.loads(initial.split('Initial observation: ', 1)[1])['observation']
        call = agent({'state': obs['state'], 'rules': obs['rules'], 'clock': obs['clock'], 'last_outcome': obs['last_outcome']})
        return _reply(call['tool'], call['arguments'])


def guarded(base, **kw):
    kw.setdefault('sleep', lambda s: None)
    kw.setdefault('min_interval', 0.0)
    return ev1.Guard(base, **kw)


# --------------------------------------------------------------------------- source scan for rejection reasons

def literal_text(node):
    """The constant text of a string expression: a literal, an f-string (constant parts) or 'text' + something."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(v.value for v in node.values if isinstance(v, ast.Constant))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return literal_text(node.left) or literal_text(node.right)
    return None


def reasons_in(source):
    """Every rejection reason text found in source: `_reject(kind, details, reason)` calls and the
    `return 'category', 'reason'` pairs of a runner's validation."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == '_reject' \
                and len(node.args) >= 3:
            t = literal_text(node.args[2])
            if t:
                out.append(t)
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2 \
                and isinstance(node.value.elts[0], ast.Constant) and isinstance(node.value.elts[0].value, str):
            t = literal_text(node.value.elts[1])
            if t:
                out.append(t)
    return out


ENFORCING_SOURCES = ('dynamic_v3.py', 'dynamic_v4.py', 'dynamic_v5.py', 'agent_runner_v3.py', 'agent_runner_v4.py',
                     'agent_runner_v5.py')


def all_reasons():
    found = {}
    for name in ENFORCING_SOURCES:
        for r in reasons_in((SRC / name).read_text()):
            found.setdefault(r, []).append(name)
    return found


class StatedRulesTests(unittest.TestCase):
    """Finding 2: every rule the world enforces is stated to the model, and cannot silently diverge again."""

    def test_the_scan_finds_the_reasons_the_world_and_runner_can_give(self):
        found = all_reasons()
        self.assertGreaterEqual(len(found), 20)
        for must in ('production exceeds open customer demand', 'recovery budget exceeded',
                     'capacity or available material exceeded', 'daily production already released',
                     'per-day attempt limit reached; advance the day'):
            self.assertIn(must, found)

    def test_every_enforced_rejection_reason_maps_to_a_rule(self):
        for reason, files in all_reasons().items():
            self.assertIsNotNone(rule_for_reason(reason), f'{reason!r} ({files}) has no stated rule in agent_runner_v5.REJECTION_RULES')

    def test_every_mapped_rule_sentence_is_in_the_system_prompt(self):
        for reason in all_reasons():
            sentence = RULES[rule_for_reason(reason)]
            self.assertIn(sentence, ev2.S01_SYSTEM_PROMPT_V2, reason)

    def test_every_mapped_rule_is_also_in_a_tool_description_except_the_episode_end(self):
        descriptions = ' '.join(ev2.S01_DESCRIPTIONS_V2.values())
        for reason in all_reasons():
            rule = rule_for_reason(reason)
            if rule == 'episode_closed':
                continue
            self.assertIn(RULES[rule], descriptions, (reason, rule))

    def test_the_tool_schemas_the_model_receives_carry_the_same_sentences(self):
        defs = ObservableRunnerV5(factory(FIXTURES['s05-sudden-5d'])()).tool_definitions()
        tools = {t['function']['name']: t['function']['description'] for t in ev2.s01_tools(defs)}
        self.assertEqual(set(tools), set(TOOL_RULES))
        for name, rules in TOOL_RULES.items():
            for r in rules:
                self.assertIn(RULES[r], tools[name], (name, r))

    def test_the_production_rule_found_in_the_first_diagnostic_is_now_stated(self):
        self.assertIn('Production cannot exceed open customer demand', ev2.S01_SYSTEM_PROMPT_V2)
        self.assertIn('open_demand', ev2.S01_DESCRIPTIONS_V2['release_production'])
        for old in (ev1.S01_SYSTEM_PROMPT, ' '.join(ev1.S01_DESCRIPTIONS.values())):
            self.assertNotIn('open customer demand', old)          # the gap the diagnostic found

    def test_capacity_components_once_per_day_budget_once_only_attempt_limit_and_tiers_are_all_stated(self):
        p = ev2.S01_SYSTEM_PROMPT_V2.lower()
        for phrase in ('daily capacity', 'components on hand', 'once per day', 'recovery budget', 'cannot be undone',
                       'at most 12 tool calls', 'cancel_after', 'priority tier', 'salvage', 'open customer demand'):
            self.assertIn(phrase, p)

    def test_a_new_unmapped_rejection_would_be_caught(self):
        src = "class W:\n    def go(self):\n        return self._reject('x', {}, 'a brand new rule nobody stated')\n"
        self.assertEqual(reasons_in(src), ['a brand new rule nobody stated'])
        self.assertIsNone(rule_for_reason('a brand new rule nobody stated'))

    def test_every_rule_in_the_table_is_used_by_a_reason_or_is_a_stated_consequence(self):
        used = {rule for _, rule in REJECTION_RULES}
        consequences = set(RULES) - used
        self.assertEqual(consequences, {'shipping', 'penalties_cancel', 'salvage'})

    def test_prompts_and_tools_never_name_an_outcome_class_or_a_private_marker(self):
        defs = ObservableRunnerV5(factory(FIXTURES['s05-sudden-5d'])()).tool_definitions()
        blob = (ev2.S01_SYSTEM_PROMPT_V2 + json.dumps(ev2.s01_tools(defs))).lower()
        for word in OUTCOME_WORDS:
            self.assertNotIn(word, blob)
        for marker in ev1.PRIVATE_MARKERS:
            self.assertNotIn(marker, blob)


# --------------------------------------------------------------------------- end to end: S01 through the model harness

class S01EndToEnd(unittest.TestCase):
    """25 episodes (5 scenarios x 5 declared policies) played by a mocked model through the real adapter path."""

    @classmethod
    def setUpClass(cls):
        cls.results = {}
        cls.bodies = {}
        for policy in POLICIES_V5:
            model = PolicyModel(policy)
            for fid, fx in FIXTURES.items():
                base = PolicyModel(policy)
                g = guarded(base, private_strings=[f['fixture_id'] for f in FIXTURES.values()])
                g.model, g.phase = MODEL, 's01'
                raw = ev2.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
                cls.results[(fid, policy)] = (raw, ev2.grade_s01(fx, raw), g, base)
            del model

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
        for (fid, policy), (raw, grade, _, _) in self.results.items():
            direct = run_episode(FIXTURES[fid], policy)
            self.assertEqual(raw['transcript']['scorecard'], direct['scorecard'], (fid, policy))
            self.assertTrue(all(direct['hand'].values()), (fid, policy))

    def test_every_observation_the_model_saw_has_only_the_opaque_label(self):
        for (fid, policy), (raw, _, _, _) in self.results.items():
            label = FIXTURES[fid]['scenario']['scenario_id']
            self.assertTrue(raw['observed'])
            for o in raw['observed']:
                self.assertEqual(o['state']['scenario_id'], label)

    def test_no_request_ever_contains_a_fixture_name_or_outcome_class_before_the_firm_notice(self):
        for (fid, policy), (_, _, _, base) in self.results.items():
            for body in base.bodies:
                low = body.lower()
                self.assertNotIn('s05-', low)
                self.assertNotIn('s04-', low)
                if NOTICE_MARK not in body:
                    for word in OUTCOME_WORDS:
                        self.assertNotIn(word, low, (fid, policy, word))

    def test_the_paired_scenarios_send_byte_identical_requests_until_the_firm_notice(self):
        for policy in POLICIES_V5:
            a = self.results[('s05-warned-delayed-10d', policy)][3].bodies
            b = self.results[('s05-warned-no-delay-10d', policy)][3].bodies
            ka = next((i for i, t in enumerate(a) if NOTICE_MARK in t), len(a))
            kb = next((i for i, t in enumerate(b) if NOTICE_MARK in t), len(b))
            self.assertEqual(ka, kb)
            self.assertGreater(ka, 0)
            self.assertEqual(a[:ka], b[:kb], policy)

    def test_the_first_runs_world_would_have_failed_this_check(self):
        """Regression anchor: with the v0.4 world the paired scenarios were NOT identical before the notice."""
        from supplychainworld import eval19 as first
        f4 = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.4/scenarios.json').read_text())['fixtures']}
        texts = []
        for fid in ('s04-warned-delayed-10d', 's04-warned-no-delay-10d'):
            from supplychainworld.agent_runner_v4 import ObservableRunnerV4
            from supplychainworld.dynamic_demo_v4 import factory as factory4
            runner = ObservableRunnerV4(factory4(f4[fid])())
            texts.append(json.dumps(runner.view()['state']))
        self.assertNotEqual(texts[0], texts[1])
        self.assertIn('warned-delayed', texts[0])
        self.assertTrue(first.S01_ORDER[0].startswith('s04-'))

    def test_a_world_that_leaked_the_class_would_be_failed_by_the_grade(self):
        """Mutation check: a leaking world is caught by the same independent scan the run uses."""
        fx = FIXTURES['s05-warned-delayed-10d']
        raw, _, _, _ = self.results[('s05-warned-delayed-10d', 'maintain')]
        bad = json.loads(json.dumps({k: raw[k] for k in ('observed',)}))
        bad['observed'][0]['state']['scenario_id'] = 'warned-delayed'
        from supplychainworld.dynamic_verifier_v5 import check_observations_for_leaks
        self.assertTrue(check_observations_for_leaks(fx['scenario'], bad['observed']))


# --------------------------------------------------------------------------- end to end: static through the model harness

class StaticModel:
    """Fake model answering each case with a scripted submission through the named tool."""

    def __init__(self, tool, answer):
        self.tool, self.answer, self.bodies = tool, answer, []

    def __call__(self, request):
        self.bodies.append(request['body'].decode())
        return _reply(self.tool(), self.answer())


class StaticEndToEnd(unittest.TestCase):
    def run_case(self, cid, tool, answer):
        base = StaticModel(lambda: tool, lambda: answer)
        g = guarded(base, private_strings=ev1.static_private_strings(CASES[cid]))
        g.model, g.phase = MODEL, 'static'
        raw = ev2.run_static_case(CASES[cid], MODEL, g, sleep=lambda s: None)
        return raw, ev2.grade_static(CASES[cid], raw['submission']), base, g

    def test_the_expected_answer_through_the_right_tool_is_credited_for_all_33_cases(self):
        self.assertEqual(len(CASES), 33)
        for cid, case in CASES.items():
            sub = case['expected']['submission']
            raw, grade, base, g = self.run_case(cid, strict.TOOL_NAMES[sub['kind']], sub)
            self.assertEqual(raw['status'], 'submitted', cid)
            self.assertTrue(grade['accepted'], (cid, grade))
            self.assertEqual(g.leak_flags, [])
            for secret in ev1.static_private_strings(case):
                self.assertNotIn(secret, base.bodies[0])

    def test_the_request_offers_three_tools_one_per_kind_and_states_the_shape(self):
        raw, _, base, _ = self.run_case('ref-09', 'submit_clarification', CASES['ref-09']['expected']['submission'])
        body = json.loads(base.bodies[0])
        self.assertEqual([t['function']['name'] for t in body['tools']], ['submit_award', 'submit_clarification', 'submit_infeasible'])
        self.assertIn('exactly the fields listed', body['messages'][0]['content'])
        self.assertNotIn('submit_decision', json.dumps(body))
        clar = next(t for t in body['tools'] if t['function']['name'] == 'submit_clarification')
        self.assertEqual(set(clar['function']['parameters']['properties']), {'kind', 'field', 'disposition', 'evidence'})

    def test_the_first_run_failure_modes_get_no_credit_and_a_clear_message_and_are_not_repaired(self):
        # 1. clarification with award fields (seen with ref-09 and ref-30)
        for cid in ('ref-09', 'ref-30'):
            sub = dict(CASES[cid]['expected']['submission'], clarification_requests=[], approval_refs=[], allocations=[])
            raw, grade, _, _ = self.run_case(cid, 'submit_clarification', sub)
            self.assertFalse(grade['accepted'])
            self.assertEqual(grade['hard_failures'], ['strict_schema'])
            self.assertEqual(len(grade['strict_problems']), 3)
            self.assertEqual(raw['submission'], sub)                 # passed on exactly as sent, nothing dropped
        # 2. evidence as one string (seen with ref-01, ref-25, ref-29)
        for cid in ('ref-01', 'ref-25', 'ref-29'):
            sub = dict(CASES[cid]['expected']['submission'])
            sub['evidence'] = json.dumps(sub['evidence'])
            _, grade, _, _ = self.run_case(cid, strict.TOOL_NAMES[sub['kind']], sub)
            self.assertFalse(grade['accepted'], cid)
            self.assertIn(f"{sub['kind']}: evidence must be a list of strings", grade['strict_problems'])

    def test_a_missing_field_is_rejected_and_names_it(self):
        sub = dict(CASES['ref-10']['expected']['submission'])
        del sub['evidence']
        _, grade, _, _ = self.run_case('ref-10', 'submit_infeasible', sub)
        self.assertFalse(grade['accepted'])
        self.assertTrue(any("missing required field 'evidence'" in p for p in grade['strict_problems']))

    def test_the_wrong_tool_for_the_kind_is_no_submission_not_a_guess(self):
        sub = CASES['ref-10']['expected']['submission']
        raw, grade, _, _ = self.run_case('ref-10', 'submit_award', sub)
        self.assertEqual(raw['status'], 'tool_kind_mismatch')
        self.assertIsNone(raw['submission'])
        self.assertEqual(raw['failure']['error_class'], 'tool_kind_mismatch')
        self.assertFalse(grade['graded'])

    def test_the_old_tool_name_is_not_accepted(self):
        sub = CASES['ref-10']['expected']['submission']
        raw, _, _, _ = self.run_case('ref-10', 'submit_decision', sub)
        self.assertEqual(raw['status'], 'no_usable_submission')

    def test_baselines_pass_the_same_strict_grader(self):
        for cid in ('ref-01', 'ref-09', 'ref-10'):
            r = ev2.static_baseline(CASES[cid], 'reference')
            self.assertTrue(r['graded'], (cid, r))
            self.assertTrue(r['accepted'], (cid, r))


# --------------------------------------------------------------------------- the first run record stays valid; the new run is separate

class VersioningTests(unittest.TestCase):
    OLD = json.loads((ROOT / 'evidence/issue-19/manifest.json').read_text())

    def test_every_file_the_first_manifest_froze_is_unchanged(self):
        for rel, digest in self.OLD['harness_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest, rel)
        for rel, digest in self.OLD['development_set']['s01_v0.4']['fixture_file_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest, rel)

    def test_the_first_manifest_still_matches_its_own_hash(self):
        body = {k: v for k, v in self.OLD.items() if k != 'manifest_sha256'}
        self.assertEqual(ev1.sha(body), self.OLD['manifest_sha256'])

    def test_the_new_manifest_bumps_version_and_hash_fields_and_names_its_predecessor(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import run_eval19_v2 as run2
        m = run2.build_manifest()
        self.assertEqual(m['schema'], 'eval19-manifest-2')
        self.assertEqual(m['harness_version'], 'eval19-2')
        self.assertNotEqual(m['schema'], self.OLD['schema'])
        self.assertNotEqual(m['manifest_sha256'], self.OLD['manifest_sha256'])
        self.assertEqual(m['predecessor']['manifest_sha256'], self.OLD['manifest_sha256'])
        self.assertEqual(m['predecessor']['harness_sha256'], self.OLD['harness_sha256'])
        self.assertFalse(m['preregistered_before_any_model_attempt'])
        self.assertIn('DRAFT', m['preregistration_status'])
        for rel in ('src/supplychainworld/eval19_v2.py', 'src/supplychainworld/schemas_v121.py',
                    'src/supplychainworld/dynamic_v5.py', 'src/supplychainworld/dynamic_verifier_v5.py',
                    'scripts/run_eval19_v2.py'):
            self.assertIn(rel, m['harness_sha256'])
            self.assertEqual(m['harness_sha256'][rel], hashlib.sha256((ROOT / rel).read_bytes()).hexdigest())
        self.assertEqual(len(m['changes_from_predecessor']), 3)
        self.assertEqual(m['prompts']['s01_system_prompt'], ev2.S01_SYSTEM_PROMPT_V2)
        self.assertEqual([t['function']['name'] for t in m['tool_profile']['static']['tools']],
                         ['submit_award', 'submit_clarification', 'submit_infeasible'])
        self.assertEqual([s['fixture_id'] for s in m['development_set']['s01_v0.5']['scenarios']], list(ev2.S01_ORDER))
        body = {k: v for k, v in m.items() if k != 'manifest_sha256'}
        self.assertEqual(ev1.sha(body), m['manifest_sha256'])
        self.assertEqual(m['spend']['approved_ceiling_usd'], 0.0)

    def test_the_old_prompts_are_not_the_new_prompts(self):
        self.assertNotEqual(ev2.S01_SYSTEM_PROMPT_V2, ev1.S01_SYSTEM_PROMPT)
        self.assertNotEqual(ev2.STATIC_SYSTEM_PROMPT_V2, ev1.STATIC_SYSTEM_PROMPT)
        self.assertNotIn('submit_decision', ev2.STATIC_SYSTEM_PROMPT_V2)
        self.assertEqual(ev1.TOTAL_REQUEST_CAP, ev2.TOTAL_REQUEST_CAP)        # limits carried over unchanged

    def test_free_models_only_still_holds_for_the_new_configs(self):
        with self.assertRaises(la.ModelNotAllowedError):
            ev2.s01_config('openai/gpt-4o', 5)
        with self.assertRaises(la.ModelNotAllowedError):
            ev2.static_config('openai/gpt-4o')


class WholeRunScript(unittest.TestCase):
    """The run script's whole live loop and report, with the network replaced by a mock. Proves the wiring."""

    def test_probe_s01_static_and_report_run_offline_with_the_new_harness(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import run_eval19_v2 as run2
        self.assertIs(run2.base.ev, ev2)

        class Router:
            """S01 requests get the scripted policy; static requests get the expected answer for the case in the prompt."""

            def __init__(self):
                self.s01, self.requests, self.static_seen = PolicyModel('alternate_on_alert'), 0, 0

            def __call__(self, request):
                self.requests += 1
                body = json.loads(request['body'])
                if any(t['function']['name'].startswith('submit_') for t in body['tools']):
                    self.static_seen += 1
                    world = json.loads(body['messages'][1]['content'].split('Visible world (JSON):\n', 1)[1])
                    case = next(c for c in CASES.values() if c['world'] == world)
                    sub = case['expected']['submission']
                    return _reply(strict.TOOL_NAMES[sub['kind']], sub)
                return self.s01(request)

        router = Router()
        real_guard = ev1.Guard

        def fast_guard(base, **kw):
            return real_guard(base, sleep=lambda s: None, min_interval=0.0, **kw)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(la, 'urllib_transport', lambda req, timeout=0: router(req)), \
                mock.patch.object(ev2, 'Guard', fast_guard), \
                mock.patch.object(ev2, 'ROSTER_CORE', (MODEL,)), mock.patch.object(ev2, 'ROSTER_CONDITIONAL', ()), \
                mock.patch.dict(os.environ, {la.CREDENTIAL_ENV: 'test-key-not-real'}):
            state, out = Path(tmp) / 'state', Path(tmp) / 'out'
            run2.base.run(state)
            run2.base.report(state, out)
            card = json.loads((out / 'scorecard.json').read_text())
            self.assertEqual(card['request_totals']['cap'], 250)
            pm = card['per_model'][MODEL]
            self.assertEqual(pm['s01']['episodes_run'], 5)
            self.assertEqual(pm['s01']['verifier_feasible'], 5)
            self.assertEqual(pm['s01']['replay_reproduced'], 5)
            self.assertEqual(pm['s01']['invalid_actions'], 0)
            self.assertEqual(pm['static']['cases_run'], 20)
            self.assertEqual(pm['static']['accepted'], 20)
            self.assertEqual(pm['static']['schema_valid'], 20)
            self.assertEqual(router.static_seen, 20)
            # sanitized run records name the v0.5 fixtures, carry the opaque label only, and hold no raw state
            runs = sorted((out / 'runs').glob('s01__*'))
            self.assertEqual(len(runs), 5)
            for p in runs:
                rec = json.loads(p.read_text())
                self.assertEqual(rec['observation_leaks'], [])
            ledger = (out / 'request-ledger.jsonl').read_text()
            self.assertNotIn('test-key-not-real', ledger)
            self.assertLessEqual(card['request_totals']['ledger_requests'], 250)
            self.assertEqual(router.requests, card['request_totals']['ledger_requests'])


if __name__ == '__main__':
    unittest.main()
