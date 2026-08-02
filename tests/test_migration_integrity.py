"""
tests/test_migration_integrity.py — Ensure all migration scripts are registered in check_migrations.py
"""

from pathlib import Path
from scripts.check_migrations import _PROBES, _verify_unprobed_files


def test_all_migrations_have_probes():
    """Verify every .sql migration in db/migrations/ has a probe in check_migrations.py."""
    unprobed = _verify_unprobed_files()
    assert not unprobed, (
        f"Migration file(s) missing from scripts/check_migrations.py _PROBES: {unprobed}. "
        f"Please add probe definitions for them."
    )


def test_probes_list_not_empty():
    """Ensure _PROBES contains registered migration probes."""
    assert len(_PROBES) >= 40
