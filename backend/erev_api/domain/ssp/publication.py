"""SSP book version publication (04 T-REF-28, T-REF-29, §14.1 DB-04, DB-05, §15.2
``ssp-study-required``, ``configuration-overlap``, ``configuration-frozen``, table 15.4-C, T-PLT-17
``flags``, T-PLT-31 ``approval.ssp_second_approver_threshold_ratio``; POLICIES §3.3 POL-073; PRD
SM-04, §2.5 routing row ``SSP_BOOK_VERSION``, BR-SSP-01, BR-SSP-02, BR-SSP-05, ERR-09, ERR-10,
ERR-32, J-02; 03 REQ-SSP-001, REQ-SSP-007, REQ-SSP-008; CTL-010, CTL-011; BUILD_SPEC RFD-13).

A version moves DRAFT → SUBMITTED → APPROVED, and a rejected or withdrawn version returns to DRAFT
(PRD SM-04). E-12 has no DRAFT → SUBMITTED pair, so submission walks DRAFT → TESTED → SUBMITTED in
one transaction, as FX rate set versions do (RFD-3).

- ``submit_ssp_book_version`` (``POST /ssp-book-versions/{id}/submit``): a DRAFT version needs a
  live ``SSP_STUDY`` attachment whose file can still be read — a study that was shredded is none
  (04 T-PLT-29 "A document a rule asks for") — and a methodology label (422
  ``ssp-study-required``, ERR-10), an
  effective-from date when its book resolves by effective date, a label when it resolves by label,
  and at least one entry. It stores the content hash and ``diff_summary`` against the latest
  APPROVED version, audits the POL-073 findings and opens one ``SSP_BOOK_VERSION`` request.
- ``change_flags`` (the subject's T-PLT-17 routing flags): ``METHODOLOGY_CHANGE`` for a methodology
  change; ``ABOVE_THRESHOLD`` when an entry paired with the latest APPROVED version changes its
  method/value basis, or an effective band/observable/fallback point by more than the tenant
  threshold. Percentage-of-list bands include list price; nonzero changes from zero qualify. Either
  flag gives the request a second ``ssp.approve`` step (REQ-SSP-007).
- ``withdraw_ssp_book_version`` (``POST /ssp-book-versions/{id}/withdraw``): the preparer withdraws
  the pending request, and ``on_voided`` returns the version to DRAFT.
- ``approve`` (``on_approved``, after the last step): 403 ``self-approval`` for the version's
  author, 422 ``ssp-study-required`` once the study is gone, and under POL-073 ``mode = BLOCK`` 422
  ``validation-failed`` with each finding code as ``rule_id``. For a book resolved by effective
  date, an effective-from date inside the APPROVED version in force there, when that version starts
  earlier and has no end date, ends it on the day before, once, as the audited
  ``ssp_book_version.supersede``; any other overlap with an APPROVED version is 409
  ``configuration-overlap`` with the ERR-32 copy (DB-04). The version becomes APPROVED, and its
  ``ssp_book_version.approve`` event carries the warnings (BR-SSP-05).
- ``on_rejected`` and ``on_voided``: SUBMITTED → REJECTED or WITHDRAWN → DRAFT.

The two commands of a member — submit and withdraw — ask the book's reach first
(``scope.require_version_book`` with ``ssp.create``; item SSP-ENTITY-SCOPE-1): a version of a
book of an entity the caller's permission does not cover answers 404. The three hooks act for
the request that was decided and ask nothing of the decider's scope: the kernel held the
preparer and the approver to the book's entity (``subjects.ssp_book_version_entity``).

The population of a range is the calculator run linked to the version (RFD-15): its non-excluded
observations of the entry's product and currency, of which those inside the band count as inside
(POLICIES §3.3; T-REF-33 ``inside_count``; PRD J-02.5; L2-1-Q-59). A version without a linked run,
or a product without observations, gives ``COVERAGE_UNKNOWN`` outside parity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Context, Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.db.tables import approval_decision, approval_request, ssp_book, ssp_book_version
from erev_api.domain.ssp import books, calculator, queries, range_validation, scope
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ConfigStatus,
)
from erev_api.problems import Problem, ProblemError
from erev_api.registry.resolve import setting

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

SUBJECT_TYPE: Final = ApprovalSubjectType.SSP_BOOK_VERSION
THRESHOLD_PARAMETER: Final = "approval.ssp_second_approver_threshold_ratio"  # T-PLT-31
FLAG_METHODOLOGY_CHANGE: Final = subjects.SSP_METHODOLOGY_CHANGE
FLAG_ABOVE_THRESHOLD: Final = subjects.SSP_ABOVE_THRESHOLD
SUBMIT_ACTION: Final = "ssp_book_version.submit"
APPROVE_ACTION: Final = "ssp_book_version.approve"
REJECT_ACTION: Final = "ssp_book_version.reject"
WITHDRAW_ACTION: Final = "ssp_book_version.withdraw"
SUPERSEDE_ACTION: Final = "ssp_book_version.supersede"
RULE_LIFECYCLE: Final = "SM-04"
RULE_OVERLAP: Final = "DB-04"
OVERLAP_CODE: Final = "EREV-CFG-001"
DRAFT: Final = ConfigStatus.DRAFT.value
TESTED: Final = ConfigStatus.TESTED.value
SUBMITTED: Final = ConfigStatus.SUBMITTED.value
APPROVED: Final = ConfigStatus.APPROVED.value
_WIDE: Final = Context(prec=80)

# PRD §5.5 ERR-10 and ERR-32; [J] the other copy the documents leave open.
STUDY_REQUIRED: Final = "Attach the SSP study before submitting this version."
OVERLAP: Final = "Version {name} overlaps approved version {other} {range} for the same scope."
RANGE_BOUNDED: Final = "from {start} to {end}"
RANGE_OPEN: Final = "from {start} with no end date"
NOT_DRAFT: Final = "Only a draft version can be submitted."
NOT_PENDING: Final = "This version has no pending approval request to withdraw."
NOT_SUBMITTED: Final = "Only a submitted version can be approved."
EFFECTIVE_FROM_REQUIRED: Final = "Enter the effective-from date before submitting this version."
LABEL_REQUIRED: Final = (
    "Enter the version label before submitting a version of a book resolved by label."
)
ENTRIES_REQUIRED: Final = "Add at least one entry before submitting this version."


# --- helpers -------------------------------------------------------------------------------------


def _stamp(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {"updated_by": principal.id, "updated_by_kind": principal.kind.value}


def _lock_version(session: Session, version_id: UUID) -> dict[str, Any]:
    """The version under ``FOR UPDATE``; 404 when it is not visible."""
    row = (
        session.execute(
            select(ssp_book_version).where(ssp_book_version.c.id == version_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _lock_book(session: Session, book_id: Any) -> dict[str, Any]:
    """The version's book under ``FOR UPDATE``, which serializes the publications of one book."""
    statement = select(ssp_book).where(ssp_book.c.id == UUID(str(book_id))).with_for_update()
    return dict(session.execute(statement).mappings().one())


def _findings_json(findings: tuple[range_validation.RangeFinding, ...]) -> list[dict[str, Any]]:
    return [range_validation.finding_json(finding) for finding in findings]


def latest_approved(session: Session, version: Mapping[str, Any]) -> dict[str, Any] | None:
    """The highest-numbered APPROVED version of the book other than ``version``: the prior version
    the diff and the second-approver test compare with (REQ-SSP-007)."""
    row = (
        session.execute(
            select(ssp_book_version.c.id, ssp_book_version.c.version_no)
            .where(
                ssp_book_version.c.ssp_book_id == version["ssp_book_id"],
                ssp_book_version.c.id != version["id"],
                ssp_book_version.c.status == APPROVED,
            )
            .order_by(ssp_book_version.c.version_no.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return None if row is None else dict(row)


def diff_summary(
    session: Session, version_id: UUID, prior: Mapping[str, Any] | None
) -> dict[str, Any]:
    """T-REF-29 ``diff_summary``: the counts of added, removed and changed entries against the
    prior APPROVED version, which it names (L2-1-Q-29)."""
    against = [] if prior is None else queries.entries_of(session, UUID(str(prior["id"])))
    found = books.diff(queries.entries_of(session, version_id), against)
    return {
        "against_version_id": None if prior is None else str(prior["id"]),
        "added": len(found["added"]),
        "removed": len(found["removed"]),
        "changed": len(found["changed"]),
    }


# --- routing flags (REQ-SSP-007) -----------------------------------------------------------------


def _value_exceeds(old: Decimal | None, new: Decimal | None, threshold: Decimal) -> bool:
    """Compare effective values exactly; a new or removed value needs independent review.

    Cross multiplication avoids rounding a ratio at the threshold. From a zero baseline,
    any nonzero value exceeds the allowed relative change; unchanged zero does not.
    """
    if old is None or new is None:
        return old != new
    return _WIDE.subtract(new, old).copy_abs() > _WIDE.multiply(old.copy_abs(), threshold)


def _band_value(entry: Mapping[str, Any], band: Mapping[str, Any]) -> Decimal | None:
    """The per-unit mid, else point, in the entry's currency (S05-R-06)."""
    value = books.decimal_or_none(band["mid_value"])
    if value is None:
        value = books.decimal_or_none(band["point_value"])
    # Legacy bands already contain list price × (1 - discount), regardless of the
    # retained value-basis label; the engine's legacy branch does not scale them again.
    if (
        value is not None
        and entry["method"] != "legacy_range"
        and entry["value_basis"] == "PERCENT_OF_LIST"
    ):
        price = books.decimal_or_none(entry["unit_list_price"])
        return None if price is None else _WIDE.multiply(value, price)
    return value


def _unbanded_cost(entry: Mapping[str, Any]) -> Decimal | None:
    """The engine's cost-plus fallback for a retained entry without bands."""
    if entry["method"] != "cost_plus_margin" or entry["ranges"]:
        return None
    cost = books.decimal_or_none(entry["cost_basis"])
    margin = books.decimal_or_none(entry["margin_ratio"])
    if cost is None or margin is None:
        return None
    return _WIDE.multiply(cost, _WIDE.add(Decimal(1), margin))


def above_threshold(change: Mapping[str, Any], threshold: Decimal) -> bool:
    """A changed entry needs two approvers when its effective SSP changes above the limit.

    Compare like units and paired bands. A method/basis change cannot be judged by a
    percentage of unlike values and also requires the second approver (REQ-SSP-007).
    """
    before, after = change["before"], change["after"]
    if any(before[name] != after[name] for name in ("method", "value_basis", "quantity_unit")):
        return True
    if _value_exceeds(
        books.decimal_or_none(before["observable_point"]),
        books.decimal_or_none(after["observable_point"]),
        threshold,
    ) or _value_exceeds(_unbanded_cost(before), _unbanded_cost(after), threshold):
        return True
    earlier = {(band["band_dimension"], band["band_from"]): band for band in before["ranges"]}
    for band in after["ranges"]:
        paired = earlier.get((band["band_dimension"], band["band_from"]))
        if paired is not None and _value_exceeds(
            _band_value(before, paired), _band_value(after, band), threshold
        ):
            return True
    return False


def change_flags(session: Session, version_id: UUID) -> frozenset[str]:
    """The T-PLT-17 routing flags of a version at submission; ``SubjectSpec.flags``."""
    version = dict(
        session.execute(
            select(
                ssp_book_version.c.id,
                ssp_book_version.c.ssp_book_id,
                ssp_book_version.c.is_methodology_change,
            ).where(ssp_book_version.c.id == version_id)
        )
        .mappings()
        .one()
    )
    flags: set[str] = set()
    if version["is_methodology_change"]:
        flags.add(FLAG_METHODOLOGY_CHANGE)
    prior = latest_approved(session, version)
    if prior is not None:
        threshold = Decimal(str(setting(session, THRESHOLD_PARAMETER)))
        changed = books.diff(
            queries.entries_of(session, version_id),
            queries.entries_of(session, UUID(str(prior["id"]))),
        )["changed"]
        if any(above_threshold(change, threshold) for change in changed):
            flags.add(FLAG_ABOVE_THRESHOLD)
    return frozenset(flags)


# --- range validation (POL-073) ------------------------------------------------------------------


def population(
    prices: Sequence[Decimal] | None, band: Mapping[str, Any]
) -> range_validation.Population | None:
    """The population of one band: the non-excluded observations of the linked calculator run for
    the entry's product and currency, and how many lie inside [low, high], inclusive (POLICIES §3.3;
    T-REF-33 ``inside_count``); None without observations or bounds (L2-1-Q-59)."""
    low = books.decimal_or_none(band["low_value"])
    high = books.decimal_or_none(band["high_value"])
    if not prices or low is None or high is None:
        return None
    inside = sum(1 for price in prices if low <= price <= high)
    return range_validation.Population(observation_count=len(prices), inside_count=inside)


def range_rows(uow: UnitOfWork, version: Mapping[str, Any]) -> list[range_validation.RangeRow]:
    """Every band of the version in key order; the subject is the band's path in that order."""
    linked = calculator.linked_prices(uow, version)
    rows: list[range_validation.RangeRow] = []
    for index, entry in enumerate(queries.entries_of(uow.session, UUID(str(version["id"])))):
        key = (str(entry["product_code"]), str(entry["currency"]))
        prices = None if linked is None else linked.get(key)
        for band_index, band in enumerate(entry["ranges"]):
            rows.append(
                range_validation.RangeRow(
                    subject=f"entries[{index}].ranges[{band_index}]",
                    label=str(entry["product_code"]),
                    low_value=books.decimal_or_none(band["low_value"]),
                    mid_value=books.decimal_or_none(band["mid_value"]),
                    high_value=books.decimal_or_none(band["high_value"]),
                    population=population(prices, band),
                )
            )
    return rows


def range_findings(
    uow: UnitOfWork, version: Mapping[str, Any]
) -> tuple[range_validation.RangeFinding, ...]:
    """The POL-073 findings of the version under the tenant value at the command instant."""
    policy = setting(uow.session, range_validation.PARAMETER, known_at=uow.now)
    return range_validation.validate_ranges(range_rows(uow, version), policy)


# --- commands ------------------------------------------------------------------------------------


def _submit_errors(version: Mapping[str, Any], book: Mapping[str, Any]) -> list[ProblemError]:
    errors: list[ProblemError] = []
    if book["resolution_mode"] == books.EFFECTIVE_DATE and version["effective_from_date"] is None:
        errors.append(
            ProblemError(
                field="effective_from_date",
                rule_id=books.RULE_VERSION,
                message=EFFECTIVE_FROM_REQUIRED,
            )
        )
    if book["resolution_mode"] == books.BY_LABEL and version["legacy_version_label"] is None:
        errors.append(
            ProblemError(
                field="legacy_version_label", rule_id=books.RULE_BOOK, message=LABEL_REQUIRED
            )
        )
    if int(version["entry_count"]) == 0:
        errors.append(
            ProblemError(field="entries", rule_id=books.RULE_ENTRY, message=ENTRIES_REQUIRED)
        )
    return errors


def submit_ssp_book_version(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    comment: str | None,
    check_version: Callable[[int], None],
) -> None:
    """``POST /ssp-book-versions/{id}/submit``: 404; 428 or 412 for ``If-Match``; 409
    ``invalid-transition`` unless DRAFT; 422 ``ssp-study-required``; 422 ``validation-failed``
    collects the missing effective-from date, label and entries."""
    session = uow.session
    scope.require_version_book(session, uow.principal, scope.CREATE, version_id)
    version = _lock_version(session, version_id)
    check_version(int(version["row_version"]))
    if version["status"] != DRAFT:
        error = ProblemError(field="status", rule_id=RULE_LIFECYCLE, message=NOT_DRAFT)
        raise Problem("invalid-transition", errors=[error])
    book = _lock_book(session, version["ssp_book_id"])
    if not str(version["methodology_label"]).strip() or not queries.counted_study_ids(
        session, version_id
    ):
        raise Problem("ssp-study-required", STUDY_REQUIRED)
    errors = _submit_errors(version, book)
    if errors:
        raise Problem("validation-failed", errors=errors)
    content_sha256 = sha256_hex(subjects.ssp_book_version_content(session, version_id))
    summary = diff_summary(session, version_id, latest_approved(session, version))
    findings = range_findings(uow, version)
    where = ssp_book_version.c.id == version_id
    session.execute(
        update(ssp_book_version)
        .where(where)
        .values(status=TESTED, content_sha256=content_sha256, diff_summary=summary, **_stamp(uow))
    )
    session.execute(update(ssp_book_version).where(where).values(status=SUBMITTED))
    uow.audit(
        action=SUBMIT_ACTION,
        object_type=books.OBJECT_VERSION,
        object_id=version_id,
        before={
            "status": DRAFT,
            "content_sha256": version["content_sha256"],
            "diff_summary": version["diff_summary"],
        },
        after={"status": SUBMITTED, "content_sha256": content_sha256, "diff_summary": summary},
        detail={
            "lifecycle": [DRAFT, TESTED, SUBMITTED],
            "range_findings": _findings_json(findings),
        },
        comment=comment,
    )
    request = approvals.submit(
        uow,
        subject_type=SUBJECT_TYPE,
        subject_id=version_id,
        summary=f"Approve version {int(version['version_no'])} of SSP book {book['code']}",
        comment=comment,
    )
    status = session.execute(select(ssp_book_version.c.status).where(where)).scalar_one()
    if status == SUBMITTED:
        session.execute(
            update(ssp_book_version).where(where).values(approval_request_id=request["id"])
        )


def withdraw_ssp_book_version(uow: UnitOfWork, version_id: UUID, *, comment: str | None) -> None:
    """``POST /ssp-book-versions/{id}/withdraw``: 404; 409 ``invalid-transition`` without a pending
    request; 403 for anyone but the preparer (PRD SM-01). The version returns to DRAFT."""
    session = uow.session
    scope.require_version_book(session, uow.principal, scope.CREATE, version_id)
    version = _lock_version(session, version_id)
    pending = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.subject_type == SUBJECT_TYPE.value,
            approval_request.c.subject_id == version_id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
    ).scalar_one_or_none()
    if version["status"] != SUBMITTED or pending is None:
        error = ProblemError(field="status", rule_id=RULE_LIFECYCLE, message=NOT_PENDING)
        raise Problem("invalid-transition", NOT_PENDING, errors=[error])
    approvals.withdraw(
        uow, approval_request_id=UUID(str(pending)), comment=comment, through_subject=True
    )


# --- approval callbacks --------------------------------------------------------------------------


def _approvers(session: Session, approval_request_id: UUID) -> set[UUID]:
    """The people whose APPROVE decisions the request holds, delegators included."""
    rows = session.execute(
        select(approval_decision.c.approver_id, approval_decision.c.on_behalf_of_id).where(
            approval_decision.c.approval_request_id == approval_request_id,
            approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
        )
    ).all()
    return {UUID(str(value)) for row in rows for value in row if value is not None}


def _day(value: date) -> str:
    return f"{value:%d %b %Y}"


def _name(row: Mapping[str, Any]) -> str:
    label = row["legacy_version_label"]
    return f"v{int(row['version_no'])}" if label is None else str(label)


def _range_text(start: date, end: date | None) -> str:
    if end is None:
        return RANGE_OPEN.format(start=_day(start))
    return RANGE_BOUNDED.format(start=_day(start), end=_day(end))


def _contains(row: Mapping[str, Any], day: date) -> bool:
    start, end = row["effective_from_date"], row["effective_to_date"]
    return (start is None or start <= day) and (end is None or day <= end)


def _overlaps(
    first_from: date | None, first_to: date | None, second_from: date, second_to: date | None
) -> bool:
    """Inclusive date ranges overlap; an absent end is open."""
    first_starts_in_time = second_to is None or first_from is None or first_from <= second_to
    second_starts_in_time = first_to is None or second_from <= first_to
    return first_starts_in_time and second_starts_in_time


def _supersede(
    uow: UnitOfWork, version: Mapping[str, Any], approval_request_id: UUID
) -> UUID | None:
    """BR-SSP-02: end the APPROVED version in force at the effective-from date on the day before,
    when it starts earlier and has no end date; 409 ``configuration-overlap`` for any other
    overlap. Returns the superseded version's id."""
    session = uow.session
    start: date | None = version["effective_from_date"]
    if start is None:
        error = ProblemError(
            field="effective_from_date", rule_id=books.RULE_VERSION, message=EFFECTIVE_FROM_REQUIRED
        )
        raise Problem("validation-failed", errors=[error])
    end: date | None = version["effective_to_date"]
    rows = [
        dict(row)
        for row in session.execute(
            select(
                ssp_book_version.c.id,
                ssp_book_version.c.version_no,
                ssp_book_version.c.legacy_version_label,
                ssp_book_version.c.effective_from_date,
                ssp_book_version.c.effective_to_date,
            )
            .where(
                ssp_book_version.c.ssp_book_id == version["ssp_book_id"],
                ssp_book_version.c.id != version["id"],
                ssp_book_version.c.status == APPROVED,
            )
            .order_by(ssp_book_version.c.effective_from_date, ssp_book_version.c.version_no)
            .with_for_update()
        ).mappings()
    ]
    prior = next((row for row in rows if _contains(row, start)), None)
    day_before = start - timedelta(days=1)
    trims = (
        prior is not None
        and prior["effective_to_date"] is None
        and prior["effective_from_date"] is not None
        and prior["effective_from_date"] < start
    )
    for row in rows:
        row_end = day_before if trims and row is prior else row["effective_to_date"]
        if _overlaps(row["effective_from_date"], row_end, start, end):
            message = OVERLAP.format(
                name=_name(version),
                other=_name(row),
                range=_range_text(row["effective_from_date"], row["effective_to_date"]),
            )
            error = ProblemError(field="effective_from_date", rule_id=RULE_OVERLAP, message=message)
            raise Problem("configuration-overlap", message, code=OVERLAP_CODE, errors=[error])
    if prior is None or not trims:
        return None
    prior_id = UUID(str(prior["id"]))
    session.execute(
        update(ssp_book_version)
        .where(ssp_book_version.c.id == prior_id)
        .values(effective_to_date=day_before, **_stamp(uow))
    )
    uow.audit(
        action=SUPERSEDE_ACTION,
        object_type=books.OBJECT_VERSION,
        object_id=prior_id,
        before={"effective_to_date": None},
        after={"effective_to_date": day_before.isoformat()},
        detail={"superseded_by_version_id": str(version["id"])},
        approval_request_id=approval_request_id,
    )
    return prior_id


def approve(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> None:
    """``SubjectSpec.on_approved``: SUBMITTED → APPROVED in the deciding transaction; a refusal
    rolls the decision back (DG-KRN-APR-02)."""
    session = uow.session
    version = _lock_version(session, version_id)
    if version["status"] != SUBMITTED:
        error = ProblemError(field="status", rule_id=RULE_LIFECYCLE, message=NOT_SUBMITTED)
        raise Problem("invalid-transition", errors=[error])
    approvers = _approvers(session, approval_request_id)
    if version["created_by"] is not None and UUID(str(version["created_by"])) in approvers:
        raise Problem("self-approval", approvals.SELF_APPROVAL_DETAIL)
    book = _lock_book(session, version["ssp_book_id"])
    if not queries.counted_study_ids(session, version_id):
        raise Problem("ssp-study-required", STUDY_REQUIRED)
    findings = range_findings(uow, version)
    blocking = [finding for finding in findings if finding.severity == range_validation.ERROR]
    if blocking:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field=finding.subject, rule_id=finding.code, message=finding.message)
                for finding in blocking
            ],
        )
    superseded = None
    if book["resolution_mode"] == books.EFFECTIVE_DATE:
        superseded = _supersede(uow, version, approval_request_id)
    principal_id = uow.principal.id
    published_by = principal_id if principal_id in approvers else None
    session.execute(
        update(ssp_book_version)
        .where(ssp_book_version.c.id == version_id)
        .values(
            status=APPROVED,
            approval_request_id=approval_request_id,
            published_at=uow.now,
            published_by=published_by,
            **_stamp(uow),
        )
    )
    uow.audit(
        action=APPROVE_ACTION,
        object_type=books.OBJECT_VERSION,
        object_id=version_id,
        before={"status": SUBMITTED, "published_at": None, "published_by": None},
        after={
            "status": APPROVED,
            "approval_request_id": str(approval_request_id),
            "published_at": uow.now.isoformat(),
            "published_by": None if published_by is None else str(published_by),
        },
        detail={
            "range_findings": _findings_json(findings),
            "diff_summary": version["diff_summary"],
            "superseded_version_id": None if superseded is None else str(superseded),
        },
        approval_request_id=approval_request_id,
    )


def _close(to_status: ConfigStatus, action: str) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """``on_rejected`` (REJECTED) or ``on_voided`` (WITHDRAWN): a SUBMITTED version takes
    ``to_status``, then returns to DRAFT without a content hash (PRD SM-04); any other status stays
    as it is."""

    def close(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        session = uow.session
        found = (
            session.execute(
                select(ssp_book_version.c.status, ssp_book_version.c.content_sha256)
                .where(ssp_book_version.c.id == subject_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if found is None or found["status"] != SUBMITTED:
            return
        where = ssp_book_version.c.id == subject_id
        session.execute(
            update(ssp_book_version).where(where).values(status=to_status.value, **_stamp(uow))
        )
        session.execute(update(ssp_book_version).where(where).values(status=DRAFT))
        session.execute(update(ssp_book_version).where(where).values(content_sha256=None))
        uow.audit(
            action=action,
            object_type=books.OBJECT_VERSION,
            object_id=subject_id,
            before={"status": SUBMITTED, "content_sha256": found["content_sha256"]},
            after={"status": DRAFT, "content_sha256": None},
            detail={"lifecycle": [SUBMITTED, to_status.value, DRAFT]},
            approval_request_id=approval_request_id,
        )

    return close


subjects.register_lifecycle(
    SUBJECT_TYPE,
    subjects.SubjectLifecycle(
        on_approved=approve,
        on_rejected=_close(ConfigStatus.REJECTED, REJECT_ACTION),
        on_voided=_close(ConfigStatus.WITHDRAWN, WITHDRAW_ACTION),
        flags=change_flags,
    ),
)
