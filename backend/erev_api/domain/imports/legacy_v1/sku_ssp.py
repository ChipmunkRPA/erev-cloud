"""Legacy v1 template ``legacy_sku_ssp`` (ENGINE_SPEC S01-R-05, S03-R-18; 04 T-IMP-01, §17.3
LM-SSP-01 to LM-SSP-09, T-REF-20, T-REF-28 to T-REF-31; PRD J-01.6, J-01.7; 03 REQ-SSP-013;
BUILD_SPEC DIN-4).

Rows group by ``SSP Version`` label in worksheet order, one plan per label. A plan:

1. creates book ``LEGACY-SKU-SSP`` (``resolution_mode = BY_LABEL``) when absent;
2. creates each absent product with ``name = code``, the first ``SKU Unique ID`` seen and the
   template flag as ``distinctness_default`` (LM-SSP-01 to LM-SSP-03). [J] L5-1-Q-13: under the
   ``LEGACY_PARITY`` preset the product is ``PRINCIPAL`` (POL-030 parity value, so S03-R-09 never
   refuses it) and takes the seeded template ``LEGACY-DISTINCT`` or ``LEGACY-NONDISTINCT`` of its
   flag as default template when that template has a PUBLISHED version (S03-R-18, T-MIG-01);
3. creates each absent revenue account (``create_missing_accounts``, type ``REVENUE``; LM-SSP-09);
4. adds the version labelled with the label, and one ``legacy_range`` entry per row whose ``NONE``
   band is derived at full precision (``books.legacy_band``: mid = L × (1 − d), low = mid × (1 − r),
   high = mid × (1 + r));
5. at commit, moves the version DRAFT → TESTED → SUBMITTED → APPROVED under the import's approval
   request, whose approver publishes it (S01-R-05 "APPROVED after the import approval").

A later file with another label adds a version and leaves the approved ones unchanged
(REQ-SSP-013); a label the book already holds is refused by ``create_ssp_book_version``.

Validation adds ``SSP_DUPLICATE_KEY`` (IMP-08; DEV-015; TC-setup-13) to every row whose (``SKU
Name``, ``ASC 606 Stratification``, ``SSP Version``) key repeats in the file, naming every
contributing row, or equals a row of an approved version (BUILD_SPEC DIN-7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.db.tables import (
    gl_account,
    import_upload,
    pob_template,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    tenant,
)
from erev_api.domain.imports import findings
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2 import ssp_declarations, ssp_values
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    ContractChange,
    CsvRow,
    CsvTemplate,
    Performed,
    Plan,
)
from erev_api.domain.imports.legacy_v1 import headers
from erev_api.domain.policies import templates as template_rules
from erev_api.domain.reference.commands import create_gl_account, create_product
from erev_api.domain.reference.products import PRINCIPAL_AGENT_POLICY
from erev_api.domain.ssp import publication, resolution
from erev_api.domain.ssp.commands import (
    create_ssp_book,
    create_ssp_book_version,
    upsert_ssp_entries,
)
from erev_api.enums import (
    AccountType,
    ApprovalSubjectType,
    Distinctness,
    PrincipalAgent,
    RegistryScope,
    SourceObjectType,
    SourceSystem,
    SspMethod,
)
from erev_api.problems import Problem
from erev_api.registry import presets
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.products import ProductIn
from erev_api.schemas.ssp_books import SspBookIn, SspBookVersionIn, SspEntriesIn, SspEntryIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "BOOK_CODE",
    "CODE",
    "ROW_RULES",
    "TEMPLATE",
    "approved_midpoints",
    "cross_findings",
    "reporting_currency",
]

CODE: Final = "legacy_sku_ssp"
BOOK_CODE: Final = "LEGACY-SKU-SSP"  # S01-R-05
BOOK_NAME: Final = "Legacy SKU SSP"
METHODOLOGY: Final = "Legacy SKU SSP upload {import_no}"
ACCOUNT_NAME: Final = "Revenue {code}"
FLAGS: Final[Mapping[str, Distinctness]] = {
    "Distinct": Distinctness.DISTINCT,
    "Nondistinct": Distinctness.NONDISTINCT,
}  # LM-SSP-03
PARITY_TEMPLATES: Final[Mapping[Distinctness, str]] = {
    Distinctness.DISTINCT: "LEGACY-DISTINCT",
    Distinctness.NONDISTINCT: "LEGACY-NONDISTINCT",
}  # S03-R-18
# PRD IMP-10 and IMP-11.
FLAG_MESSAGE: Final = (
    'Distinct or Nondistinct must be exactly Distinct or Nondistinct. Found "{value}".'
)
DISCOUNT_MESSAGE: Final = "Midpoint Discount Percentage must be at least 0 and below 1."
RANGE_MESSAGE: Final = "SSP Range Method (+-) must be at least 0."
# PRD IMP-08.
DUPLICATE_KEY: Final = (
    "SSP key {key} appears more than once or already exists in an approved version."
)


# --- row rules (04 table 15.4-A; IMP-10, IMP-11) -------------------------------------------------


# Ruling (c), F-DIN 2026-09-19: the legacy template carries no value basis, so a row for a product
# whose default POB template is `series` would take the silent T-REF-30 default AMOUNT; it is
# refused (04 table 15.4-A SSP_VALUE_BASIS_REQUIRED at the SKU column); the v2 template declares
# it.
SERIES_NOT_DECLARABLE: Final = (
    "The legacy SKU SSP template cannot declare the value basis of the series product {sku}; "
    "import its entries with the ssp_values template and an explicit lines.value_basis."
)


def _series_findings(
    session: Session, rows: Sequence[tuple[int, Mapping[str, Any]]]
) -> dict[int, list[headers.RowFinding]]:
    codes = {headers.text(values, columns.SKU) or "" for _, values in rows}
    series = ssp_declarations.series_products(session, codes)
    found: dict[int, list[headers.RowFinding]] = {}
    for number, values in rows:
        sku = headers.text(values, columns.SKU) or ""
        if sku in series:
            message = findings.csv_located(
                SERIES_NOT_DECLARABLE.format(sku=sku),
                ssp_declarations.CODE_BASIS_REQUIRED,
                row_number=number,
                column=columns.SKU,
            )
            found.setdefault(number, []).append(
                headers.RowFinding(
                    ssp_declarations.CODE_BASIS_REQUIRED, "ERROR", message, columns.SKU
                )
            )
    return found


def _flag_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    value = typed.get(columns.DISTINCT_FLAG)
    if value is None or str(value) in FLAGS:
        return ()
    message = FLAG_MESSAGE.format(value=value)
    return (
        headers.RowFinding("SSP_DISTINCT_FLAG_INVALID", "ERROR", message, columns.DISTINCT_FLAG),
    )


def _percent_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    found: list[headers.RowFinding] = []
    discount = typed.get(columns.DISCOUNT)
    if isinstance(discount, Decimal) and not Decimal(0) <= discount < Decimal(1):
        found.append(
            headers.RowFinding(
                "SSP_PERCENT_OUT_OF_RANGE", "ERROR", DISCOUNT_MESSAGE, columns.DISCOUNT
            )
        )
    spread = typed.get(columns.RANGE)
    if isinstance(spread, Decimal) and spread < 0:
        found.append(
            headers.RowFinding("SSP_PERCENT_OUT_OF_RANGE", "ERROR", RANGE_MESSAGE, columns.RANGE)
        )
    return found


ROW_RULES: Final = (_flag_rule, _percent_rule)


# --- cross-row and cross-file rules (04 table 15.4-A; IMP-08) -------------------------------------

type SspKey = tuple[str, str, str]  # (label, SKU, stratification), as S01-R-05 resolves it


def ssp_key(values: Mapping[str, Any]) -> SspKey:
    """The (``SSP Version``, ``SKU Name``, ``ASC 606 Stratification``) key of a row."""
    return (
        headers.text(values, columns.SSP_VERSION) or "",
        headers.text(values, columns.SKU) or "",
        headers.text(values, columns.STRATIFICATION) or "",
    )


def approved_midpoints(session: Session) -> dict[SspKey, Decimal | None]:
    """The unit midpoint L × (1 − d) of each row of the APPROVED ``LEGACY-SKU-SSP`` versions, by
    (label, SKU, stratification); None when the row lacks the list price or the discount."""
    rows = session.execute(
        select(
            ssp_book_version.c.legacy_version_label,
            product.c.code,
            ssp_entry.c.stratification,
            ssp_entry.c.unit_list_price,
            ssp_entry.c.midpoint_discount_ratio,
        )
        .select_from(
            ssp_entry.join(
                ssp_book_version, ssp_book_version.c.id == ssp_entry.c.ssp_book_version_id
            )
            .join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
            .join(product, product.c.id == ssp_entry.c.product_id)
        )
        .where(
            ssp_book.c.code == BOOK_CODE,
            ssp_book_version.c.status == publication.APPROVED,
            ssp_book_version.c.legacy_version_label.is_not(None),
        )
    ).all()
    found: dict[SspKey, Decimal | None] = {}
    for label, code, stratification, price, discount in rows:
        key = (str(label), str(code), str(stratification))
        if price is None or discount is None:
            found[key] = None
        else:
            found[key] = Decimal(str(price)) * (1 - Decimal(str(discount)))
    return found


def key_text(key: SspKey) -> str:
    """IMP-08 and IMP-09 ``<SKU / stratification / version>``."""
    label, code, stratification = key
    return f"{code} / {stratification} / {label}"


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[headers.RowFinding]]:
    """``SSP_DUPLICATE_KEY`` for each row whose key repeats in the file or equals a row of an
    approved version (IMP-08; REQ-SSP-013); ``SSP_VALUE_BASIS_REQUIRED`` for a row naming a series
    product, which this template cannot declare (ruling (c), F-DIN)."""
    del known_at, parameters
    found: dict[int, list[headers.RowFinding]] = _series_findings(session, rows)
    numbers: dict[SspKey, list[int]] = {}
    for number, values in sorted(rows, key=lambda item: item[0]):
        numbers.setdefault(ssp_key(values), []).append(number)
    approved = approved_midpoints(session)
    for key, members in numbers.items():
        if len(members) < 2 and key not in approved:
            continue
        message = findings.every_row(DUPLICATE_KEY.format(key=key_text(key)), members)
        for number in members:
            found.setdefault(number, []).append(
                headers.RowFinding("SSP_DUPLICATE_KEY", "ERROR", message, columns.SKU)
            )
    return found


# --- plans and apply -----------------------------------------------------------------------------


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per ``SSP Version`` label, in worksheet order of first appearance."""
    grouped: dict[str, list[CsvRow]] = {}
    for row in rows:
        grouped.setdefault(headers.text(row.normalized, columns.SSP_VERSION) or "", []).append(row)
    return [Plan(key=label, rows=tuple(members), body={}) for label, members in grouped.items()]


def reporting_currency(uow: UnitOfWork) -> str:
    """The tenant reporting currency (T-PLT-01), the currency of legacy entries and contracts."""
    found = uow.session.execute(
        select(tenant.c.reporting_currency).where(tenant.c.id == uow.principal.tenant_id)
    ).scalar_one()
    return str(found).strip()


def _book(uow: UnitOfWork) -> UUID:
    found = uow.session.execute(select(ssp_book.c.id).where(ssp_book.c.code == BOOK_CODE)).first()
    if found is not None:
        return UUID(str(found[0]))
    return create_ssp_book(
        uow, body=SspBookIn(code=BOOK_CODE, name=BOOK_NAME, resolution_mode="BY_LABEL")
    )


def product_parity_values() -> dict[str, Any]:
    """[J] L5-1-Q-25: the ``LEGACY_PARITY`` values a product carries at level P: the accounting
    parameters allowed at ``PRODUCT`` that a TENANT version cannot hold, such as POL-051
    ``returns.model``, POL-053 ``returns.returned_units_scope`` and POL-026
    ``material_right.ssp_method`` (POLICIES §6.3); POL-030 is the product's own conclusion."""
    tenant_values = presets.legacy_parity_values(scope=RegistryScope.TENANT, book_code=None)
    return {
        code: value
        for code, value in presets.legacy_parity_values(
            scope=RegistryScope.PRODUCT, book_code=None
        ).items()
        if code not in tenant_values and code != PRINCIPAL_AGENT_POLICY
    }


def _parity_templates(uow: UnitOfWork) -> dict[Distinctness, UUID]:
    """The seeded parity templates with a PUBLISHED version, by flag (S03-R-18)."""
    session = uow.session
    rows = session.execute(
        select(pob_template.c.code, pob_template.c.id).where(
            pob_template.c.code.in_(sorted(PARITY_TEMPLATES.values()))
        )
    ).all()
    by_code = {str(code): UUID(str(value)) for code, value in rows}
    return {
        flag: by_code[code]
        for flag, code in PARITY_TEMPLATES.items()
        if code in by_code and template_rules.has_published_version(session, by_code[code])
    }


def _products(uow: UnitOfWork, rows: Sequence[CsvRow], *, parity: bool) -> None:
    """Create the absent products of the rows (LM-SSP-01 to LM-SSP-03)."""
    session = uow.session
    codes = {headers.text(row.normalized, columns.SKU) or "" for row in rows}
    existing = {
        str(value)
        for value in session.execute(
            select(product.c.code).where(product.c.code.in_(sorted(codes)))
        ).scalars()
    }
    chosen = _parity_templates(uow) if parity else {}
    for row in rows:
        code = headers.text(row.normalized, columns.SKU) or ""
        if code in existing:
            continue
        flag = FLAGS[str(headers.text(row.normalized, columns.DISTINCT_FLAG))]
        create_product(
            uow,
            body=ProductIn(
                code=code,
                name=code,
                sku_number=headers.text(row.normalized, columns.SKU_ID),
                distinctness_default=flag,
                principal_agent=PrincipalAgent.PRINCIPAL if parity else PrincipalAgent.NOT_ASSESSED,
                default_pob_template_id=chosen.get(flag),
                policy_values=product_parity_values() if parity else {},
            ),
        )
        existing.add(code)


def _accounts(uow: UnitOfWork, rows: Sequence[CsvRow]) -> None:
    """Create the absent revenue accounts of the rows (LM-SSP-09)."""
    session = uow.session
    codes = {
        code
        for code in (headers.text(row.normalized, columns.REVENUE_ACCOUNT) for row in rows)
        if code is not None
    }
    existing = {
        str(value)
        for value in session.execute(
            select(gl_account.c.code).where(gl_account.c.code.in_(sorted(codes)))
        ).scalars()
    }
    for code in sorted(codes - existing):
        create_gl_account(
            uow,
            body=GlAccountIn(
                code=code,
                name=ACCOUNT_NAME.format(code=code),
                account_type=AccountType.REVENUE,
                normal_balance="C",
            ),
            source_system=SourceSystem.LEGACY_TEMPLATE_V1,
        )


def _entry(row: CsvRow, currency: str) -> SspEntryIn:
    values = row.normalized
    return SspEntryIn(
        product_code=headers.text(values, columns.SKU) or "",
        stratification=headers.text(values, columns.STRATIFICATION) or "",
        currency=currency,
        method=SspMethod.LEGACY_RANGE,
        unit_list_price=format(headers.number(values, columns.LIST_PRICE) or Decimal(0), "f"),
        midpoint_discount_ratio=format(headers.number(values, columns.DISCOUNT) or Decimal(0), "f"),
        range_ratio=format(headers.number(values, columns.RANGE) or Decimal(0), "f"),
        revenue_account_code=headers.text(values, columns.REVENUE_ACCOUNT),
        distinctness=FLAGS[str(headers.text(values, columns.DISTINCT_FLAG))],
    )


def _approve(uow: UnitOfWork, version_id: UUID, context: ApplyContext) -> None:
    """DRAFT → TESTED → SUBMITTED → APPROVED under the import's approval request (S01-R-05)."""
    session = uow.session
    version = dict(
        session.execute(select(ssp_book_version).where(ssp_book_version.c.id == version_id))
        .mappings()
        .one()
    )
    content_sha256 = sha256_hex(subjects.ssp_book_version_content(session, version_id))
    summary = publication.diff_summary(
        session, version_id, publication.latest_approved(session, version)
    )
    principal = uow.principal
    stamps = {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    where = ssp_book_version.c.id == version_id
    session.execute(
        update(ssp_book_version)
        .where(where)
        .values(
            status=publication.TESTED,
            content_sha256=content_sha256,
            diff_summary=summary,
            **stamps,
        )
    )
    session.execute(update(ssp_book_version).where(where).values(status=publication.SUBMITTED))
    # The approver who answered for the version by ordinal (R-98 (9) as refined, rev 1.198).
    published_by = context.approver_of(ApprovalSubjectType.SSP_BOOK_VERSION)
    session.execute(
        update(ssp_book_version)
        .where(where)
        .values(
            status=publication.APPROVED,
            approval_request_id=context.approval_request_id,
            published_at=uow.now,
            published_by=published_by,
        )
    )
    uow.audit(
        action=publication.APPROVE_ACTION,
        object_type="ssp_book_version",
        object_id=version_id,
        before={"status": publication.DRAFT, "content_sha256": None},
        after={
            "status": publication.APPROVED,
            "content_sha256": content_sha256,
            "published_by": None if published_by is None else str(published_by),
        },
        detail={
            "import_upload_id": str(context.import_upload_id),
            "lifecycle": [
                publication.DRAFT,
                publication.TESTED,
                publication.SUBMITTED,
                publication.APPROVED,
            ],
        },
        approval_request_id=context.approval_request_id,
    )


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """One book version of the label with its entries; approved at commit (S01-R-05)."""
    parity = resolution.tenant_preset(uow.session, known_at=uow.now) == presets.LEGACY_PARITY
    refused = _series_findings(uow.session, [(row.row_number, row.normalized) for row in plan.rows])
    if refused:  # defensive: validation refused these rows already; nothing is written
        raise Problem("validation-failed", next(iter(refused.values()))[0].message)
    currency = reporting_currency(uow)
    book_id = _book(uow)
    _products(uow, plan.rows, parity=parity)
    _accounts(uow, plan.rows)
    version_id = create_ssp_book_version(
        uow,
        book_id,
        body=SspBookVersionIn(
            legacy_version_label=plan.key,
            methodology_label=METHODOLOGY.format(import_no=context.import_no or "(dry run)"),
        ),
    )
    entry_ids = upsert_ssp_entries(
        uow, version_id, body=SspEntriesIn(entries=[_entry(row, currency) for row in plan.rows])
    )
    if not context.dry_run:
        _approve(uow, version_id, context)
    applied = Applied()
    applied.targets.append(("ssp_book_version", version_id))
    for row, entry_id in zip(plan.rows, entry_ids, strict=True):
        applied.row_targets[row.id] = [("ssp_entry", entry_id)]
    return applied


def underlying(
    session: Session,
    plan: Plan,
    applied: Applied,
    context: ApplyContext,
    changes: Mapping[str, ContractChange],
) -> dict[ApprovalSubjectType, list[Performed]]:
    """Ruling R-38 (ii): the commit approves the plan's version (S01-R-05), so the import approval
    answers for an ``SSP_BOOK_VERSION`` approval — with the routing flags that subject states for
    the version the dry run wrote (REQ-SSP-007: a methodology change, or an entry that moves by
    more than the threshold against the latest APPROVED version). A request of that subject
    carries no amount (item IMP-FLOOR-AMOUNT-1)."""
    del plan, context, changes
    spec = subjects.spec_for(ApprovalSubjectType.SSP_BOOK_VERSION)
    return {
        ApprovalSubjectType.SSP_BOOK_VERSION: [
            Performed(
                flags=frozenset(spec.flags(session, target_id)),
                amount=spec.amount_functional(session, target_id),
            )
            for target_type, target_id in applied.targets
            if target_type == "ssp_book_version"
        ]
    }


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Read legacy SSP prices and derived ranges independently of the emitter request."""
    currency = str(
        session.execute(
            select(tenant.c.reporting_currency)
            .join(import_upload, import_upload.c.tenant_id == tenant.c.id)
            .where(import_upload.c.id == context.import_upload_id)
        ).scalar_one()
    ).strip()
    translated = tuple(
        replace(
            row,
            normalized={
                "ssp_book_code": BOOK_CODE,
                "lines.product_code": row.normalized[columns.SKU],
                "lines.stratification": row.normalized[columns.STRATIFICATION],
                "lines.currency": currency,
                "lines.method": "legacy_range",
                "lines.distinctness": FLAGS[str(row.normalized[columns.DISTINCT_FLAG])],
                "lines.unit_list_price": str(row.normalized[columns.LIST_PRICE]),
                "lines.midpoint_discount_ratio": str(row.normalized[columns.DISCOUNT]),
                "lines.range_ratio": str(row.normalized[columns.RANGE]),
            },
        )
        for row in plan.rows
    )
    return ssp_values.reconcile_amounts(
        session, replace(plan, rows=translated), applied, context=context
    )


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.SSP_ROW,
    target_type="ssp_book_version",
    key_column=columns.SSP_VERSION,
    columns=(),
    plans=plans,
    apply=apply,
    source_system=SourceSystem.LEGACY_TEMPLATE_V1,
    underlying=underlying,
    reconcile_amounts=reconcile_amounts,
)
