"""S01 v0.6: fixtures, generators, independence of the checker, and pinned examples.

Property and fuzz coverage is in test_s01_v6_property.py and test_s01_v6_fuzz.py; the S01.3 assessment is in
test_s01_v6_assessment_property.py; the demonstration packet in test_s01_v6_e2e.py; the page in test_s01_v6_browser.py.
"""
import ast
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

import support  # noqa: F401
from supplychainworld import dynamic_demo_v6 as demo
from supplychainworld import dynamic_verifier_v6 as dv6
from supplychainworld.agent_runner_v6 import ObservableRunnerV6, scripted_policy_v6
from supplychainworld.dynamic_v5 import LABEL_PATTERN, opaque_label
from supplychainworld.dynamic_v6 import AUTO_PREFIX, OperationalWorldV6, ScenarioV6

ROOT = Path(__file__).resolve().parents[1]
V5 = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.5/scenarios.json').read_text())['fixtures']}
V6 = {f['fixture_id']: f for f in demo.load_fixtures()}


def imports_of(path):
    out = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out |= {('.' * node.level) + (node.module or '') + ':' + a.name for a in node.names}
    return out


class FixtureTests(unittest.TestCase):
    def test_five_scenarios_with_the_v05_numbers_and_the_same_opaque_labels(self):
        self.assertEqual(len(V6), 5)
        for fid, f in V6.items():
            old = V5[fid.replace('s06-', 's05-')]
            self.assertEqual(f['scenario'], old['scenario'])
            self.assertRegex(f['scenario']['scenario_id'], LABEL_PATTERN)
            self.assertEqual(f['scenario']['scenario_id'], opaque_label(f['scenario']))
            self.assertEqual((f['horizon_days'], f['disruption_class']), (old['horizon_days'], old['disruption_class']))

    def test_fixtures_and_hand_ledgers_equal_their_generators_output(self):
        for script in ('generate_fixtures_v06.py', 'generate_hand_ledgers_v06.py'):
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--check'], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_generators_import_nothing_from_the_project(self):
        for script in ('generate_fixtures_v06.py', 'generate_hand_ledgers_v06.py'):
            for name in imports_of(ROOT / 'scripts' / script):
                self.assertNotIn('supplychainworld', name, script)

    def test_the_hand_ledgers_cover_25_episodes(self):
        hand = demo.load_hand()
        self.assertEqual(sorted(hand), sorted(V6))
        self.assertEqual(sum(len(v) for v in hand.values()), 25)


class CheckerIsIndependent(unittest.TestCase):
    def test_the_v06_checker_imports_only_the_standard_library_and_earlier_checkers(self):
        names = imports_of(ROOT / 'src/supplychainworld/dynamic_verifier_v6.py')
        self.assertEqual(names, {'hashlib', '.:dynamic_verifier_v4', '.:dynamic_verifier_v5'})

    def test_the_earlier_checkers_it_builds_on_do_not_import_the_simulator_either(self):
        self.assertEqual(imports_of(ROOT / 'src/supplychainworld/dynamic_verifier_v4.py'), {'dataclasses:dataclass', 'dataclasses:field'})
        self.assertEqual(imports_of(ROOT / 'src/supplychainworld/dynamic_verifier_v5.py'),
                         {'hashlib', 'json', '.:dynamic_verifier_v4'})

    def test_no_simulator_runner_or_policy_module_is_loaded_by_importing_the_checker_alone(self):
        code = ('import sys; import supplychainworld.dynamic_verifier_v6; '
                'import re; bad=[m for m in sys.modules if m.startswith("supplychainworld.") and (re.search(r"dynamic_v\\d", m) '
                'or any(k in m for k in ("agent_runner", "baselines", "environment", "solvers")) or m.endswith(".dynamic"))]; print(bad)')
        done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                              env={'PYTHONPATH': str(ROOT / 'src'), 'PATH': '/usr/bin:/bin'})
        self.assertEqual(done.stdout.strip(), '[]', done.stderr)

    def _sabotaged(self, fid, policy, hook):
        """A world with a wrong rule still self-reports a scorecard; the checker derives its own from the commands."""
        f = V6[fid]

        class Wrong(OperationalWorldV6):
            def close_day(self):
                r = super().close_day()
                hook(self)
                return r
        w = Wrong(f['horizon_days'], scenario=ScenarioV6(**f['scenario']))
        ObservableRunnerV6(w).run(scripted_policy_v6(policy))
        return dv6.verify_episode(f['scenario'], w.history(), horizon_days=f['horizon_days'], scorecard=w.scorecard())

    def test_a_simulator_that_breaks_a_rule_is_caught_not_trusted(self):
        def extra_penalty(w):
            w._s['penalties'] += 1

        def conjured_component(w):
            w._s['component_on_hand'] += 1

        def lost_goods(w):
            w._s['delivered_total'] += 1
        for name, hook in (('extra penalty', extra_penalty), ('conjured component', conjured_component),
                           ('goods delivered from nowhere', lost_goods)):
            with self.subTest(sabotage=name):
                report = self._sabotaged('s06-multitier-cancel-10d', 'maintain', hook)
                self.assertTrue(report.violations)


class ExamplesTests(unittest.TestCase):
    def test_the_scenario_class_accepts_only_version_6_and_the_opaque_label(self):
        sc = deepcopy(V6['s06-sudden-5d']['scenario'])
        ScenarioV6(**sc)
        ScenarioV6(**dict(sc, schema_version='6.0', runtime_version='6.0'))
        for bad in ('5.0', '4.0', 6):
            with self.assertRaises(ValueError):
                ScenarioV6(**dict(sc, schema_version=bad))
        with self.assertRaises(ValueError):
            ScenarioV6(**dict(sc, scenario_id='s06-sudden-5d'))

    def test_state_carries_the_6_0_version_fields_and_the_scorecard_schema(self):
        w = demo.factory(V6['s06-sudden-5d'])()
        s = w.snapshot()
        self.assertEqual((s['schema_version'], s['runtime_version']), ('6.0', '6.0'))
        for _ in range(5):
            w.release_production(0)
            w.close_day()
        self.assertEqual(w.scorecard()['schema'], 'dyn-scorecard-6')

    def test_the_conventions_block_has_one_statement_per_stated_fact_and_numbers_match_the_rules(self):
        block = ObservableRunnerV6(demo.factory(V6['s06-multitier-cancel-10d'])()).view()['rules']['conventions']
        self.assertEqual(sorted(block), ['parameters', 'statements'])
        for needed in ('receipts_usable_on_arrival_day', 'shipping_starts_on', 'shipping_priority', 'cancellation',
                       'penalty_rate_unit_percent_of_value', 'penalty_rate_unit_fixed_per_unit',
                       'penalty_rate_unit_per_unit_per_day', 'penalty_cap', 'production_completes_at', 'repeated_purchase'):
            self.assertIn(needed, block['statements'])
        self.assertIn('basis points', block['statements']['penalty_rate_unit_percent_of_value'])
        self.assertEqual(block['parameters']['penalty_rate_divisor_percent_of_value'], 10000)
        self.assertEqual(block['parameters']['auto_key_prefix'], AUTO_PREFIX)

    def test_the_conventions_do_not_change_any_number_the_v05_world_produces(self):
        from supplychainworld.agent_runner_v5 import ObservableRunnerV5
        from supplychainworld.dynamic_demo_v5 import factory as f5
        for fid, f in V6.items():
            for policy in ('maintain', 'combo_on_alert', 'staged_revisit'):
                a = ObservableRunnerV6(demo.factory(f)()).run(scripted_policy_v6(policy))
                b = ObservableRunnerV5(f5(V5[fid.replace('s06-', 's05-')])()).run(scripted_policy_v6(policy))
                self.assertEqual(a['scorecard']['cost']['net_cost'], b['scorecard']['cost']['net_cost'], (fid, policy))
                self.assertEqual({k: v for k, v in a['scorecard'].items() if k != 'schema'},
                                 {k: v for k, v in b['scorecard'].items() if k != 'schema'}, (fid, policy))


if __name__ == '__main__':
    unittest.main()
