"""Property tests for the strict per-kind submission schema, static rules 1.2.1 (issue #19 fixes, finding 3).

Generated valid answers of every kind are accepted; generated mutations (one extra field, or one missing field) are
rejected with a message that names the field and the kind; nothing is repaired. The frozen 1.2 contract is unchanged.
"""
import copy
import json
import unittest
from pathlib import Path

from hypothesis import given, strategies as st

import support  # noqa: F401

from supplychainworld import schemas_v12 as s12
from supplychainworld import schemas_v121 as strict

ROOT = Path(__file__).resolve().parents[1]
CASES = {p.stem: json.loads(p.read_text()) for p in sorted((ROOT / 'fixtures/reference_cases_v1_2').glob('ref-*.json'))}

ident = st.from_regex(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,8}', fullmatch=True)
words = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=30)
text_list = st.lists(words, max_size=3)
evidence = st.lists(words, min_size=1, max_size=3)
money = st.decimals(min_value=0, max_value=10**6, places=2, allow_nan=False).map(str)


@st.composite
def awards(draw):
    pairs = draw(st.lists(st.tuples(ident, ident), max_size=4, unique=True))
    allocs = [{'supplier_id': s, 'item_id': i, 'quantity': draw(st.integers(0, 500))} for s, i in pairs]
    return {'kind': 'award', 'allocations': allocs, 'claimed_total_cost': draw(money), 'evidence': draw(evidence),
            'flags': draw(text_list), 'clarification_requests': draw(text_list), 'approval_refs': draw(text_list)}


clarifications = st.builds(lambda f, e: {'kind': 'clarification', 'field': f, 'disposition': 'record_and_escalate', 'evidence': e},
                           words, evidence)
infeasibles = st.builds(lambda e: {'kind': 'infeasible', 'evidence': e}, evidence)
valid_submissions = st.one_of(awards(), clarifications, infeasibles)
extra_keys = st.sampled_from(['allocations', 'claimed_total_cost', 'flags', 'clarification_requests', 'approval_refs',
                              'field', 'disposition', 'schema_version', 'note', 'reasoning', 'confidence'])


class StrictAcceptsValid(unittest.TestCase):
    @given(valid_submissions)
    def test_generated_valid_submissions_are_accepted(self, sub):
        self.assertEqual(strict.strict_problems(sub), [])
        parsed = strict.parse_strict_submission(sub)
        self.assertEqual(parsed.kind, sub['kind'])
        self.assertEqual(set(strict.FIELDS[sub['kind']]), set(sub))

    def test_every_committed_expected_answer_is_accepted(self):
        self.assertEqual(len(CASES), 33)
        for cid, c in CASES.items():
            self.assertEqual(strict.strict_problems(c['expected']['submission']), [], cid)

    def test_frozen_v12_still_accepts_its_loose_forms(self):
        """1.2 is untouched: the loose shapes 1.2 allowed are still valid there and still invalid in 1.2.1."""
        loose = {'kind': 'infeasible', 'evidence': ['x capacity less than y']}
        self.assertEqual(s12.parse_submission(loose).kind, 'infeasible')
        loose_award = {'kind': 'award', 'allocations': [], 'claimed_total_cost': '0', 'evidence': ['e']}     # optional lists omitted
        self.assertEqual(s12.parse_submission(loose_award).kind, 'award')
        self.assertTrue(strict.strict_problems(loose_award))


class StrictRejectsMutations(unittest.TestCase):
    @given(valid_submissions, extra_keys, st.data())
    def test_one_extra_field_is_rejected_naming_the_field_and_kind(self, sub, key, data):
        kind = sub['kind']
        if key in sub:
            return
        bad = dict(sub, **{key: data.draw(st.one_of(st.none(), words, st.lists(words, max_size=2)))})
        problems = strict.strict_problems(bad)
        self.assertTrue(problems)
        self.assertTrue(any(f"'{key}'" in p and kind in p and 'not allowed' in p for p in problems), problems)
        with self.assertRaises(strict.StrictSubmissionError) as ctx:
            strict.parse_strict_submission(bad)
        self.assertEqual(ctx.exception.problems, problems)

    @given(valid_submissions, st.data())
    def test_one_missing_field_is_rejected_naming_the_field_and_kind(self, sub, data):
        kind = sub['kind']
        key = data.draw(st.sampled_from([k for k in strict.FIELDS[kind] if k != 'kind']))
        bad = {k: v for k, v in sub.items() if k != key}
        problems = strict.strict_problems(bad)
        self.assertTrue(any(f"missing required field '{key}'" in p and kind in p for p in problems), problems)

    WRONG = {
        'allocations': ['a string', 123, None, {'a': 1}, [1], [{'supplier_id': 'S'}]],
        'claimed_total_cost': [123, 12.5, True, None, ['1'], '', '   '],
        'evidence': ['a string', 123, None, [], [''], ['x', 1], {'a': 1}],
        'flags': ['a string', 123, None, {'a': 1}, ['x', 1]],
        'clarification_requests': ['a string', 123, None, {'a': 1}, ['x', 1]],
        'approval_refs': ['a string', 123, None, {'a': 1}, ['x', 1]],
        'field': [123, None, '', ['x']],
        'disposition': ['escalate', None, 123, 'RECORD_AND_ESCALATE'],
    }

    @given(valid_submissions, st.sampled_from(sorted(WRONG)), st.data())
    def test_every_wrong_type_or_value_is_rejected_not_coerced(self, sub, key, data):
        if key not in sub:
            return
        bad = dict(sub, **{key: data.draw(st.sampled_from(self.WRONG[key]))})
        problems = strict.strict_problems(bad)
        self.assertTrue(problems, (key, bad[key]))
        self.assertTrue(any(key in p for p in problems), problems)

    @given(valid_submissions)
    def test_extra_and_missing_together_report_both(self, sub):
        key = next(k for k in strict.FIELDS[sub['kind']] if k != 'kind')
        bad = {k: v for k, v in sub.items() if k != key}
        bad['zzz_unknown'] = 1
        joined = ' | '.join(strict.strict_problems(bad))
        self.assertIn("'zzz_unknown'", joined)
        self.assertIn(f"'{key}'", joined)

    def test_the_failure_modes_seen_in_the_first_diagnostic_are_each_rejected_with_a_clear_message(self):
        exc = copy.deepcopy(CASES['ref-09']['expected']['submission'])
        # clarification with award fields (ref-09 and ref-30 in the first run)
        bad = dict(exc, clarification_requests=['x'], approval_refs=[], allocations=[])
        problems = strict.strict_problems(bad)
        self.assertEqual(sorted(p.split("'")[1] for p in problems), ['allocations', 'approval_refs', 'clarification_requests'])
        # evidence sent as one string (ref-01, ref-25, ref-29 in the first run)
        aw = copy.deepcopy(CASES['ref-01']['expected']['submission'])
        aw['evidence'] = '["one", "two"]'
        self.assertIn('award: evidence must be a list of strings', strict.strict_problems(aw))

    @given(valid_submissions)
    def test_kind_is_required_and_must_be_known(self, sub):
        no_kind = {k: v for k, v in sub.items() if k != 'kind'}
        self.assertIn('kind must be one of', strict.strict_problems(no_kind)[0])
        self.assertIn('kind must be one of', strict.strict_problems(dict(sub, kind='Award'))[0])


class ToolSchemaMatchesTheShape(unittest.TestCase):
    def test_one_tool_per_kind_with_exactly_its_fields_all_required(self):
        names = set()
        for kind in strict.KINDS:
            fn = strict.json_schema(kind)['function']
            names.add(fn['name'])
            self.assertEqual(set(fn['parameters']['properties']), set(strict.FIELDS[kind]))
            self.assertEqual(fn['parameters']['required'], list(strict.FIELDS[kind]))
            self.assertIs(fn['parameters']['additionalProperties'], False)
            self.assertEqual(fn['parameters']['properties']['kind']['enum'], [kind])
        self.assertEqual(len(names), 3)

    @given(valid_submissions)
    def test_a_valid_submission_satisfies_its_own_tool_schema(self, sub):
        params = strict.json_schema(sub['kind'])['function']['parameters']
        self.assertEqual(set(sub), set(params['properties']))
        self.assertTrue(set(params['required']) <= set(sub))


if __name__ == '__main__':
    unittest.main()
