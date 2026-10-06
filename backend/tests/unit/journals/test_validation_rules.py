"""CLO-10 journal line validation as pure rules (REQ-JE-022; BUILD_SPEC CLO-10). CPU-only:
``validation.line_findings`` over detail lines and account facts — the database wrapper
``validate_lines`` loads the facts and names the contract and obligation."""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

from erev_api.domain.journals import validation
from erev_api.domain.journals.summarise import DetailLine

ENTITY: Final = UUID("00000000-0000-4000-8000-00000000e001")
OTHER_ENTITY: Final = UUID("00000000-0000-4000-8000-00000000e002")
ACCOUNT: Final = UUID("00000000-0000-4000-8000-00000000f001")
CONTRACT: Final = UUID("00000000-0000-4000-8000-00000000d001")
OBLIGATION: Final = UUID("00000000-0000-4000-8000-00000000b001")
RATE: Final = UUID("00000000-0000-4000-8000-000000000f0f")


def _line(
    *,
    role: str = "UNBILLED_RECEIVABLE",
    currency: str = "USD",
    fx_rate_id: UUID | None = None,
    dimensions: dict[str, str] | None = None,
) -> DetailLine:
    return DetailLine(
        id=UUID(int=1),
        book_code="ASC606",
        sign=1,
        chain_seq=3,
        posting_kind="ENGINE_COMPUTE",
        entry_kind="REVENUE_RECOGNITION",
        account_role=role,
        gl_account_id=ACCOUNT,
        gl_account_code="1201",
        dimensions=dimensions or {},
        txn_currency=currency,
        amount_txn=Decimal("100.00"),
        functional_currency="USD",
        amount_functional=Decimal("100.00"),
        contract_id=CONTRACT,
        obligation_id=OBLIGATION,
        fx_rate_id=fx_rate_id,
    )


def _account(
    *, active: bool = True, entities: frozenset[UUID] = frozenset(), required: tuple[str, ...] = ()
) -> validation.AccountFacts:
    return validation.AccountFacts(
        id=ACCOUNT,
        code="1201",
        is_active=active,
        entity_ids=entities,
        required_dimensions=frozenset(required),
    )


def _findings(
    line: DetailLine, account: validation.AccountFacts | None
) -> list[validation.LineFinding]:
    accounts = {} if account is None else {ACCOUNT: account}
    return validation.line_findings([line], accounts, entity_id=ENTITY, functional_currency="USD")


def test_a_valid_line_has_no_findings() -> None:
    assert _findings(_line(), _account()) == []
    assert _findings(_line(currency="EUR", fx_rate_id=RATE), _account()) == []
    assert (
        _findings(_line(dimensions={"department": "D1"}), _account(required=("department",))) == []
    )


def test_an_inactive_or_absent_account_is_an_unmapped_role() -> None:
    for account in (None, _account(active=False)):
        (finding,) = _findings(_line(), account)
        assert (finding.code, finding.problem) == (
            validation.ACCOUNT_MAPPING_MISSING,
            "unmapped-account-role",
        )
        assert (finding.account_role, finding.contract_id, finding.obligation_id) == (
            "UNBILLED_RECEIVABLE",
            CONTRACT,
            OBLIGATION,
        )
        assert "UNBILLED_RECEIVABLE" in finding.message


def test_an_account_of_other_entities_only_is_an_unmapped_role_for_this_entity() -> None:
    (finding,) = _findings(_line(), _account(entities=frozenset({OTHER_ENTITY})))
    assert finding.code == validation.ACCOUNT_MAPPING_MISSING
    assert "entity" in finding.message


def test_a_missing_required_dimension_names_contract_obligation_role_and_dimension() -> None:
    (finding,) = _findings(_line(), _account(required=("department", "region")))
    assert finding.code == validation.DIMENSION_MISSING_CODE
    assert finding.problem == "unmapped-account-role"
    assert finding.missing_dimensions == ("department", "region")
    assert (finding.contract_id, finding.obligation_id, finding.account_role) == (
        CONTRACT,
        OBLIGATION,
        "UNBILLED_RECEIVABLE",
    )
    assert "department" in finding.message and "region" in finding.message


def test_a_foreign_currency_line_without_a_rate_is_a_missing_fx_rate() -> None:
    """Defensive branch (Codex 1054 R4): ``ck_subledger_line__fx`` keeps an id-less foreign-currency
    line out of the ledger, so this is a validation boundary, not the database acceptance path."""
    (finding,) = _findings(_line(currency="EUR"), _account())
    assert (finding.code, finding.problem) == (validation.FX_RATE_MISSING, "missing-fx-rate")
    assert "EUR" in finding.message and "USD" in finding.message


def _rate(base: str = "EUR", quote: str = "USD", status: str = "APPROVED") -> validation.RateFacts:
    return validation.RateFacts(
        id=RATE, base_currency=base, quote_currency=quote, version_status=status
    )


def _rated(
    line: DetailLine, rates: dict[UUID, validation.RateFacts]
) -> list[validation.LineFinding]:
    return validation.line_findings(
        [line], {ACCOUNT: _account()}, entity_id=ENTITY, functional_currency="USD", rates=rates
    )


def test_a_named_rate_that_converts_the_line_and_is_in_force_passes() -> None:
    line = _line(currency="EUR", fx_rate_id=RATE)
    assert _rated(line, {RATE: _rate()}) == []
    assert _rated(line, {RATE: _rate(status="SUPERSEDED")}) == []


def test_a_named_rate_that_does_not_convert_the_line_is_a_missing_fx_rate() -> None:
    """The admitted boundary (1054 R4): the line carries both rate ids, so the ledger admits it, but
    the rate is GBP->USD while the line is in EUR — no rate from EUR to USD backs the line."""
    (finding,) = _rated(_line(currency="EUR", fx_rate_id=RATE), {RATE: _rate(base="GBP")})
    assert (finding.code, finding.problem) == (validation.FX_RATE_MISSING, "missing-fx-rate")
    assert "GBP->USD" in finding.message and "EUR" in finding.message


def test_a_named_rate_of_a_version_not_in_force_is_a_missing_fx_rate() -> None:
    for status in ("DRAFT", "TESTED", "SUBMITTED", "WITHDRAWN"):
        (finding,) = _rated(_line(currency="EUR", fx_rate_id=RATE), {RATE: _rate(status=status)})
        assert finding.code == validation.FX_RATE_MISSING and status in finding.message


def test_a_named_rate_this_workspace_does_not_hold_is_a_missing_fx_rate() -> None:
    (finding,) = _rated(_line(currency="EUR", fx_rate_id=RATE), {})
    assert finding.code == validation.FX_RATE_MISSING and str(RATE) in finding.message


def test_a_functional_currency_line_names_no_rate_and_needs_none() -> None:
    assert _rated(_line(currency="USD"), {}) == []


def test_every_line_is_reported_and_none_is_dropped() -> None:
    """REQ-JE-022: findings name every failing line; a valid line beside them is untouched."""
    lines = [_line(), _line(currency="EUR"), _line(role="REVENUE")]
    accounts = {ACCOUNT: _account(active=False)}
    findings = validation.line_findings(
        lines, accounts, entity_id=ENTITY, functional_currency="USD"
    )
    assert len(findings) == 4  # inactive account × 3 lines + the missing rate
    assert validation.problem_of(findings).slug == "unmapped-account-role"
    rate_findings = [item for item in findings if item.code == validation.FX_RATE_MISSING]
    assert len(rate_findings) == 1 and rate_findings[0].line_id == lines[1].id
    assert validation.problem_of(rate_findings).slug == "missing-fx-rate"
