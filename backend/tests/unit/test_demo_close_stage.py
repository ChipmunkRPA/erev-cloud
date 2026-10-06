"""The close stage of the demo seed, the parts that need no database (BUILD_SPEC CLO-22; PRD §2.2
WLD-P-02, WLD-P-04; dev-guide DG-MK-seed; supervisor ruling of 2026-10-01 on lane F-ADM-WEB's
design line). The stage itself is witnessed on a seeded world in
``tests/domain/demo/test_close_history_seed.py``.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from erev_api import cli
from erev_api.domain.demo import builders, close_history, closing, seed, tenants
from erev_api.domain.demo.avenmoor import background as avenmoor_background
from erev_api.domain.demo.avenmoor import imports as avenmoor_imports
from erev_api.domain.demo.builders import BuildContext
from erev_api.domain.demo.personas import PERSONAS
from erev_api.enums import BookCode


def test_the_stage_stands_after_the_contracts_and_before_the_imports() -> None:
    """WLD-P-04: the close comes after every contract of the closed months and before the items
    that would hold its locks. Only WLD-T-01 has the stage."""
    registered = builders.BUILDERS["WLD-T-01"]
    at = registered.index(close_history.build)
    assert registered.index(avenmoor_background.build) == at - 1
    assert registered.index(avenmoor_imports.build) == at + 1
    assert [tenant.wld_id for tenant in tenants.CATALOGUE if seed.has_close_stage(tenant)] == [
        "WLD-T-01"
    ]


def test_the_stage_closes_avm_us_january_to_august_in_the_primary_book() -> None:
    """WLD-P-02 as built: one entity-book, eight months, earliest first; ``demo_seed.complete``
    says so."""
    assert close_history.CLOSED == (("AVM-US", BookCode.ASC606),)
    assert close_history.PERIOD_KEYS == tuple(f"FY2026-P0{month}" for month in range(1, 9))
    assert close_history.closed_scopes() == [
        {
            "entity_code": "AVM-US",
            "book": "ASC606",
            "from_period_key": "FY2026-P01",
            "to_period_key": "FY2026-P08",
        }
    ]
    assert (close_history.CAST.preparer, close_history.CAST.reviewer) == ("maya", "priya")
    assert close_history.CAST.controller == "marcus"


def test_the_stage_does_nothing_for_a_seed_that_did_not_ask() -> None:
    """The default seed: the builder returns before it reads or writes anything."""

    class Unasked:
        with_close = False

        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"the unasked stage touched ctx.{name}")

    close_history.build(cast(BuildContext, Unasked()))


def test_the_asked_stage_closes_its_months_in_order_and_then_makes_the_open_period_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WLD-P-04 and BR-CLS-08: the months earliest first, and the open-period items only after
    the last lock — each of them holds every lock made after it."""
    calls: list[str] = []

    def close_period(
        ctx: object, acting: object, *, entity_code: str, book: BookCode, period_key: str
    ) -> None:
        assert acting is close_history.CAST
        calls.append(f"{entity_code} {book.value} {period_key}")

    monkeypatch.setattr(closing, "close_period", close_period)
    monkeypatch.setattr(
        avenmoor_background, "open_period_items", lambda ctx: calls.append("open-period items")
    )
    close_history.build(cast(BuildContext, SimpleNamespace(with_close=True)))
    assert calls == [
        *(f"AVM-US ASC606 FY2026-P0{month}" for month in range(1, 9)),
        "open-period items",
    ]


def test_a_tenant_seeded_without_its_close_is_refused_the_stage() -> None:
    """DG-MK-seed: the earlier refusals come first; then a tenant this version seeded without
    its close is refused the stage by name, and one seeded with it is skipped as always."""
    entry = seed._DirectoryEntry  # noqa: SLF001
    version = seed.GENERATOR_VERSION
    plain = entry(tenant_id=uuid4(), is_demo=True, generator_version=version)
    closed = entry(tenant_id=uuid4(), is_demo=True, generator_version=version, with_close=True)
    assert seed._refusal("avenmoor", None, close_asked=True) is None  # noqa: SLF001
    assert seed._refusal("avenmoor", plain) is None  # noqa: SLF001
    assert seed._refusal("avenmoor", closed) is None  # noqa: SLF001
    assert seed._refusal("avenmoor", closed, close_asked=True) is None  # noqa: SLF001
    assert seed._refusal("avenmoor", plain, close_asked=True) == (  # noqa: SLF001
        "Refusing to close avenmoor: it is seeded without its close, and its open items hold "
        "every lock; run make seed RESET=1 CLOSE=1"
    )
    foreign = entry(tenant_id=uuid4(), is_demo=False, generator_version=version)
    assert seed._refusal("avenmoor", foreign, close_asked=True) == (  # noqa: SLF001
        "Refusing to seed avenmoor: is_demo is false"
    )
    unfinished = entry(tenant_id=uuid4(), is_demo=True, generator_version=None)
    assert "an earlier run did not finish" in str(
        seed._refusal("avenmoor", unfinished, close_asked=True)  # noqa: SLF001
    )
    older = entry(tenant_id=uuid4(), is_demo=True, generator_version=version - 1)
    assert f"generator version {version - 1} built it" in str(
        seed._refusal("avenmoor", older, close_asked=True)  # noqa: SLF001
    )


def test_a_persona_steps_up_through_the_run_that_holds_her_session() -> None:
    """``BuildContext.step_up`` hands the persona to the seed's sessions; a caller that wired
    none — a clock that stands still — asks for nothing."""
    maya = PERSONAS[0]
    asked: list[str] = []
    services = SimpleNamespace()

    def context(verify_again: Any) -> BuildContext:
        return BuildContext(
            tenant_id=uuid4(),
            tenant_code="avenmoor",
            wld_id="WLD-T-01",
            cast={maya.key: maya},
            clock=cast(Any, services),
            keyring=cast(Any, services),
            files=cast(Any, services),
            request_id="tests",
            principal_context=cast(Any, services),
            guard=cast(Any, services),
            verify_again=verify_again,
        )

    unwired = context(None)
    assert unwired.with_close is False
    unwired.step_up("maya")
    context(lambda persona: asked.append(persona.email)).step_up("maya")
    assert asked == [maya.email]


def test_a_trial_balance_file_states_one_row_per_account_in_the_currency_s_decimals() -> None:
    """BUILD_SPEC CLO-17's upload: ``account,currency,amount``, accounts in order, a credit
    negative, an account without a line at zero."""
    content = closing.trial_balance_csv(
        {"4000": Decimal("-96000"), "1300": Decimal("0"), "2100": Decimal("1250.5")}, "USD"
    )
    assert content.decode("utf-8").splitlines() == [
        "account,currency,amount",
        "1300,USD,0.00",
        "2100,USD,1250.50",
        "4000,USD,-96000.00",
    ]
    assert closing.trial_balance_csv({"2100": Decimal("-1200")}, "JPY").decode().splitlines()[
        1
    ] == ("2100,JPY,-1200")


def test_a_csv_batch_is_acknowledged_with_a_reference_of_its_entity_period_and_number() -> None:
    assert closing.document_reference("AVM-US", "FY2026-P01", 1, 1) == "GL-AVM-US-FY2026-P01-01-01"
    assert closing.document_reference("VOL-UK", "FY2025-P12", 2, 13) == "GL-VOL-UK-FY2025-P12-02-13"


def test_a_draft_journal_run_without_a_line_is_left_as_the_close_run_calculated_it() -> None:
    """A period without activity has a journal run without a line — the lock asks a run of the
    period that is not cancelled — and there is nothing in it to approve or export: the helper
    leaves it ``draft`` and goes on to the lock. Item JRN-EMPTY-RUN-1 refuses the submission of
    such a run (409), which would stop a seed that sent it. A run with lines, and a run a person
    moved on before, go the whole way. The helper asks before it submits."""
    assert closing.stands_as_calculated("draft", 0)
    assert not closing.stands_as_calculated("draft", 1)
    assert not closing.stands_as_calculated("approved", 0)
    assert not closing.stands_as_calculated("exported", 0)
    source = inspect.getsource(closing._journal)  # noqa: SLF001
    assert source.index("if stands_as_calculated(state, lines):") < source.index("submit_run(")


def test_the_seed_command_takes_the_flag_and_is_off_by_default() -> None:
    """``erev seed demo --with-close`` and ``seed_demo(with_close=...)``: both default to a seed
    without the close."""
    option = inspect.signature(cli.seed_demo_command).parameters["with_close"].default
    assert option.default is False and option.param_decls == ("--with-close",)
    assert inspect.signature(seed.seed_demo).parameters["with_close"].default is False
