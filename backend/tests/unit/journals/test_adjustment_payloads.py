"""CLO-12 payload rules of a manual adjustment as pure functions (04 T-SL-05 ``payload``, §16.14
"API-R-37 shapes", §16.3; ENGINE_SPEC_B S09-R-38 to S09-R-41, S14-R-09a; BUILD_SPEC CLO-12).
CPU-only: ``adjustments.payload_errors``, ``unbalanced`` and ``stored_payload`` over a parsed
payload and the facts the command reads, and ``bundles.adjustment_members`` — what the engine reads
of a stored row. The commands around them are witnessed in
``tests/domain/journals/test_adjustments.py``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import erev_api.db
from erev_api.domain.contracts import bundles
from erev_api.domain.journals import adjustments
from erev_api.domain.journals.adjustments import AccountFacts
from erev_api.schemas.manual_adjustments import AdjustmentPayloadIn

ENTITY: Final = UUID("00000000-0000-4000-8000-00000000e001")
OTHER_ENTITY: Final = UUID("00000000-0000-4000-8000-00000000e002")
OBLIGATION: Final = UUID("00000000-0000-4000-8000-00000000b001")
STRANGER: Final = UUID("00000000-0000-4000-8000-00000000b009")
SEPTEMBER: Final = UUID("00000000-0000-4000-8000-00000000c009")
OCTOBER: Final = UUID("00000000-0000-4000-8000-00000000c010")
NO_PERIOD: Final = UUID("00000000-0000-4000-8000-00000000c099")
LIABILITY: Final = UUID("00000000-0000-4000-8000-00000000f001")
REVENUE: Final = UUID("00000000-0000-4000-8000-00000000f002")
NO_ACCOUNT: Final = UUID("00000000-0000-4000-8000-00000000f099")
ACCOUNTS: Final = {
    LIABILITY: AccountFacts("2100", True, frozenset(), frozenset()),
    REVENUE: AccountFacts("4010", True, frozenset(), frozenset()),
}


def _usd(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def _payload(**members: Any) -> AdjustmentPayloadIn:
    return AdjustmentPayloadIn.model_validate(members)


def _line(account: UUID, amount: str, role: str, **dimensions: str) -> dict[str, Any]:
    return {
        "account_role": role,
        "gl_account_id": str(account),
        "amount_txn": _usd(amount),
        "dimensions": dimensions,
    }


def _journal(*lines: dict[str, Any], **members: Any) -> AdjustmentPayloadIn:
    return _payload(lines=list(lines), **members)


BALANCED: Final = (
    _line(LIABILITY, "2400.00", "CONTRACT_LIABILITY"),
    _line(REVENUE, "-2400.00", "REVENUE"),
)


def _errors(
    kind: str,
    payload: AdjustmentPayloadIn,
    accounts: dict[UUID, AccountFacts] | None = None,
    *,
    functional_currency: str = "USD",
) -> list[tuple[str | None, str]]:
    found = adjustments.payload_errors(
        kind,
        payload,
        currency="USD",
        functional_currency=functional_currency,
        entity_id=ENTITY,
        entity_code="AVM-US",
        obligations={OBLIGATION: {"obligation_key": "O1"}},
        periods={SEPTEMBER: object(), OCTOBER: object()},
        accounts=ACCOUNTS if accounts is None else accounts,
    )
    return [(error.field, error.message) for error in found]


def test_a_release_names_one_obligation_and_one_basis() -> None:
    for kind in ("MANUAL_RELEASE", "MANUAL_DEFER"):
        assert _errors(kind, _payload(obligation_id=OBLIGATION, amount=_usd("2400.00"))) == []
        assert _errors(kind, _payload(obligation_id=OBLIGATION, ratio="0.25")) == []
        assert _errors(kind, _payload(obligation_id=OBLIGATION, ratio="1")) == []
        assert _errors(kind, _payload(obligation_id=OBLIGATION, remaining=True)) == []
    release = "MANUAL_RELEASE"
    assert _errors(release, _payload(obligation_id=OBLIGATION)) == [
        ("payload", "Send exactly one of amount, ratio and remaining.")
    ]
    both = _payload(obligation_id=OBLIGATION, amount=_usd("2400.00"), remaining=True)
    assert _errors(release, both) == [
        ("payload", "Send exactly one of amount, ratio and remaining.")
    ]
    assert _errors(release, _payload(amount=_usd("2400.00"))) == [
        ("payload.obligation_id", "Choose the obligation the adjustment applies to.")
    ]
    assert _errors(release, _payload(obligation_id=STRANGER, amount=_usd("2400.00"))) == [
        ("payload.obligation_id", "Choose an obligation of the contract.")
    ]
    for amount in ("0.00", "-2400.00"):
        assert _errors(release, _payload(obligation_id=OBLIGATION, amount=_usd(amount))) == [
            ("payload.amount", "Enter an amount greater than 0.")
        ]
    euro = _payload(obligation_id=OBLIGATION, amount=_usd("2400.00", "EUR"))
    assert _errors(release, euro) == [
        ("payload.amount", "Amounts are in the contract currency USD.")
    ]
    for ratio in ("0", "1.01", "-0.5"):
        assert _errors(release, _payload(obligation_id=OBLIGATION, ratio=ratio)) == [
            ("payload.ratio", "Enter a ratio greater than 0 and at most 1.")
        ]
    foreign = _payload(
        obligation_id=OBLIGATION,
        amount=_usd("2400.00"),
        periods=[{"period_id": str(SEPTEMBER), "amount": _usd("1.00")}],
        lines=list(BALANCED),
    )
    assert _errors(release, foreign) == [
        ("payload.periods", "periods does not apply to a MANUAL_RELEASE adjustment."),
        ("payload.lines", "lines does not apply to a MANUAL_RELEASE adjustment."),
    ]


def test_a_minor_unit_finding_carries_the_money_rule() -> None:
    payload = _payload(obligation_id=OBLIGATION, amount=_usd("2400.001"))
    (found,) = adjustments.payload_errors(
        "MANUAL_RELEASE",
        payload,
        currency="USD",
        functional_currency="USD",
        entity_id=ENTITY,
        entity_code="AVM-US",
        obligations={OBLIGATION: {}},
        periods={},
        accounts={},
    )
    assert (found.field, found.rule_id, found.message) == (
        "payload.amount",
        "API-C-06",
        "USD amounts have at most 2 decimal places.",
    )


def test_an_override_lists_each_period_once() -> None:
    kind = "SCHEDULE_OVERRIDE"

    def periods(*items: tuple[UUID, str]) -> list[dict[str, Any]]:
        return [
            {"period_id": str(period_id), "amount": _usd(amount)} for period_id, amount in items
        ]

    listed = periods((SEPTEMBER, "12164.38"), (OCTOBER, "0.00"))
    assert _errors(kind, _payload(obligation_id=OBLIGATION, periods=listed)) == []
    assert _errors(kind, _payload(obligation_id=OBLIGATION)) == [
        ("payload.periods", "List at least one period with its amount.")
    ]
    assert _errors(kind, _payload(obligation_id=OBLIGATION, periods=[])) == [
        ("payload.periods", "List at least one period with its amount.")
    ]
    wrong = periods((SEPTEMBER, "1.00"), (NO_PERIOD, "1.00"), (SEPTEMBER, "2.00"))
    assert _errors(kind, _payload(obligation_id=OBLIGATION, periods=wrong)) == [
        ("payload.periods.1.period_id", "Choose a period of the entity's calendar."),
        ("payload.periods.2.period_id", "A period is listed once."),
    ]
    mixed = _payload(obligation_id=OBLIGATION, periods=listed, ratio="0.5", remaining=True)
    assert _errors(kind, mixed) == [
        ("payload.ratio", "ratio does not apply to a SCHEDULE_OVERRIDE adjustment."),
        ("payload.remaining", "remaining does not apply to a SCHEDULE_OVERRIDE adjustment."),
    ]


def test_journal_lines_name_usable_roles_and_accounts() -> None:
    for kind in ("MANUAL_JOURNAL", "ACCOUNT_RECLASS"):
        assert _errors(kind, _journal(*BALANCED)) == []
        assert _errors(kind, _journal(*BALANCED, obligation_id=OBLIGATION)) == []
    kind = "MANUAL_JOURNAL"
    assert _errors(kind, _journal(BALANCED[0])) == [
        ("payload.lines", "A journal has at least two lines.")
    ]
    assert _errors(kind, _payload(obligation_id=OBLIGATION, amount=_usd("1.00"))) == [
        ("payload.amount", "amount does not apply to a MANUAL_JOURNAL adjustment."),
        ("payload.lines", "A journal has at least two lines."),
    ]
    zero = _journal(_line(LIABILITY, "0.00", "CONTRACT_LIABILITY"), BALANCED[1])
    assert _errors(kind, zero) == [
        ("payload.lines.0.amount_txn", "A line carries an amount other than 0.")
    ]
    for role in (
        "RETAINED_EARNINGS",
        "FINANCING_OBLIGATION",
        "ROUNDING",
        "BILLING_CLEARING",
        "INTERCOMPANY_DUE_TO",
        "INTERCOMPANY_DUE_FROM",
    ):
        refused = _journal(BALANCED[0], _line(REVENUE, "-2400.00", role))
        assert _errors(kind, refused) == [
            ("payload.lines.1.account_role", f"Role {role} cannot be used on a manual line.")
        ]
    unknown = _journal(BALANCED[0], _line(NO_ACCOUNT, "-2400.00", "REVENUE"))
    assert _errors(kind, unknown) == [
        ("payload.lines.1.gl_account_id", "Choose a GL account of this workspace.")
    ]
    elsewhere = {
        LIABILITY: AccountFacts("2100", False, frozenset(), frozenset()),
        REVENUE: AccountFacts("4010", True, frozenset({OTHER_ENTITY}), frozenset()),
    }
    assert _errors(kind, _journal(*BALANCED), elsewhere) == [
        ("payload.lines.0.gl_account_id", "Account 2100 is inactive."),
        ("payload.lines.1.gl_account_id", "Account 4010 does not apply to AVM-US."),
    ]
    here = {**ACCOUNTS, REVENUE: AccountFacts("4010", True, frozenset({ENTITY}), frozenset())}
    assert _errors(kind, _journal(*BALANCED), here) == []


def test_a_journal_needs_a_contract_in_the_functional_currency() -> None:
    """Accepted limit of 1.0 (ruling R-51; ENGINE_SPEC_B S14-R-09a): a manual journal or
    reclassification of a contract whose currency is not its entity's functional currency is
    refused by name — its lines state one amount and no rate reference. The schedule kinds are
    not limited: their amounts are the contract's, measured by the engine."""
    message = (
        "A manual journal or reclassification is available for contracts in the entity's "
        "functional currency (GBP); this contract is in USD."
    )
    for kind in ("MANUAL_JOURNAL", "ACCOUNT_RECLASS"):
        found = adjustments.payload_errors(
            kind,
            _journal(*BALANCED),
            currency="USD",
            functional_currency="GBP",
            entity_id=ENTITY,
            entity_code="AVM-UK",
            obligations={},
            periods={},
            accounts=ACCOUNTS,
        )
        assert [(error.field, error.rule_id, error.message) for error in found] == [
            ("kind", "S14-R-09a", message)
        ]
    release = _payload(obligation_id=OBLIGATION, amount=_usd("2400.00"))
    assert _errors("MANUAL_RELEASE", release, functional_currency="GBP") == []
    override = _payload(
        obligation_id=OBLIGATION, periods=[{"period_id": str(SEPTEMBER), "amount": _usd("1.00")}]
    )
    assert _errors("SCHEDULE_OVERRIDE", override, functional_currency="GBP") == []


def test_journal_line_dimensions() -> None:
    """The posting sets the identity dimensions (S14-R-13); a line sends the others, and an account
    that requires one is refused without it (REQ-JE-022)."""
    kind = "MANUAL_JOURNAL"
    reserved = _journal(
        BALANCED[0],
        _line(REVENUE, "-2400.00", "REVENUE", contract="G-1", obligation_key="O1", region="EMEA"),
    )
    assert _errors(kind, reserved) == [
        (
            "payload.lines.1.dimensions",
            "Dimension contract is set by the posting and cannot be sent.",
        ),
        (
            "payload.lines.1.dimensions",
            "Dimension obligation_key is set by the posting and cannot be sent.",
        ),
    ]
    needy = {
        **ACCOUNTS,
        REVENUE: AccountFacts(
            "4010", True, frozenset(), frozenset({"contract", "obligation_key", "region"})
        ),
    }
    # without an obligation the posting carries no obligation key, and the line sends no region
    assert _errors(kind, _journal(*BALANCED), needy) == [
        (
            "payload.lines.1.dimensions",
            "Account 4010 needs the dimension(s) obligation_key, region.",
        )
    ]
    assert _errors(kind, _journal(*BALANCED, obligation_id=OBLIGATION), needy) == [
        ("payload.lines.1.dimensions", "Account 4010 needs the dimension(s) region.")
    ]
    regional = _journal(
        BALANCED[0], _line(REVENUE, "-2400.00", "REVENUE", region="EMEA"), obligation_id=OBLIGATION
    )
    assert _errors(kind, regional, needy) == []


def test_every_finding_is_returned_together() -> None:
    lines = (
        _line(NO_ACCOUNT, "0.00", "ROUNDING"),
        {**_line(REVENUE, "-1.005", "REVENUE"), "amount_txn": _usd("-1.005", "EUR")},
    )
    assert _errors("ACCOUNT_RECLASS", _journal(*lines, obligation_id=STRANGER)) == [
        ("payload.obligation_id", "Choose an obligation of the contract."),
        ("payload.lines.0.amount_txn", "A line carries an amount other than 0."),
        ("payload.lines.0.account_role", "Role ROUNDING cannot be used on a manual line."),
        ("payload.lines.0.gl_account_id", "Choose a GL account of this workspace."),
        ("payload.lines.1.amount_txn", "Amounts are in the contract currency USD."),
    ]


def test_lines_that_do_not_balance_are_their_own_problem() -> None:
    off = _journal(BALANCED[0], _line(REVENUE, "-2399.99", "REVENUE"))
    refused = adjustments.unbalanced("MANUAL_JOURNAL", off, "USD")
    assert refused is not None
    assert (refused.slug, refused.status) == ("ledger-unbalanced", 422)
    assert refused.detail == (
        "The lines do not balance: debits 2400.00 and credits 2399.99 differ by 0.01 USD."
    )
    assert [(error.field, error.rule_id) for error in refused.errors] == [
        ("payload.lines", "T-SL-05")
    ]
    assert adjustments.unbalanced("ACCOUNT_RECLASS", _journal(*BALANCED), "USD") is None
    three = _journal(
        _line(LIABILITY, "2400.00", "CONTRACT_LIABILITY"),
        _line(REVENUE, "-2000.00", "REVENUE"),
        _line(REVENUE, "-400.00", "REVENUE"),
    )
    assert adjustments.unbalanced("MANUAL_JOURNAL", three, "USD") is None
    # a schedule kind carries no lines to balance
    release = _payload(obligation_id=OBLIGATION, amount=_usd("2400.00"))
    assert adjustments.unbalanced("MANUAL_RELEASE", release, "USD") is None


def test_the_stored_payload_holds_the_members_of_its_kind() -> None:
    release = _payload(obligation_id=OBLIGATION, amount=_usd("2400.00"))
    assert adjustments.stored_payload("MANUAL_RELEASE", release) == {
        "obligation_id": str(OBLIGATION),
        "amount": {"amount": "2400.00", "currency": "USD"},
    }
    assert adjustments.stored_payload(
        "MANUAL_DEFER", _payload(obligation_id=OBLIGATION, ratio="0.25")
    ) == {"obligation_id": str(OBLIGATION), "ratio": "0.25"}
    assert adjustments.stored_payload(
        "MANUAL_RELEASE", _payload(obligation_id=OBLIGATION, remaining=True)
    ) == {"obligation_id": str(OBLIGATION), "remaining": True}
    override = _payload(
        obligation_id=OBLIGATION,
        periods=[{"period_id": str(SEPTEMBER), "amount": _usd("12164.38")}],
    )
    assert adjustments.stored_payload("SCHEDULE_OVERRIDE", override) == {
        "obligation_id": str(OBLIGATION),
        "periods": [
            {"period_id": str(SEPTEMBER), "amount": {"amount": "12164.38", "currency": "USD"}}
        ],
    }
    journal = _journal(
        BALANCED[0], _line(REVENUE, "-2400.00", "REVENUE", region="EMEA", channel="DIRECT")
    )
    assert adjustments.stored_payload("MANUAL_JOURNAL", journal) == {
        "lines": [
            {
                "account_role": "CONTRACT_LIABILITY",
                "gl_account_id": str(LIABILITY),
                "amount_txn": {"amount": "2400.00", "currency": "USD"},
                "dimensions": {},
            },
            {
                "account_role": "REVENUE",
                "gl_account_id": str(REVENUE),
                "amount_txn": {"amount": "-2400.00", "currency": "USD"},
                "dimensions": {"channel": "DIRECT", "region": "EMEA"},
            },
        ]
    }


def _row(
    kind: str, payload: dict[str, Any], obligation_id: UUID | None = OBLIGATION
) -> dict[str, Any]:
    return {"kind": kind, "book_code": "ASC606", "obligation_id": obligation_id, "payload": payload}


def _members(row: dict[str, Any]) -> dict[str, Any]:
    return bundles.adjustment_members(
        row,
        entity_code="AVM-US",
        period_key="FY2026-P09",
        period_keys={str(SEPTEMBER): "FY2026-P09", str(OCTOBER): "FY2026-P10"},
        obligation_keys={OBLIGATION: "O1"},
    )


COMMON: Final = {
    "book_code": "ASC606",
    "entity_code": "AVM-US",
    "period_key": "FY2026-P09",
    "obligation_key": "O1",
}


def test_the_engine_reads_the_row_in_natural_keys() -> None:
    """04 §16.3 (rev 1.120): what the bundle builder adds to ``MANUAL_ADJUSTMENT_APPLIED`` — the
    kind, the book, the entity, the adjustment period, the obligation key and the kind's members
    with plain decimal amounts (ENGINE_SPEC §0.4), never an id."""
    release = _row("MANUAL_RELEASE", {"obligation_id": str(OBLIGATION), "amount": _usd("2400.00")})
    assert _members(release) == {"kind": "MANUAL_RELEASE", **COMMON, "amount": "2400.00"}
    defer = _row("MANUAL_DEFER", {"obligation_id": str(OBLIGATION), "ratio": "0.25"})
    assert _members(defer) == {"kind": "MANUAL_DEFER", **COMMON, "ratio": "0.25"}
    rest = _row("MANUAL_RELEASE", {"obligation_id": str(OBLIGATION), "remaining": True})
    assert _members(rest) == {"kind": "MANUAL_RELEASE", **COMMON, "remaining": True}
    override = _row(
        "SCHEDULE_OVERRIDE",
        {
            "obligation_id": str(OBLIGATION),
            "periods": [
                {"period_id": str(SEPTEMBER), "amount": _usd("12164.38")},
                {"period_id": str(NO_PERIOD), "amount": _usd("1.00")},
            ],
        },
    )
    assert _members(override) == {
        "kind": "SCHEDULE_OVERRIDE",
        **COMMON,
        "periods": [
            {"period_key": "FY2026-P09", "amount": "12164.38"},
            # a period the calendar does not hold stays unnamed: the engine refuses it by name
            {"period_key": None, "amount": "1.00"},
        ],
    }
    stored_lines = adjustments.stored_payload("MANUAL_JOURNAL", _journal(*BALANCED))
    journal = _row("MANUAL_JOURNAL", stored_lines)
    assert _members(journal) == {
        "kind": "MANUAL_JOURNAL",
        **COMMON,
        "lines": [
            {"account_role": "CONTRACT_LIABILITY", "amount_txn": "2400.00"},
            {"account_role": "REVENUE", "amount_txn": "-2400.00"},
        ],
    }
    # lines of the contract: no obligation key, so stage 14 takes the contract's subject
    contract_level = _members(_row("ACCOUNT_RECLASS", stored_lines, obligation_id=None))
    assert "obligation_key" not in contract_level and contract_level["kind"] == "ACCOUNT_RECLASS"
    unknown = _members(_row("MANUAL_JOURNAL", stored_lines, obligation_id=STRANGER))
    assert "obligation_key" not in unknown


def test_the_preview_job_names_a_t_plt_27_subject() -> None:
    """04 T-PLT-27 ``ck_job__subject_type`` admits a fixed list — revision 0012, then the literals
    later revisions add. The preview job works on the adjustment's ``contract``;
    ``manual_adjustment`` is not a job subject type, and a job deferred with it is refused by the
    database (the 500 of ``POST /manual-adjustments/{id}/preview`` on lane head f185c026)."""
    versions = Path(erev_api.db.__file__).parent / "migrations" / "versions"
    admitted: set[str] = set()
    for path in sorted(versions.glob("*.py")):
        if "ck_job__subject_type" not in path.read_text(encoding="utf-8"):
            continue
        spec = importlib.util.spec_from_file_location(f"clo12_{path.stem}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        admitted.update(module.SUBJECT_TYPES)
    assert {"contract", "journal_run"} <= admitted
    assert adjustments.PREVIEW_JOB_SUBJECT in admitted
    assert adjustments.OBJECT not in admitted
