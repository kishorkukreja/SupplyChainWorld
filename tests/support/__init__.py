"""Shared test infrastructure. See docs/testing.md.

Importing this package registers and loads the Hypothesis profile, so a test
module only needs `import support` (or any `from support... import ...`).
"""
from . import profiles  # noqa: F401  (side effect: registers and loads the profile)
