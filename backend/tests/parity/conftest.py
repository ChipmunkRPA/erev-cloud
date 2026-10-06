"""The G3 parity world shared by the parity modules (docs/dev-guide.md §9.6 DG-PAR-04; BUILD_SPEC
GPA-1; D-87 L6-2-Q-6).

``parity_scenario`` builds the DG-PAR-04 world once per session, so the golden cases of
``test_golden_parity`` and the GPA-4 figures of ``test_gpa4_unasserted_figures`` read the same
committed replay.
"""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.config import get_settings
from support.db import TestDatabase
from support.parity import scenario
from support.parity.scenario import ParityScenario


@pytest.fixture(scope="session")
def parity_scenario(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> ParityScenario:
    """The DG-PAR-04 world, committed to the migrated test database once per session."""
    del test_database  # the session's migrated database, which the scenario commits to
    root = tmp_path_factory.mktemp("parity-files")
    return scenario.build(get_settings().model_copy(update={"file_root": root}), keyring)
