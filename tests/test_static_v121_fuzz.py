"""Fuzz tests for the strict submission schema (1.2.1) and its use in the eval19 v2 grader.

Arbitrary JSON, damaged real answers and hostile key names are fed in. Assert: never a crash, a verdict that is either
a clear list of problems or a valid exact-shape answer, and the grader never gives credit to an answer the strict
schema refused. Nothing is repaired.
"""
import copy
import json
import unittest
from pathlib import Path

from hypothesis import given, strategies as st

import support  # noqa: F401
from support import fuzz

from supplychainworld import eval19_v2 as ev2
from supplychainworld import schemas_v121 as strict

ROOT = Path(__file__).resolve().parents[1]
CASES = ev2.load_static_cases()
SELECTED = ev2.select_static_cases(CASES)


def damage(sub, data):
    out = copy.deepcopy(sub)
    kind = data.draw(st.sampled_from(['drop', 'add', 'replace', 'swap_kind', 'dup_alloc', 'nest']))
    keys = sorted(out)
    if kind == 'drop' and keys:
        del out[data.draw(st.sampled_from(keys))]
    elif kind == 'add':
        out[data.draw(st.text(min_size=1, max_size=12))] = data.draw(fuzz.json_blobs)
    elif kind == 'replace' and keys:
        out[data.draw(st.sampled_from(keys))] = data.draw(fuzz.json_blobs)
    elif kind == 'swap_kind':
        out['kind'] = data.draw(st.sampled_from(['award', 'clarification', 'infeasible', 'AWARD', '', None, 3]))
    elif kind == 'dup_alloc' and isinstance(out.get('allocations'), list) and out['allocations']:
        out['allocations'].append(copy.deepcopy(out['allocations'][0]))
    elif kind == 'nest':
        out = {'submission': out}
    return out


class StrictFuzz(unittest.TestCase):
    @given(fuzz.json_blobs)
    def test_arbitrary_json_never_crashes_and_valid_means_exact_shape(self, blob):
        problems = strict.strict_problems(blob)
        self.assertIsInstance(problems, list)
        if not problems:
            self.assertIsInstance(blob, dict)
            self.assertEqual(set(blob), set(strict.FIELDS[blob['kind']]))
            strict.parse_strict_submission(blob)       # and the frozen 1.2 model really accepts it
        else:
            with self.assertRaises(strict.StrictSubmissionError):
                strict.parse_strict_submission(blob)

    @given(st.sampled_from(SELECTED), st.data())
    def test_damaged_real_answers_are_refused_or_exactly_shaped(self, cid, data):
        good = CASES[cid]['expected']['submission']
        bad = damage(good, data)
        problems = strict.strict_problems(bad)
        if not problems:
            self.assertEqual(set(bad), set(strict.FIELDS[bad['kind']]))
        grade = ev2.grade_static(CASES[cid], bad)       # never crashes
        self.assertTrue(grade['graded'])
        if problems:
            self.assertFalse(grade['accepted'])
            self.assertFalse(grade['schema_valid'])
            self.assertEqual(grade['strict_problems'], problems)
            self.assertEqual(grade['hard_failures'], ['strict_schema'])

    @given(st.sampled_from(SELECTED), st.text(min_size=1, max_size=10))
    def test_an_extra_field_on_any_correct_answer_is_never_credited(self, cid, key):
        good = CASES[cid]['expected']['submission']
        if key in good:
            return
        grade = ev2.grade_static(CASES[cid], dict(good, **{key: 'x'}))
        self.assertFalse(grade['accepted'])
        self.assertEqual(grade['hard_failures'], ['strict_schema'])

    def test_the_correct_answer_for_every_selected_case_is_credited(self):
        for cid in SELECTED:
            grade = ev2.grade_static(CASES[cid], CASES[cid]['expected']['submission'])
            self.assertTrue(grade['accepted'], (cid, grade))
            self.assertEqual(grade['strict_problems'], [])

    @given(st.sampled_from(SELECTED), st.sampled_from(['"', '{', '[1', 'null', '[]', '1e999', '"\\ud800"']))
    def test_garbage_argument_text_in_the_harness_is_no_submission(self, cid, raw):
        calls = []

        def transport(req):
            calls.append(1)
            msg = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'c', 'type': 'function', 'function': {
                'name': 'submit_award', 'arguments': raw}}]}
            return 200, {}, json.dumps({'choices': [{'message': msg, 'finish_reason': 'tool_calls'}],
                                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()
        rec = ev2.run_static_case(CASES[cid], 'test/mock-model:free', transport, sleep=lambda s: None)
        self.assertIn(rec['status'], ('no_usable_submission', 'submitted', 'tool_kind_mismatch'))
        self.assertLessEqual(len(calls), 2)
        grade = ev2.grade_static(CASES[cid], rec['submission'])
        self.assertFalse(grade.get('accepted', False))


if __name__ == '__main__':
    unittest.main()
