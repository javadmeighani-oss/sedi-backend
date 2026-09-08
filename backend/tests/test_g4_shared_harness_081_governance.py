"""G4 shared PG16 harness 081 alignment — governance closure.

GATE=SEDI-V1-BE-FINALCERT-G4-SHARED-PG16-HARNESS-081-ALIGNMENT-IMPACT-VALIDATION-AND-GOVERNANCE-CLOSURE-01

POLICY=KEEP_081_SHARED_DEFAULT
Basis: i10_pg_db_module docstring = Alembic-head; ALEMBIC_HEAD=_REV_081;
historical callers use explicit revision=; G4 create uses revision=ALEMBIC_HEAD.
"""

from __future__ import annotations

import pytest
from alembic import command

from backend.tests.helpers.i10_postgresql_harness import (
    ALEMBIC_HEAD,
    I10IsolatedPgDb,
    _REV_073,
    _REV_074,
    _REV_080,
    _REV_081,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]


def test_harness_default_create_targets_alembic_head_081():
    isolated = I10IsolatedPgDb.create(suffix="govdef")
    try:
        assert ALEMBIC_HEAD == _REV_081
        assert isolated.head() == ALEMBIC_HEAD
        assert isolated.head() == "081_self_health_subject_1to1_hardening"
    finally:
        isolated.close()


def test_explicit_revision_override_preserved_080():
    isolated = I10IsolatedPgDb.create(suffix="gov080", revision=_REV_080)
    try:
        assert isolated.head() == _REV_080
        assert isolated.head() != ALEMBIC_HEAD
    finally:
        isolated.close()


def test_explicit_historical_migration_cycle_073_to_074():
    """Historical I10 B04 pattern — must not silently rebase to 081."""
    isolated = I10IsolatedPgDb.create(suffix="govmig074", revision=_REV_073)
    try:
        assert isolated.head() == _REV_073
        command.upgrade(isolated.cfg, _REV_074)
        assert isolated.head() == _REV_074
        command.downgrade(isolated.cfg, _REV_073)
        assert isolated.head() == _REV_073
        command.upgrade(isolated.cfg, _REV_074)
        assert isolated.head() == _REV_074
        assert isolated.head() != ALEMBIC_HEAD
    finally:
        isolated.close()


def test_i10_pg_db_module_is_alembic_head(i10_pg_db_module):
    _, isolated = i10_pg_db_module
    assert isolated.head() == ALEMBIC_HEAD


def test_g4_scenario_create_explicitly_pins_081():
    """G4 081 proof preserved without full suite rerun."""
    isolated = I10IsolatedPgDb.create(suffix="govg4", revision=ALEMBIC_HEAD)
    try:
        assert isolated.head() == _REV_081
    finally:
        isolated.close()
