"""What a close run read beside its contracts, without a database (item CLO-RATE-AFTER-RUN-1; the
supervisor's ruling of 2026-10-02 08:56; 04 T-CLS-01 "What a run read" rev 1.291): the two reads
of ``close.run_inputs`` as statements and as rules. The database witnesses are
``tests/domain/close/test_close_run_inputs.py``.

- ONE admission of a rate, two callers: a bundle's rates and the digest of what a run could read
  are the same statement, narrowed differently.
- The digest of the rates is by value — set, rate type, pair, date, rate — never by version.
- The period-pinned parameters are DERIVED from the catalogue's pin, and the value read for a
  run is the one a bundle hands to the run's period: the same versions, the same instant — the
  earlier of the cutoff and the period's last instant in the entity's zone — the same resolver
  (third row of rev 1.291, with item PINP-PERIOD-VALUE-1).
- ``read`` costs a caller under the tenant's scope five statements: the scope, the transaction
  timestamp, the rates, the registry's versions, the legal entities.
- ``standing``, the gate's read, takes the rates whenever their version was published.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import fx_rate
from erev_api.domain.close import run_inputs
from erev_api.domain.close.gates import PeriodScope
from erev_api.domain.contracts import bundles
from erev_api.domain.policies.templates import engine_policy_value
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine.bundle import EntityInput, PeriodInput
from sqlalchemy.dialects import postgresql

CUTOFF = datetime(2026, 9, 3, 14, 0, tzinfo=UTC)
AUGUST_END = date(2026, 8, 31)
ENTITY, OTHER = UUID(int=1), UUID(int=2)
SCOPE = PeriodScope(
    state_id=UUID(int=10),
    entity_id=ENTITY,
    entity_code="AVM-US",
    functional_currency="USD",
    book_code="ASC606",
    period_id=UUID(int=11),
    period_key="FY2026-P08",
    period_name="Aug 2026",
    start_date=date(2026, 8, 1),
    end_date=AUGUST_END,
    state="closing",
    current_lock_id=None,
    row_version=1,
)
# The digest statement as PostgreSQL receives it, up to its FROM: ``{row}`` is one admitted row
# as text, and ``{order}`` the same expression — the rows are listed in the order of their text.
DIGEST_HEAD = (
    "SELECT encode(sha256(convert_to(coalesce(string_agg({row}, %(param_1)s ORDER BY {order}),"
    " %(coalesce_1)s), %(convert_to_1)s)), %(encode_2)s) AS encode_1 FROM ("
)


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


# --- the rates ------------------------------------------------------------------------------------


def test_one_admission_of_a_rate_serves_the_bundle_and_the_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor's condition: the digest reads its rows through the function the bundle
    reads them through. Both call ``bundles.fx_rates_in_force`` with their cutoff, and each adds
    only its own narrowing: the bundle its currencies, the digest the period's last day."""
    calls: list[datetime] = []
    admission = bundles.fx_rates_in_force

    def spied(known_at: datetime) -> Any:
        calls.append(known_at)
        return admission(known_at)

    monkeypatch.setattr(bundles, "fx_rates_in_force", spied)

    class _Session:
        def __init__(self) -> None:
            self.statements: list[Any] = []

        def execute(self, statement: Any) -> Any:
            self.statements.append(statement)
            return iter(())

    session = _Session()
    assert bundles._fx_rate_rows(session, ["USD", "EUR"], CUTOFF) == ()  # type: ignore[arg-type]
    digest = run_inputs.rates_statement(CUTOFF, AUGUST_END)
    assert calls == [CUTOFF, CUTOFF]

    admitted = _sql(admission(CUTOFF))
    (bundle_read,) = session.statements
    assert _sql(bundle_read) == admitted + (
        " AND erev.fx_rate.base_currency IN (__[POSTCOMPILE_base_currency_1])"
        " AND erev.fx_rate.quote_currency IN (__[POSTCOMPILE_quote_currency_1])"
    )
    narrowed = _sql(admission(CUTOFF).where(fx_rate.c.effective_date <= AUGUST_END))
    assert narrowed == admitted + " AND erev.fx_rate.effective_date <= %(effective_date_1)s"
    # inside the digest the same statement stands as a subquery: its columns take labels, and
    # its joins, its admission and the narrowing are the bundle's statement word for word
    inner = _sql(digest).split(" FROM (", 1)[1].removesuffix(") AS admitted")
    assert inner.split(" FROM ", 1)[1] == narrowed.split(" FROM ", 1)[1]


def test_the_admission_of_a_rate_is_what_it_was() -> None:
    """D-87 L6-5-Q-23, unchanged by the item: a version APPROVED or SUPERSEDED, published by the
    cutoff, whose coverage holds the rate's date and that no higher such version of its set
    covers."""
    admitted = _sql(bundles.fx_rates_in_force(CUTOFF))
    where = admitted.split(" WHERE ", 1)[1]
    assert where == (
        "erev.fx_rate_set_version.status IN (__[POSTCOMPILE_status_1])"
        " AND erev.fx_rate_set_version.published_at <= %(published_at_1)s"
        " AND erev.fx_rate_set_version.coverage_from <= erev.fx_rate.effective_date"
        " AND erev.fx_rate_set_version.coverage_to >= erev.fx_rate.effective_date"
        " AND NOT (EXISTS (SELECT * FROM erev.fx_rate_set_version AS later_version"
        " WHERE later_version.tenant_id = erev.fx_rate_set_version.tenant_id"
        " AND later_version.fx_rate_set_id = erev.fx_rate_set_version.fx_rate_set_id"
        " AND later_version.status IN (__[POSTCOMPILE_status_2])"
        " AND later_version.published_at <= %(published_at_2)s"
        " AND later_version.version_no > erev.fx_rate_set_version.version_no"
        " AND later_version.coverage_from <= erev.fx_rate.effective_date"
        " AND later_version.coverage_to >= erev.fx_rate.effective_date))"
    )


def test_the_digest_of_the_rates_is_by_value_and_never_by_version() -> None:
    """One statement: the SHA-256 of the admitted rows, each as set code, rate type, base, quote,
    date and rate, in the order of that text. Neither the version's id nor its number is part
    of a row: a version that repeats the rates leaves the digest as it was."""
    digest = _sql(run_inputs.rates_statement(CUTOFF, AUGUST_END))
    row = (
        "concat_ws(%(concat_ws_1)s, admitted.code, CAST(admitted.rate_type AS TEXT),"
        " trim(admitted.base_currency), trim(admitted.quote_currency),"
        " CAST(admitted.effective_date AS TEXT), CAST(admitted.rate AS TEXT))"
    )
    head = DIGEST_HEAD.format(row=row, order=row)
    assert digest.startswith(head), digest[: len(head) + 40]
    assert "version" not in digest.split(" FROM (", 1)[0]


# --- the registry ---------------------------------------------------------------------------------


def test_the_period_pinned_parameters_are_derived_from_the_catalogues_pin() -> None:
    """Never written out: a parameter joins by being declared with pin ``P``. They are the
    parameters a bundle hands to each period, per entity (``contracts.bundles._period_rows``)."""
    assert registry.PERIOD_PINNED == tuple(
        code for code, spec in sorted(POLICY_PARAMETERS.items()) if spec.pin == "P"
    )
    assert registry.PERIOD_PINNED and set(registry.PERIOD_PINNED) < set(POLICY_PARAMETERS)


ATTRIBUTION = "position.reclass_attribution_key"  # POL-121: the TENANT level alone
ZONE = "America/New_York"
# A second version of the category takes effect AFTER August's last instant in New York
# (1 Sep 2026 03:59:59.999999 UTC) and BEFORE the cutoff of 3 Sep 2026 14:00 UTC.
TOOK_EFFECT = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _version(values: dict[str, Any], **named: Any) -> dict[str, Any]:
    """One row of ``registry.known_versions``: a TENANT version of the accounting policies."""
    return {
        "id": named.get("id", UUID(int=99)),
        "category": POLICY_PARAMETERS[ATTRIBUTION].category.value,
        "scope": "TENANT",
        "book_code": None,
        "entity_id": None,
        "values": values,
        "effective_from": named.get("effective_from"),
        "effective_to": named.get("effective_to"),
        "published_at": named.get("published_at", datetime(2026, 1, 1, tzinfo=UTC)),
    }


KNOWN = (  # the latest published first, as ``known_versions`` orders them
    _version(
        {ATTRIBUTION: "CUMULATIVE_SSP_DELIVERED"},
        id=UUID(int=98),
        effective_from=TOOK_EFFECT,
        published_at=TOOK_EFFECT,
    ),
    _version({ATTRIBUTION: "POB_DEBIT_POSITIONS"}, effective_to=TOOK_EFFECT),
)


class _Registry:
    """A session that answers the two statements of ``period_values`` and keeps them."""

    def __init__(self, entities: list[tuple[UUID, str]]) -> None:
        self.entities = entities
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Any:
        text = _sql(statement)
        self.statements.append(text)
        if "FROM erev.registry_version" in text:
            return type("R", (), {"mappings": lambda s: list(KNOWN)})()
        assert "FROM erev.legal_entity" in text, text
        return type("R", (), {"all": lambda s: list(self.entities)})()


def _period(key: str, number: int, end: date) -> PeriodInput:
    return PeriodInput(
        period_key=key,
        fiscal_year=2026,
        period_no=number,
        start_date=end.replace(day=1),
        end_date=end,
        states=(("ASC606", "open"),),
    )


def test_the_read_asks_for_the_runs_period_what_a_bundle_hands_to_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE TIE (the supervisor's condition of 2026-10-02 08:56, restated for the joined engine):
    for the run's entity and the run's period, ``period_values`` answers exactly the value of
    the bundle's PERIOD row — ``bundles._period_rows`` over the same versions at the same cutoff
    — for every period-pinned parameter. A version that took effect after August's last instant
    and before the cutoff is September's value and not August's, in the bundle and in the read
    alike; read at the cutoff, as before the join, it would have been August's too."""
    august, september = AUGUST_END, date(2026, 9, 30)
    assert bundles.period_end_instant(august, ZONE) < TOOK_EFFECT < CUTOFF
    entity = EntityInput(
        code="AVM-US",
        functional_currency="USD",
        time_zone=ZONE,
        calendar_pattern="MONTHLY",
        periods=(_period("FY2026-P08", 8, august), _period("FY2026-P09", 9, september)),
    )
    for end_date, key, expected in (
        (august, "FY2026-P08", "POB_DEBIT_POSITIONS"),
        (september, "FY2026-P09", "CUMULATIVE_SSP_DELIVERED"),
    ):
        scope = dataclasses.replace(SCOPE, end_date=end_date, period_key=key)
        session = _Registry([(ENTITY, ZONE)])
        read = run_inputs.period_values(session, scope, CUTOFF)  # type: ignore[arg-type]
        assert list(read) == [ENTITY] and set(read[ENTITY]) == set(registry.PERIOD_PINNED)
        assert read[ENTITY][ATTRIBUTION] == expected
        for code in registry.PERIOD_PINNED:
            rows = bundles._period_rows(
                code,
                book_code="ASC606",
                entities=[entity],
                entity_ids={"AVM-US": ENTITY},
                versions=KNOWN,
                known_at=CUTOFF,
            )
            handed = {row.subject_key: row.value for row in rows}
            value = read[ENTITY][code]
            if value is None:
                assert f"AVM-US@{key}" not in handed, code  # no version, no default: no row
            else:
                assert handed[f"AVM-US@{key}"] == engine_policy_value(value), code


def test_a_cutoff_inside_the_period_reads_at_the_cutoff() -> None:
    """The EARLIER of the two instants: a run made before its period's last instant reads what
    is in force at its cutoff, as the bundle built at that cutoff does. A version published by
    then that takes effect later in the period is not what any pass of that run read — read at
    the period's last instant whatever the cutoff, the run would record it."""
    september = date(2026, 9, 30)
    later = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert CUTOFF < later < bundles.period_end_instant(september, ZONE)
    versions = (  # the latest published first
        _version(
            {ATTRIBUTION: "POB_DEBIT_POSITIONS"},
            id=UUID(int=97),
            effective_from=later,
            published_at=TOOK_EFFECT + timedelta(hours=1),
        ),
        _version(
            {ATTRIBUTION: "CUMULATIVE_SSP_DELIVERED"},
            id=UUID(int=98),
            effective_from=TOOK_EFFECT,
            effective_to=later,
            published_at=TOOK_EFFECT,
        ),
        _version({ATTRIBUTION: "POB_DEBIT_POSITIONS"}, effective_to=TOOK_EFFECT),
    )

    class _Three(_Registry):
        def execute(self, statement: Any) -> Any:
            found = super().execute(statement)
            if "FROM erev.registry_version" in self.statements[-1]:
                return type("R", (), {"mappings": lambda s: list(versions)})()
            return found

    scope = dataclasses.replace(SCOPE, end_date=september, period_key="FY2026-P09")
    read = run_inputs.period_values(_Three([(ENTITY, ZONE)]), scope, CUTOFF)  # type: ignore[arg-type]
    assert read[ENTITY][ATTRIBUTION] == "CUMULATIVE_SSP_DELIVERED"
    entity = EntityInput(
        code="AVM-US",
        functional_currency="USD",
        time_zone=ZONE,
        calendar_pattern="MONTHLY",
        periods=(_period("FY2026-P09", 9, september),),
    )
    (row,) = bundles._period_rows(
        ATTRIBUTION,
        book_code="ASC606",
        entities=[entity],
        entity_ids={"AVM-US": ENTITY},
        versions=versions,
        known_at=CUTOFF,
    )
    assert (row.subject_key, row.value) == (
        "AVM-US@FY2026-P09",
        engine_policy_value("CUMULATIVE_SSP_DELIVERED"),
    )


def test_the_period_values_cost_two_statements_whatever_the_entities() -> None:
    """The versions known at the cutoff, once (``registry.known_versions``: PUBLISHED or
    SUPERSEDED and published by the cutoff, whatever their effective range), and the legal
    entities with their time zones. Each entity is read at the run's last day in ITS zone: for
    an entity east of the version's instant the period ends before it, for one far enough west
    after it."""
    far_west = "Pacific/Pago_Pago"  # UTC-11: 2 Sep 2026 ends at 3 Sep 10:59:59.999999 UTC
    scope = dataclasses.replace(SCOPE, end_date=date(2026, 9, 2))
    assert bundles.period_end_instant(scope.end_date, "UTC") < CUTOFF
    took_effect = bundles.period_end_instant(scope.end_date, "UTC") + timedelta(hours=1)
    monkey = (
        _version(
            {ATTRIBUTION: "CUMULATIVE_SSP_DELIVERED"},
            id=UUID(int=98),
            effective_from=took_effect,
            published_at=took_effect,
        ),
        _version({ATTRIBUTION: "POB_DEBIT_POSITIONS"}, effective_to=took_effect),
    )

    class _Two(_Registry):
        def execute(self, statement: Any) -> Any:
            found = super().execute(statement)
            if "FROM erev.registry_version" in self.statements[-1]:
                return type("R", (), {"mappings": lambda s: list(monkey)})()
            return found

    session = _Two([(ENTITY, "UTC"), (OTHER, far_west)])
    read = run_inputs.period_values(session, scope, CUTOFF)  # type: ignore[arg-type]
    assert len(session.statements) == 2
    versions, entities = session.statements
    assert versions.endswith(
        "WHERE erev.registry_version.status IN (__[POSTCOMPILE_status_1])"
        " AND erev.registry_version.published_at <= %(published_at_1)s"
        " ORDER BY erev.registry_version.published_at DESC,"
        " erev.registry_version.version_no DESC, erev.registry_version.id"
    )
    assert entities == (
        "SELECT erev.legal_entity.id, erev.legal_entity.time_zone FROM erev.legal_entity"
        " ORDER BY erev.legal_entity.id"
    )
    assert read[ENTITY][ATTRIBUTION] == "POB_DEBIT_POSITIONS"  # its 2 September had ended
    assert read[OTHER][ATTRIBUTION] == "CUMULATIVE_SSP_DELIVERED"  # its 2 September had not


def test_the_digest_of_the_registry_holds_values_and_only_what_an_entity_resolves_otherwise() -> (
    None
):
    base = {"a.one": "X", "b.two": ["P", "Q"]}
    same = run_inputs._registry_digest({ENTITY: dict(base)}, ENTITY)
    assert len(same) == 64
    # an entity that resolves every parameter as the run's entity does is not part of it
    assert run_inputs._registry_digest({ENTITY: dict(base), OTHER: dict(base)}, ENTITY) == same
    assert run_inputs._registry_digest({ENTITY: dict(reversed(base.items()))}, ENTITY) == same
    # a value of the run's entity, and a value another entity resolves otherwise, each move it
    assert run_inputs._registry_digest({ENTITY: {**base, "a.one": "Y"}}, ENTITY) != same
    moved = run_inputs._registry_digest({ENTITY: dict(base), OTHER: {**base, "a.one": "Y"}}, ENTITY)
    assert moved != same
    third = UUID(int=3)
    assert moved != run_inputs._registry_digest(
        {ENTITY: dict(base), third: {**base, "a.one": "Y"}}, ENTITY
    )


# --- the read and the comparison ------------------------------------------------------------------


class _Recording:
    """A session that answers the statements of ``read`` in order and records them."""

    def __init__(self, scope: str) -> None:
        self.scope = scope
        self.statements: list[str] = []

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        text = _sql(statement)
        self.statements.append(text)
        if "current_setting" in text:
            return type("R", (), {"scalar_one": lambda s: self.scope})()
        if "transaction_timestamp" in text:
            return type("R", (), {"scalar_one": lambda s: datetime(2026, 9, 3, 15, tzinfo=UTC)})()
        if text.startswith("SELECT encode(sha256("):
            return type("R", (), {"scalar_one": lambda s: "r" * 64})()
        if "set_config" in text:
            return None
        if "FROM erev.legal_entity" in text:
            return type("R", (), {"all": lambda s: [(ENTITY, ZONE)]})()
        return type("R", (), {"mappings": lambda s: []})()


def test_a_read_under_the_tenants_scope_costs_five_statements() -> None:
    """The scope it finds, the transaction timestamp of the cutoff, the rates, the registry's
    versions and the legal entities — in that order, the cutoff being the bundle's: the later of
    the instant and the timestamp."""
    session = _Recording("*")
    found = run_inputs.read(session, SCOPE, CUTOFF)  # type: ignore[arg-type]
    assert found.rates == "r" * 64 and len(found.registry) == 64
    kinds = [
        "scope"
        if "current_setting" in text
        else "timestamp"
        if "transaction_timestamp" in text
        else "rates"
        if text.startswith("SELECT encode(sha256(")
        else "registry"
        if "FROM erev.registry_version" in text
        else "entities"
        if "FROM erev.legal_entity" in text
        else text
        for text in session.statements
    ]
    assert kinds == ["timestamp", "scope", "rates", "registry", "entities"]


def test_a_read_under_a_narrower_scope_widens_for_its_statements_and_gives_it_back() -> None:
    """Supervisor ruling R-42 (d): a version at the level of an entity is a row of that entity,
    and what a control reads must not depend on who reads it."""
    session = _Recording("01a0fd81-dc05-7212-b4fc-a770d875e14f")
    run_inputs.read(session, SCOPE, CUTOFF)  # type: ignore[arg-type]
    marks = [
        "set"
        if "set_config" in text
        else "rates"
        if text.startswith("SELECT encode(sha256(")
        else "registry"
        if "FROM erev.registry_version" in text
        else "entities"
        if "FROM erev.legal_entity" in text
        else "-"
        for text in session.statements
    ]
    assert [mark for mark in marks if mark != "-"] == [
        "set",
        "rates",
        "registry",
        "entities",
        "set",
    ]


def test_the_gates_read_takes_the_rates_whenever_published_and_the_versions_by_its_cutoff() -> None:
    """``standing``, the gate's read (the supervisor's ruling of 2026-10-02 11:08): a version's
    ``published_at`` is the instant its approval began, so a lock decision that waited for an
    approval, or runs on a clock behind it, would not admit by time a version that is committed.
    The rates are read whenever published; the registry's versions are those published by the
    cutoff, as a bundle reads them — a version is in force over an effective range, and the
    period's value is read at its own instant. The step's read keeps the cutoff for both: it is
    what its passes can read."""
    session = _Recording("*")
    found = run_inputs.standing(session, SCOPE, CUTOFF)  # type: ignore[arg-type]
    assert found.rates == "r" * 64 and len(found.registry) == 64
    assert len(session.statements) == 5  # as ``read``: timestamp, scope, rates, registry, entities
    (rates,) = [text for text in session.statements if text.startswith("SELECT encode(sha256(")]
    (policies,) = [text for text in session.statements if "FROM erev.registry_version" in text]
    assert "published_at" not in rates
    assert " AND erev.registry_version.published_at <= %(published_at_1)s" in policies

    step = _Recording("*")
    run_inputs.read(step, SCOPE, CUTOFF)  # type: ignore[arg-type]
    (bounded,) = [text for text in step.statements if text.startswith("SELECT encode(sha256(")]
    assert bounded.count(".published_at <= ") == 2
    assert [text for text in step.statements if "FROM erev.registry_version" in text] == [policies]


def test_what_changed_is_named_as_the_gate_names_it() -> None:
    recorded = run_inputs.RunInputs(rates="a", registry="b")
    assert run_inputs.changed(recorded, recorded) == ()
    assert run_inputs.changed(recorded, run_inputs.RunInputs("x", "b")) == ("exchange rates",)
    assert run_inputs.changed(recorded, run_inputs.RunInputs("a", "y")) == ("policies",)
    assert run_inputs.changed(recorded, run_inputs.RunInputs("x", "y")) == (
        "exchange rates",
        "policies",
    )
