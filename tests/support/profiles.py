"""Hypothesis profiles.

ci   : reproducible. derandomize=True means the same examples every run, so a CI
       failure can always be reproduced locally with the same command.
dev  : random exploration with more examples; failures are kept in the local
       example database and replayed first on the next run.

Hypothesis refuses derandomize=True together with a database (a fixed example
stream needs no saved examples), so `ci` has no database. `dev` stores examples
under .hypothesis/examples, which is gitignored.

Select with SCW_HYPOTHESIS_PROFILE=dev. The default is `ci`, so a plain
`python -m unittest discover -s tests` is deterministic.
"""
import os
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis.database import DirectoryBasedExampleDatabase

ROOT = Path(__file__).resolve().parents[2]
# Gitignored (see .gitignore). Never commit this directory.
DATABASE_DIR = ROOT / '.hypothesis' / 'examples'

_database = DirectoryBasedExampleDatabase(str(DATABASE_DIR))

settings.register_profile(
    'ci', max_examples=100, derandomize=True, deadline=None, database=None,
    print_blob=True, suppress_health_check=[HealthCheck.too_slow])
settings.register_profile(
    'dev', max_examples=500, derandomize=False, deadline=None, database=_database,
    print_blob=True, suppress_health_check=[HealthCheck.too_slow])

ACTIVE = os.environ.get('SCW_HYPOTHESIS_PROFILE', 'ci')
settings.load_profile(ACTIVE)
