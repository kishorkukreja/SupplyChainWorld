#!/usr/bin/env python3
"""Sanitized independent batch-two regressions; never prints generated records."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tests'))
suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_batch2_integration.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('Independent integration review: boundary, split, checker and tamper regressions only.')
print('No generated world, private expected answer or trajectory contents are printed.')
raise SystemExit(0 if result.wasSuccessful() else 1)
