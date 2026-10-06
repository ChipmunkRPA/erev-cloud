"""The definitions whose columns are period keys, read from the builders (04 T-RPT-01 rule 6 rev
1.264; PRD ERR-97; item RPT-PERIOD-KEY-CALENDARS-1; the supervisor's ruling of 2026-10-02). No
database.

A builder that states its figures in one column per period key names those columns with its
``PERIOD_PREFIX``. Over entities of more than one fiscal calendar such a report sets one month
into a column per calendar — measured: the disaggregation of September 2026 over a January-year
and an April-year entity came as ``period:FY2026-P09`` and ``period:FY2027-P06``, both headed
"Sep 2026" — so ``reports.framework`` refuses its run over them whether or not a key is named
(``PERIOD_KEY_COLUMNS``). The set is read from the builders: a definition registered with period
columns is in it, and so is asked by the database witness
(``tests/domain/reports/test_period_key_calendars_db.py``).
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path
from types import ModuleType

from erev_api.domain.reports import builders, framework

# A column key that begins with the period prefix, spelled as a literal.
PERIOD_LITERAL = re.compile(r"""["']period:""")


def _builder_modules() -> list[ModuleType]:
    return [
        importlib.import_module(f"{builders.__name__}.{found.name}")
        for found in pkgutil.iter_modules(builders.__path__)
    ]


def test_the_set_is_the_registered_builders_that_declare_a_period_prefix() -> None:
    """``PERIOD_KEY_COLUMNS`` is every registered definition whose builder declares
    ``PERIOD_PREFIX`` — today the waterfall and the disaggregation — and each declares the one
    prefix, so that a column of one is a column of the other to every reader."""
    declaring = [module for module in _builder_modules() if hasattr(module, "PERIOD_PREFIX")]
    assert {module.PERIOD_PREFIX for module in declaring} == {"period:"}
    registered = {module.CODE for module in declaring} & set(framework.BUILDERS)
    assert framework.PERIOD_KEY_COLUMNS == registered
    assert {"revenue_waterfall", "disaggregation"} <= framework.PERIOD_KEY_COLUMNS


def test_no_builder_names_a_period_column_without_declaring_the_prefix() -> None:
    """A builder that spelled the prefix as a literal would have period columns and stay outside
    the set. The literal stands once in a module, as the value of its ``PERIOD_PREFIX``."""
    for module in _builder_modules():
        assert module.__file__ is not None
        literals = PERIOD_LITERAL.findall(Path(module.__file__).read_text(encoding="utf-8"))
        assert len(literals) == (1 if hasattr(module, "PERIOD_PREFIX") else 0), module.__name__
