"""The entity scope table of the import templates and its pure rules (security findings SC-2 and
SC-3, imports part; supervisor rulings R-28, R-29, R-38 (ii), R-41 (5), R-98, R-109; 04 rev 1.107
and 1.147 T-IMP-02, table 15.4-B ``IMPORT_ENTITY_NOT_AVAILABLE`` and
``IMPORT_CONTRACT_INCOMPLETE``, §16.6 template scope table; 05 rev 1.46 and 1.86 IPL-05 to IPL-10;
03 REQ-PLT-012, REQ-DAT-008).

No database: the table against the template registry and the permission catalogue, the findings
and the fail-closed helper over a resolution built by hand, and the shape of what the dry run
records for the approvals a commit performs. The database witnesses are
``tests/domain/imports/test_entity_scope.py`` and ``legacy_v1/test_approval_floor.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.auth import permissions
from erev_api.auth.principal import system_principal
from erev_api.domain.imports import csv_v2, diff, scope, validate
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import (
    UNEVALUATED,
    Applied,
    ApplyContext,
    ContractChange,
    Performed,
    Plan,
)
from erev_api.domain.imports.legacy_v1 import modification
from erev_api.enums import ApprovalSubjectType, ImportRowStatus, PrincipalKind

US = UUID(int=0x0A)
UK = UUID(int=0x0B)
DE = UUID(int=0x0C)
TENANT = UUID(int=0x01)
UPLOADER = UUID(int=0x02)


def resolution(
    *,
    codes: dict[str, UUID] | None = None,
    ids: frozenset[UUID] = frozenset(),
    contracts: dict[str, UUID] | None = None,
    books: dict[str, UUID | None] | None = None,
) -> scope.Resolution:
    codes = codes or {}
    contracts = contracts or {}
    books = books or {}
    named = (
        frozenset(codes.values())
        | ids
        | frozenset(contracts.values())
        | frozenset(entity for entity in books.values() if entity is not None)
    )
    return scope.Resolution(named, codes, ids, contracts, books)


def bounds(*allowed: UUID) -> scope.Bounds:
    held = frozenset(allowed)
    return scope.Bounds(allowed=held, db_scope=held)


EVERY = scope.Bounds(allowed="*", db_scope="*")


# --- the table --------------------------------------------------------------------------------


def test_every_uploadable_template_declares_its_scope() -> None:
    """``POST /imports`` accepts exactly the templates the table rules on; a template without a
    row has no bounds and ``scope_of`` fails closed."""
    assert set(scope.TEMPLATE_SCOPES) == set(validate.ROW_MODELS)
    with pytest.raises(LookupError):
        scope.scope_of("modifications")


def test_write_permissions_are_catalogue_permissions_a_preparer_holds() -> None:
    """The write permission is the one of the equivalent API command: a catalogue code, never an
    approval permission (the uploader prepares, REQ-PLT-011), and one a default preparer role
    holds — the Revenue Accountant, or the SSP Analyst for the SSP templates (PRD §5.6)."""
    preparers = (
        permissions.DEFAULT_ROLES["revenue_accountant"] | permissions.DEFAULT_ROLES["ssp_analyst"]
    )
    for code, spec in scope.TEMPLATE_SCOPES.items():
        permission = permissions.spec(spec.write_permission)
        assert not permission.is_approval, code
        assert spec.write_permission in preparers, code
    assert {
        code: spec.write_permission
        for code, spec in scope.TEMPLATE_SCOPES.items()
        if code.startswith("legacy_") or code in ("contracts", "ssp_values", "account_mapping")
    } == {
        "legacy_sku_ssp": "ssp.create",
        "legacy_contract_setup": "contract.create",
        "legacy_progress_tracking": "event.record",
        "legacy_contract_modification": "modification.create",
        "contracts": "contract.create",
        "ssp_values": "ssp.create",
        "account_mapping": "config.author",
    }


def test_tenant_level_templates_are_the_ones_of_ruling_r_41_5() -> None:
    """R-41 (5): customers, products, FX rates, GL accounts — and bundles, a product attribute —
    name no legal entity; SSP values and account mappings are tenant-level only when the book or
    the rules name none, which the upload decides, not the template."""
    tenant_level = {code for code, spec in scope.TEMPLATE_SCOPES.items() if spec.tenant_level}
    assert tenant_level == {
        "legacy_sku_ssp",
        "customers",
        "products",
        "bundles",
        "fx_rates",
        "gl_accounts",
    }
    assert scope.TEMPLATE_SCOPES["ssp_values"].ssp_book_column == "ssp_book_code"
    assert scope.TEMPLATE_SCOPES["account_mapping"].entity_id_columns == ("lines.entity_id",)


def test_one_set_the_contracting_entities() -> None:
    """R-114 (g) with the supervisor's word of 2026-10-01 — R-41 (5)'s clause on performing and
    selling entities is replaced (04 T-IMP-02 rev 1.256; 05 IPL-08 rev 1.186): the entities an
    upload names are the ones its rows write for — the CSV contract's contracting entity, the
    legacy ``Selling Entity`` of a contract's first row. A performing entity is looked up and no
    more: the CSV line's column, the legacy ``Selling Entity`` of every row of a setup file and
    of a modification's added line."""
    setup = scope.TEMPLATE_SCOPES["legacy_contract_setup"]
    assert setup.entity_code_columns == (columns.SELLING_ENTITY,)
    assert setup.performing_code_columns == (columns.SELLING_ENTITY,)
    assert setup.contracting_on_first_row
    added = scope.TEMPLATE_SCOPES["legacy_contract_modification"]
    assert added.entity_code_columns == ()
    assert added.performing_code_columns == (columns.SELLING_ENTITY,)
    assert not added.tenant_level  # the contract its key names is its entity
    contracts = scope.TEMPLATE_SCOPES["contracts"]
    assert contracts.entity_code_columns == ("contracting_entity_code",)
    assert contracts.performing_code_columns == ("lines.performing_entity_code",)
    assert not contracts.contracting_on_first_row
    # no other template names a performing entity or reads its entity from a first row
    others = {
        code
        for code, spec in scope.TEMPLATE_SCOPES.items()
        if spec.performing_code_columns or spec.contracting_on_first_row
    }
    assert others == {"legacy_contract_setup", "legacy_contract_modification", "contracts"}


def test_contract_columns_are_the_registered_contract_columns() -> None:
    """The contract a row names is read from the column the approvals kernel pins the heads of
    (``subjects.register_import_contract_column``): one source for both. ``estimates`` names its
    contract too, without being registered there (its target is an estimate version)."""
    beyond: set[str] = set()
    for code, spec in scope.TEMPLATE_SCOPES.items():
        registered = subjects.import_contract_column(code)
        if registered is None and spec.contract_column is not None:
            beyond.add(code)
            continue
        assert spec.contract_column == registered, code
    assert beyond == {"estimates"}


def test_a_template_performs_an_approval_exactly_when_it_states_one() -> None:
    """R-38 (ii): the templates whose commit performs an approval by itself are the ones that
    carry the dry-run evaluator, and every such approval has a built subject specification and a
    name for the refusal."""
    for code, spec in scope.TEMPLATE_SCOPES.items():
        template = diff.emitter_of(code)
        assert template is not None, code
        assert (template.underlying is not None) == bool(spec.puts_in_force), code
        for subject in spec.puts_in_force:
            assert subjects.spec_for(subject).required_permission, (code, subject)
            assert subject in scope._ACTS, (code, subject)
    performing = {code for code, spec in scope.TEMPLATE_SCOPES.items() if spec.puts_in_force}
    assert performing == {
        "legacy_sku_ssp",
        "legacy_contract_setup",
        "legacy_contract_modification",
    }


# --- findings (04 table 15.4-B) ---------------------------------------------------------------


def test_an_entity_outside_the_scope_and_an_unknown_entity_get_one_copy() -> None:
    """REQ-PLT-012: the finding never tells whether an entity exists — the copy names the text the
    uploader typed and nothing looked up."""
    found = scope.findings(
        "contracts",
        [
            (2, {"external_id": "A", "contracting_entity_code": "AVM-US"}),
            (3, {"external_id": "B", "contracting_entity_code": "AVM-ZZ"}),
            (4, {"external_id": "C", "contracting_entity_code": "AVM-UK"}),
        ],
        resolution(codes={"AVM-US": US, "AVM-UK": UK}),
        bounds(UK),
    )
    assert sorted(found) == [2, 3]
    (outside,) = found[2]
    (unknown,) = found[3]
    assert (outside.code, outside.severity, outside.column) == (
        "IMPORT_ENTITY_NOT_AVAILABLE",
        "ERROR",
        "contracting_entity_code",
    )
    assert outside.message == (
        "Legal entity AVM-US is not available for this import. "
        "Upload these rows under a role that covers the entity."
    )
    assert unknown.message == outside.message.replace("AVM-US", "AVM-ZZ")


def test_a_performing_entity_must_exist_and_need_not_be_covered() -> None:
    """R-114 (g): a line performed by an entity outside the uploader's scope is the uploader's
    to write — the booking command reads it so (05 RCP-18; ruling R-95) — and raises no finding;
    a performing entity that does not exist is refused, with the one copy. Before, AVM-US as a
    performing entity was refused for an uploader of AVM-UK."""
    row = {"external_id": "A", "contracting_entity_code": "AVM-UK"}
    known = resolution(codes={"AVM-US": US, "AVM-UK": UK})
    performed = {**row, "lines.performing_entity_code": "AVM-US"}
    assert scope.findings("contracts", [(2, performed)], known, bounds(UK)) == {}
    assert scope.outside("contracts", performed, known, bounds(UK)) == frozenset()
    unknown = {**row, "lines.performing_entity_code": "AVM-ZZ"}
    found = scope.findings("contracts", [(2, unknown)], known, bounds(UK))
    assert [(item.column, item.code, item.message) for item in found[2]] == [
        (
            "lines.performing_entity_code",
            "IMPORT_ENTITY_NOT_AVAILABLE",
            "Legal entity AVM-ZZ is not available for this import. "
            "Upload these rows under a role that covers the entity.",
        )
    ]
    # it must exist for an uploader of every entity too
    assert sorted(scope.findings("contracts", [(2, unknown)], known, EVERY)) == [2]


def test_the_legacy_selling_entity_is_the_contracting_entity_on_a_contracts_first_row() -> None:
    """R-114 (g): the legacy setup's ``Selling Entity`` names the contracting entity on the first
    row of a contract and the line's performing entity on every row
    (``legacy_v1.contract_setup._book``). A later row performed by an entity outside the scope
    is the uploader's to write; a first row's is refused; a later row's that does not exist is
    refused; and a modification's added line names a performing entity only."""
    rows = [
        (2, {columns.CONTRACT: "L-1", columns.SELLING_ENTITY: "AVM-UK"}),
        (3, {columns.CONTRACT: "L-1", columns.SELLING_ENTITY: "AVM-US"}),
        (4, {columns.CONTRACT: "L-2", columns.SELLING_ENTITY: "AVM-US"}),
        (5, {columns.CONTRACT: "L-2", columns.SELLING_ENTITY: "AVM-UK"}),
        (6, {columns.CONTRACT: "L-1", columns.SELLING_ENTITY: "AVM-ZZ"}),
    ]
    cells = [row for _, row in rows]
    setup = "legacy_contract_setup"
    assert scope.writing_rows(setup, cells) == [True, False, True, False, False]
    known = resolution(codes={"AVM-US": US, "AVM-UK": UK})
    found = scope.findings(setup, rows, known, bounds(UK))
    assert {number: [item.column for item in items] for number, items in found.items()} == {
        4: [columns.SELLING_ENTITY],  # the contracting entity of L-2 is outside the scope
        6: [columns.SELLING_ENTITY],  # a performing entity that does not exist
    }
    assert scope.outside(setup, cells[1], known, bounds(UK), writes=False) == frozenset()
    assert scope.outside(setup, cells[2], known, bounds(UK), writes=True) == frozenset({US})
    # elsewhere every row names what it writes for
    assert scope.writing_rows("contracts", cells) == [True] * 5
    # a modification's added line: a performing entity, whatever its entity
    modification_file = "legacy_contract_modification"
    added = {columns.CONTRACT: "L-1", columns.SELLING_ENTITY: "AVM-US"}
    assert scope.findings(modification_file, [(2, added)], known, bounds(UK)) == {}
    assert scope.outside(modification_file, added, known, bounds(UK)) == frozenset()
    gone = {columns.CONTRACT: "L-1", columns.SELLING_ENTITY: "AVM-ZZ"}
    assert sorted(scope.findings(modification_file, [(2, gone)], known, bounds(UK))) == [2]


def test_the_rows_that_commit_are_read_in_file_order() -> None:
    """R-114 (g): the first row of a contract names its entity, so the usable rows of an upload
    are read by sheet and row number — whatever order the table holds them in — when the
    uploader's cover is read again at submit and at commit (``committing_entity_ids``)."""
    statement = str(scope.usable_rows(UUID(int=0x77)))
    assert statement.endswith("ORDER BY erev.import_row.sheet_name, erev.import_row.row_number"), (
        statement
    )


def test_a_contract_template_key_of_another_entitys_contract_is_refused() -> None:
    """A row whose key names an existing contract of an entity outside the scope would replace or
    collide with a contract the uploader cannot write."""
    found = scope.findings(
        "contracts",
        [(2, {"external_id": "SF-ORD-20417", "contracting_entity_code": "AVM-UK"})],
        resolution(codes={"AVM-UK": UK}, contracts={"SF-ORD-20417": US}),
        bounds(UK),
    )
    assert [(item.column, item.message) for item in found[2]] == [
        ("external_id", "Contract SF-ORD-20417 is not available for this import.")
    ]


def test_a_contract_event_template_raises_no_finding_of_its_own() -> None:
    """A contract of another entity in a contract-keyed template is ``CONTRACT_NOT_FOUND`` through
    the template's own rule, which reads inside the scope — no second, telling finding here."""
    rows = [(2, {"contract": "SF-ORD-20417"})]
    other = resolution(contracts={"SF-ORD-20417": US})
    assert scope.findings("invoices", rows, other, bounds(UK)) == {}
    assert scope.findings("invoices", rows, resolution(), bounds(UK)) == {}


def test_an_ssp_book_outside_the_scope_and_an_unknown_book_get_one_copy() -> None:
    rows = [
        (2, {"ssp_book_code": "US-LIST"}),
        (3, {"ssp_book_code": "NO-SUCH"}),
        (4, {"ssp_book_code": "GLOBAL"}),
        (5, {"ssp_book_code": "UK-LIST"}),
    ]
    found = scope.findings(
        "ssp_values",
        rows,
        resolution(books={"US-LIST": US, "GLOBAL": None, "UK-LIST": UK}),
        bounds(UK),
    )
    assert sorted(found) == [2, 3]
    assert found[2][0].message == "SSP book US-LIST is not available for this import."
    assert found[3][0].message == "SSP book NO-SUCH is not available for this import."


def test_an_account_mapping_rule_names_its_entity_by_id() -> None:
    rows = [
        (2, {"name": "MAP", "lines.entity_id": str(US)}),
        (3, {"name": "MAP", "lines.entity_id": str(UK)}),
        (4, {"name": "MAP", "lines.entity_id": ""}),
        (5, {"name": "MAP", "lines.entity_id": "not-a-uuid"}),
    ]
    found = scope.findings("account_mapping", rows, resolution(ids=frozenset({US, UK})), bounds(UK))
    assert sorted(found) == [2, 5]


def test_an_all_entities_uploader_is_refused_only_what_does_not_exist() -> None:
    found = scope.findings(
        "contracts",
        [
            (2, {"external_id": "A", "contracting_entity_code": "AVM-US"}),
            (3, {"external_id": "B", "contracting_entity_code": "AVM-ZZ"}),
        ],
        resolution(codes={"AVM-US": US}, contracts={"A": US}),
        EVERY,
    )
    assert sorted(found) == [3]


def test_tenant_level_templates_raise_nothing() -> None:
    for code, spec in scope.TEMPLATE_SCOPES.items():
        if spec.tenant_level:
            assert scope.findings(code, [(2, {"code": "C-1"})], resolution(), bounds()) == {}


def test_outside_is_the_fail_closed_reading_of_one_row() -> None:
    """The validation job keeps a row usable only when ``outside`` finds nothing: every way a row
    names an entity is read again, independent of the rules above."""
    found = resolution(
        codes={"AVM-US": US, "AVM-UK": UK}, contracts={"K-1": DE}, books={"US-LIST": US}
    )
    row = {"external_id": "K-1", "contracting_entity_code": "AVM-US"}
    assert scope.outside("contracts", row, found, bounds(UK)) == frozenset({US, DE})
    assert scope.outside("contracts", row, found, bounds(UK, US, DE)) == frozenset()
    assert scope.outside("contracts", row, found, EVERY) == frozenset()
    assert scope.outside("invoices", {"contract": "K-1"}, found, bounds(UK)) == frozenset({DE})
    book = {"ssp_book_code": "US-LIST"}
    assert scope.outside("ssp_values", book, found, bounds(UK)) == frozenset({US})


# --- exact keys and references that do not resolve (ruling R-98 (2)) --------------------------


def test_a_key_is_the_exact_text_of_its_cell() -> None:
    """R-98 (2): a key is looked up as the templates' own rules read it — exact text, nothing
    stripped. A contract whose external id carries white space is that contract, and the same
    text without the white space is another key: before, the scope read ``K-1`` from the cell
    ``K-1 `` and found no entity while the template matched the cell as typed."""
    spaced = resolution(contracts={"K-1 ": DE}, codes={" AVM-US": US}, books={"US-LIST\u00a0": US})
    assert scope.outside("invoices", {"contract": "K-1 "}, spaced, bounds(UK)) == frozenset({DE})
    assert scope.outside("invoices", {"contract": "K-1"}, spaced, bounds(UK)) == frozenset()
    row = {"external_id": "N-1", "contracting_entity_code": " AVM-US"}
    assert scope.outside("contracts", row, spaced, bounds(UK)) == frozenset({US})
    book = {"ssp_book_code": "US-LIST\u00a0"}
    assert scope.outside("ssp_values", book, spaced, bounds(UK)) == frozenset({US})
    # The findings read the same text: the code as typed is outside the scope, by name.
    found = scope.findings("contracts", [(2, row)], spaced, bounds(UK))
    assert [item.message for item in found[2]] == [
        "Legal entity  AVM-US is not available for this import. "
        "Upload these rows under a role that covers the entity."
    ]
    # A blank cell names nothing; white space alone is blank.
    assert scope.key_text(None) is None and scope.key_text("   ") is None
    assert scope.key_text(" K-1 ") == " K-1 "


def test_a_reference_that_does_not_resolve_leaves_the_upload_unresolved() -> None:
    """R-98 (2): what the upload stores is the named set, or nothing (NULL: every entity) when a
    row names a reference that does not resolve — never the empty set of a tenant-level
    upload."""
    assert resolution(codes={"AVM-UK": UK}).named == frozenset({UK})
    assert resolution().named == frozenset()
    unresolved = scope.Resolution(frozenset({UK}), {"AVM-UK": UK}, frozenset(), {}, {}, True)
    assert unresolved.named is None and unresolved.entity_ids == frozenset({UK})


# --- quarantine mode loads a subject whole or not at all (rulings R-98 (10), R-109 (c)) -------


def row(
    number: int, status: ImportRowStatus, unit_key: str | None, **cells: Any
) -> validate.RowResult:
    usable = status is not ImportRowStatus.ERROR
    return validate.RowResult(
        row_number=number,
        raw={name: str(value) for name, value in cells.items()},
        normalized=dict(cells) if usable else None,
        status=status,
        business_key=unit_key,
        row_sha256="0" * 64,
        findings=(),
        unit_key=unit_key,
    )


def test_quarantine_refuses_the_other_rows_of_a_refused_rows_contract() -> None:
    """A usable row of a contract another row of which was refused is refused with it, by name;
    the rows of the other contracts stay, and so does a row without a contract."""
    valid, error = ImportRowStatus.VALID, ImportRowStatus.ERROR
    rows = (
        row(2, valid, "K-1", contract="K-1"),
        row(3, error, "K-1", contract="K-1"),
        row(4, ImportRowStatus.WARNING, "K-1", contract="K-1"),
        row(5, valid, "K-2", contract="K-2"),
        row(6, error, None, contract=""),
        row(7, ImportRowStatus.AGGREGATED, "K-1", contract="K-1"),
        row(8, valid, "K-1 ", contract="K-1 "),  # another key: exact text
    )
    found = validate.incomplete_units("usage", validate.Validation("csv", (), rows, len(rows)))
    assert sorted(found) == [2, 4, 7]
    (finding,) = found[2]
    assert (finding.code, finding.severity, finding.column) == (
        "IMPORT_CONTRACT_INCOMPLETE",
        "ERROR",
        "contract",
    )
    assert finding.message == (
        "Another row of contract K-1 was refused, so none of its rows is loaded. "
        "Correct that row and upload the contract's rows again."
    )


def test_quarantine_units_are_every_object_a_file_builds_from_several_rows() -> None:
    """R-109 (c) and R-116 (g): the subject that loads whole or not at all is the contract for
    every template with a contract column, the SSP book version for the legacy SKU SSP template,
    and the object the rows of a CSV v2 file build together — a bundle, a mapping version, the
    version of an SSP book, a rate set version. A template each of whose rows is an object of its
    own keeps the row-by-row semantics of REQ-DAT-008. (Until R-116 (g) the four were row by
    row: a bundle lost the component of a refused row, and a version was built without it.)"""
    units = {code: spec.unit for code, spec in scope.TEMPLATE_SCOPES.items()}
    assert {code for code, unit in units.items() if unit is None} == {
        "customers",
        "products",
        "gl_accounts",
    }
    assert units["legacy_sku_ssp"] == (columns.SSP_VERSION, "SSP version")
    objects = {
        "bundles": ("product_code", "bundle"),
        "account_mapping": ("name", "mapping version"),
        "ssp_values": ("ssp_book_code", "SSP book"),
        "fx_rates": ("fx_rate_set_code", "rate set"),
    }
    for code, unit in units.items():
        if code in objects:
            assert unit == objects[code], code
            # the column is the one the template's rows are grouped by into one command
            assert unit[0] == csv_v2.TEMPLATES[code].key_column, code
        elif unit is not None and code != "legacy_sku_ssp":
            assert unit == (scope.TEMPLATE_SCOPES[code].contract_column, "contract"), code
    # naming an object names no entity: the two master-data templates stay tenant-level
    assert scope.TEMPLATE_SCOPES["bundles"].tenant_level
    assert scope.TEMPLATE_SCOPES["fx_rates"].tenant_level
    # The version column names no entity: the template stays tenant-level.
    assert scope.TEMPLATE_SCOPES["legacy_sku_ssp"].tenant_level
    valid, error = ImportRowStatus.VALID, ImportRowStatus.ERROR
    rows = (
        row(2, valid, "2023-01-01", **{columns.SSP_VERSION: "2023-01-01"}),
        row(3, error, "2023-01-01", **{columns.SSP_VERSION: "2023-01-01"}),
        row(4, valid, "2024-01-01", **{columns.SSP_VERSION: "2024-01-01"}),
    )
    found = validate.incomplete_units(
        "legacy_sku_ssp", validate.Validation("SKU Setup", (), rows, len(rows))
    )
    assert sorted(found) == [2]
    assert found[2][0].message == (
        "Another row of SSP version 2023-01-01 was refused, so none of its rows is loaded. "
        "Correct that row and upload the version's rows again."
    )
    assert validate.incomplete_units("customers", validate.Validation("csv", (), rows, 3)) == {}
    # R-116 (g): the usable rows of a bundle, a mapping version, an SSP book and a rate set one
    # of whose rows was refused are refused with it, by name; the rows of another object stay
    for code, (column, kind), short in (
        ("bundles", objects["bundles"], "bundle"),
        ("account_mapping", objects["account_mapping"], "version"),
        ("ssp_values", objects["ssp_values"], "book"),
        ("fx_rates", objects["fx_rates"], "set"),
    ):
        built = (
            row(2, valid, "A", **{column: "A"}),
            row(3, error, "A", **{column: "A"}),
            row(4, valid, "B", **{column: "B"}),
        )
        found = validate.incomplete_units(code, validate.Validation("csv", (), built, len(built)))
        assert sorted(found) == [2], code
        (finding,) = found[2]
        assert (finding.code, finding.severity, finding.column) == (
            "IMPORT_CONTRACT_INCOMPLETE",
            "ERROR",
            column,
        ), code
        assert finding.message == (
            f"Another row of {kind} A was refused, so none of its rows is loaded. "
            f"Correct that row and upload the {short}'s rows again."
        ), code


# --- the principal and the stored set ---------------------------------------------------------


def test_the_import_principal_holds_its_permissions_for_the_scope_only() -> None:
    """05 IPL-07 rev 1.46: SYSTEM on behalf of the uploader, every import permission held for the
    uploader's scope — never ``*`` for an entity-restricted uploader (decision L5-1-Q-11 as
    narrowed by R-29)."""
    base = system_principal(TENANT, on_behalf_of_id=UPLOADER)
    narrow = scope.import_principal(base, diff.IMPORT_PERMISSIONS, frozenset({UK}))
    assert narrow.kind is PrincipalKind.SYSTEM and narrow.on_behalf_of_id == UPLOADER
    assert narrow.entity_scope == (UK,)
    assert set(narrow.permission_scopes) == set(diff.IMPORT_PERMISSIONS)
    assert set(narrow.permission_scopes.values()) == {frozenset({UK})}
    wide = scope.import_principal(base, diff.IMPORT_PERMISSIONS, "*")
    assert wide.entity_scope == "*" and set(wide.permission_scopes.values()) == {"*"}


def test_the_stored_set_distinguishes_unresolved_from_tenant_level() -> None:
    assert scope.stored({"named_entity_ids": None}) is None
    assert scope.stored({"named_entity_ids": []}) == frozenset()
    assert scope.stored({"named_entity_ids": [str(UK), US]}) == frozenset({UK, US})
    assert scope.covers("*", frozenset({US}))
    assert scope.covers(frozenset({UK, US}), frozenset({US}))
    assert not scope.covers(frozenset({UK}), frozenset({US}))


def test_holding_a_scope_for_an_uploads_entities() -> None:
    """R-41 (5): a tenant-level upload (no entity named) is decidable by any holder; an unresolved
    one needs every entity; otherwise the scope covers the whole named set."""
    assert not scope._held(None, frozenset())
    assert scope._held(frozenset(), frozenset())
    assert scope._held(frozenset({UK}), frozenset({UK}))
    assert not scope._held(frozenset({UK}), frozenset({UK, US}))
    assert not scope._held(frozenset({UK, US}), None)
    assert scope._held("*", None)


# --- what the dry run records (04 §16.6 ``diff_summary.underlying_approvals``) ----------------


def test_the_record_of_the_underlying_approvals() -> None:
    """Sorted by subject; per subject the union of the flags, ``evaluated`` false when the flags
    of one approval could not be evaluated, and — item IMP-FLOOR-AMOUNT-1 — the distinct routing
    facts among its approvals with the number of approvals that carry them, in a fixed order.

    The expectation of the first two members is the one of part A, restated on the statement
    per approval (STALE EXPECTATION under the item: the record gained ``instances`` and the dry
    run now states approvals one by one)."""
    usd = "USD"
    activation = ApprovalSubjectType.CONTRACT_ACTIVATION
    record = scope.underlying_record(
        {
            ApprovalSubjectType.JUDGEMENT_RECORD: [Performed(flags=None), Performed(flags=None)],
            activation: [
                Performed(flags=frozenset(), amount=(Decimal("1300.00"), usd)),
                Performed(
                    flags=frozenset({"ABOVE_THRESHOLD", "ABOVE_CONTROLLER_THRESHOLD"}),
                    amount=(Decimal("1000800.00"), usd),
                ),
                Performed(flags=frozenset(), amount=(Decimal("1300.0"), usd)),
                Performed(flags=frozenset(), amount=None),  # another currency: no amount
                UNEVALUATED,  # a plan that failed
            ],
        }
    )
    assert record == [
        {
            "subject_type": "CONTRACT_ACTIVATION",
            "flags": ["ABOVE_CONTROLLER_THRESHOLD", "ABOVE_THRESHOLD"],
            "evaluated": False,
            "instances": [
                {
                    "flags": [],
                    "evaluated": False,
                    "amount": None,
                    "amount_evaluated": False,
                    "count": 1,
                },
                {
                    "flags": [],
                    "evaluated": True,
                    "amount": None,
                    "amount_evaluated": True,
                    "count": 1,
                },
                {
                    "flags": [],
                    "evaluated": True,
                    "amount": {"amount": "1300.00", "currency": "USD"},
                    "amount_evaluated": True,
                    "count": 2,
                },
                {
                    "flags": ["ABOVE_CONTROLLER_THRESHOLD", "ABOVE_THRESHOLD"],
                    "evaluated": True,
                    "amount": {"amount": "1000800.00", "currency": "USD"},
                    "amount_evaluated": True,
                    "count": 1,
                },
            ],
        },
        {
            "subject_type": "JUDGEMENT_RECORD",
            "flags": [],
            "evaluated": False,
            "instances": [
                {
                    "flags": [],
                    "evaluated": False,
                    "amount": None,
                    "amount_evaluated": True,
                    "count": 2,
                }
            ],
        },
    ]
    assert scope.underlying_record({}) == []
    # The order does not depend on the order of the plans (the diff file is hashed).
    reordered = scope.underlying_record(
        {activation: [UNEVALUATED, Performed(flags=frozenset(), amount=(Decimal("5.00"), usd))]}
    )
    assert reordered == scope.underlying_record(
        {activation: [Performed(flags=frozenset(), amount=(Decimal("5.00"), usd)), UNEVALUATED]}
    )


def test_an_entry_states_its_instances_and_an_older_entry_reads_unevaluated() -> None:
    """``approval_floor`` passes on what each approval would carry as a request of its own. An
    entry written before the member existed states one approval with the entry's flags whose
    amount was never stated: not evaluated, so it counts as the strictest outcome."""
    stated = scope._instances(
        {
            "subject_type": "CONTRACT_ACTIVATION",
            "flags": ["ABOVE_THRESHOLD"],
            "evaluated": True,
            "instances": [
                {
                    "flags": ["ABOVE_THRESHOLD"],
                    "evaluated": True,
                    "amount": {"amount": "250000.00", "currency": "USD"},
                    "amount_evaluated": True,
                    "count": 3,
                },
                {
                    "flags": [],
                    "evaluated": False,
                    "amount": None,
                    "amount_evaluated": False,
                    "count": 1,
                },
            ],
        }
    )
    assert stated == (
        scope.UnderlyingInstance(
            flags=frozenset({"ABOVE_THRESHOLD"}),
            evaluated=True,
            amount=(Decimal("250000.00"), "USD"),
            amount_evaluated=True,
            count=3,
        ),
        scope.UnderlyingInstance(
            flags=frozenset(), evaluated=False, amount=None, amount_evaluated=False, count=1
        ),
    )
    older = scope._instances(
        {"subject_type": "SSP_BOOK_VERSION", "flags": ["X"], "evaluated": True}
    )
    assert older == (
        scope.UnderlyingInstance(
            flags=frozenset({"X"}), evaluated=True, amount=None, amount_evaluated=False, count=1
        ),
    )


# --- a legacy modification's own routing facts (rulings R-38 (ii), R-98 (4)) ------------------


class _Entity:
    """A session that answers one question: the functional currency of the contract's entity."""

    def __init__(self, functional: str) -> None:
        self.functional = functional

    def execute(self, statement: Any) -> _Entity:
        del statement
        return self

    def scalar_one(self) -> str:
        return self.functional


def _modification(
    currency: str,
    functional: str,
    *,
    before: str = "1000.00",
    after: str = "1400.00",
    catch_up: str = "100.00",
    computed: bool = True,
) -> Performed:
    """What the dry run states for one plan that moved the price of contract K-1."""
    contract_id, group_id = UUID(int=0x21), UUID(int=0x22)
    applied = Applied(contracts=[("K-1", contract_id, group_id, 3)], computed=computed)
    change = ContractChange(
        currency=currency,
        transaction_price_before=Decimal(before),
        transaction_price_after=Decimal(after),
        catch_up_total=Decimal(catch_up),
    )
    context = ApplyContext(
        import_upload_id=UUID(int=0x23),
        file_sha256="0" * 64,
        template_code="legacy_contract_modification",
        template_version=1,
        dry_run=True,
    )
    found = modification.underlying(
        _Entity(functional),  # type: ignore[arg-type]
        Plan(key="K-1", rows=(), body={}),
        applied,
        context,
        {"K-1": change},
    )
    assert list(found) == [ApprovalSubjectType.MODIFICATION]
    (performed,) = found[ApprovalSubjectType.MODIFICATION]
    return performed


def test_a_modification_states_the_flags_and_the_amount_its_own_request_would_carry() -> None:
    """Item IMP-FLOOR-AMOUNT-1 on PRD §2.5: the flags compare the dry run's figures with the USD
    thresholds, so they are evaluated for a USD contract only (the upload retains no FX basis);
    the amount is the absolute change of the transaction price in the FUNCTIONAL currency, so it
    is stated when the contract currency is that currency and not evaluated otherwise. The two
    are independent."""
    usd = _modification("USD", "USD")
    assert usd == Performed(flags=frozenset(), amount=(Decimal("400.00"), "USD"))
    large = _modification("USD", "USD", after="301000.00", catch_up="-60000.00")
    assert large == Performed(
        flags=frozenset({"CATCH_UP_GE_50K", "TP_CHANGE_GE_250K"}),
        amount=(Decimal("300000.00"), "USD"),
    )
    # A USD contract of an entity that keeps its books in GBP: flags yes, amount no.
    abroad = _modification("USD", "GBP", after="301000.00")
    assert abroad == Performed(
        flags=frozenset({"TP_CHANGE_GE_250K"}), amount=None, amount_evaluated=False
    )
    # A EUR contract of a EUR entity: no USD rate for the flags; the amount at a rate of 1.
    euro = _modification("EUR", "EUR", after="900.00")
    assert euro == Performed(flags=None, amount=(Decimal("100.00"), "EUR"))
    # A EUR contract of a USD entity: nothing can be stated.
    assert _modification("EUR", "USD") == UNEVALUATED


def test_a_modification_is_not_evaluated_unless_its_computation_succeeded() -> None:
    """R-98 (4): a computation that ended QUARANTINED or FAILED leaves the earlier version in
    place, so the figures read "no change" whatever the amendment — the plan says so
    (``Applied.computed``) and the approval is stated unevaluated, flags and amount."""
    assert _modification("USD", "USD", after="1000.00", computed=False) == UNEVALUATED
    assert _modification("USD", "USD", after="301000.00", computed=False) == UNEVALUATED
    # With a computation that succeeded, an unchanged price is a real "no change".
    unchanged = _modification("USD", "USD", after="1000.00", catch_up="0.00")
    assert unchanged == Performed(flags=frozenset(), amount=(Decimal("0.00"), "USD"))
