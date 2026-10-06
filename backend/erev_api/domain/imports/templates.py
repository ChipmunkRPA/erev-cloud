"""The import template registry and template downloads (04 T-IMP-01, §16.6 API-S-ImportTemplate;
05 UPL-21; 03 REQ-DAT-016; BUILD_SPEC DIN-1).

Revision 0044 seeds ``import_template`` (DG-MIG-07), and the registry reads those rows. What the
rows do not hold (the business-key columns of each legacy template, the example row of each
download, and ``LEGACY_HEADER_TYPES``, which the per-row models are built from) lives in
``legacy_templates``, the allow-listed home of legacy column names (DG-MK-vocab-check, D-33).

``build_download`` renders a template as XLSX through XlsxWriter with the UPL-21 options: the first
sheet holds the exact headers and one example row, and the sheet "Definitions" one row per header
(name, type, required, rule ids). Cells are written as text (L4-1-Q-30).
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

import xlsxwriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import import_template
from erev_api.domain.imports.legacy_templates import EXAMPLES, KEY_COLUMNS, LEGACY_HEADER_TYPES
from erev_api.schemas.imports import (
    ImportTemplateHeaderOut,
    ImportTemplateOut,
    ImportTemplateParameterOut,
)

__all__ = [
    "CATALOGUE_ORDER",
    "EXAMPLES",
    "KEY_COLUMNS",
    "LEGACY_HEADER_TYPES",
    "NUMERIC_TYPES",
    "Header",
    "Parameter",
    "Template",
    "build_download",
    "current_templates",
    "download_href",
    "find_template",
    "template_out",
]

type HeaderType = Literal["identifier", "text", "label", "amount", "quantity", "ratio", "date"]

NUMERIC_TYPES: Final = frozenset({"amount", "quantity", "ratio"})
DOWNLOAD_HREF: Final = "/api/v1/import-templates/{code}/download"
DEFINITIONS_SHEET: Final = "Definitions"
DEFINITION_COLUMNS: Final = ("name", "type", "required", "rule_ids")
XLSX_OPTIONS: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
        "strings_to_numbers": False,
    }
)
# UPL-20: text that a spreadsheet could read as a formula is prefixed with an apostrophe.
_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")
# 04 T-IMP-01 table order.
CATALOGUE_ORDER: Final = (
    "legacy_sku_ssp",
    "legacy_contract_setup",
    "legacy_progress_tracking",
    "legacy_contract_modification",
    "customers",
    "products",
    "bundles",
    "ssp_values",
    "contracts",
    "invoices",
    "progress_events",
    "usage",
    "modifications",
    "estimates",
    "fx_rates",
    "cost_events",
    "pre_standard_revenue",
    "gl_accounts",
    "account_mapping",
)


@dataclass(frozen=True, slots=True)
class Header:
    name: str
    type: str
    required: bool
    rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    type: str
    allowed_values: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class Template:
    """One ``import_template`` row."""

    code: str
    version: int
    name: str
    family: Literal["LEGACY_V1", "CSV_V2"]
    target_object: str
    file_format: Literal["XLSX", "CSV"]
    sheet_rule: str
    header_match: Literal["EXACT_SET", "ALIASES"]
    headers: tuple[Header, ...]
    required_parameters: tuple[Parameter, ...]
    row_model: str
    aggregation_rule: str | None
    is_current: bool


def _template(row: Mapping[str, Any]) -> Template:
    headers = tuple(
        Header(
            name=str(item["name"]),
            type=str(item["type"]),
            required=bool(item["required"]),
            rule_ids=tuple(str(rule) for rule in item["rule_ids"]),
        )
        for item in row["headers"]
    )
    parameters = tuple(
        Parameter(
            name=str(item["name"]),
            type=str(item["type"]),
            allowed_values=None
            if item.get("allowed_values") is None
            else tuple(str(value) for value in item["allowed_values"]),
        )
        for item in row["required_parameters"]
    )
    return Template(
        code=str(row["code"]),
        version=int(row["version"]),
        name=str(row["name"]),
        family=row["family"],
        target_object=str(row["target_object"]),
        file_format=row["file_format"],
        sheet_rule=str(row["sheet_rule"]),
        header_match=row["header_match"],
        headers=headers,
        required_parameters=parameters,
        row_model=str(row["row_model"]),
        aggregation_rule=None if row["aggregation_rule"] is None else str(row["aggregation_rule"]),
        is_current=bool(row["is_current"]),
    )


def _order(template: Template) -> tuple[int, str, int]:
    known = template.code in CATALOGUE_ORDER
    return (
        CATALOGUE_ORDER.index(template.code) if known else len(CATALOGUE_ORDER),
        template.code,
        template.version,
    )


def current_templates(session: Session) -> list[Template]:
    """The current version of every template, in 04 T-IMP-01 order."""
    rows = session.execute(select(import_template).where(import_template.c.is_current)).mappings()
    return sorted((_template(dict(row)) for row in rows), key=_order)


def find_template(session: Session, code: str, version: int | None = None) -> Template | None:
    """One template version, or its current version without ``version``; None when absent."""
    statement = select(import_template).where(import_template.c.code == code)
    if version is None:
        statement = statement.where(import_template.c.is_current)
    else:
        statement = statement.where(import_template.c.version == version)
    row = (
        session.execute(statement.order_by(import_template.c.version.desc()).limit(1))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _template(dict(row))


def download_href(code: str) -> str:
    return DOWNLOAD_HREF.format(code=code)


def template_out(template: Template) -> ImportTemplateOut:
    """API-S-ImportTemplate."""
    return ImportTemplateOut(
        code=template.code,
        version=template.version,
        name=template.name,
        family=template.family,
        file_format=template.file_format,
        headers=[
            ImportTemplateHeaderOut(
                name=header.name,
                type=header.type,
                required=header.required,
                rule_ids=list(header.rule_ids),
            )
            for header in template.headers
        ],
        required_parameters=[
            ImportTemplateParameterOut(
                name=parameter.name,
                type=parameter.type,
                allowed_values=None
                if parameter.allowed_values is None
                else list(parameter.allowed_values),
            )
            for parameter in template.required_parameters
        ],
        download_href=download_href(template.code),
    )


def safe_text(value: str) -> str:
    """UPL-20: an apostrophe before text a spreadsheet could evaluate."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _sheet_title(name: str) -> str:
    title = "".join(" " if character in "[]:*?/\\" else character for character in name)
    return title[:31]


def build_download(template: Template, examples: Mapping[str, str] | None = None) -> bytes:
    """The XLSX of a template: headers and one example row, then the "Definitions" sheet."""
    row = EXAMPLES.get(template.code, {}) if examples is None else examples
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, dict(XLSX_OPTIONS))
    sheet = workbook.add_worksheet(_sheet_title(template.name))
    for column, header in enumerate(template.headers):
        sheet.write_string(0, column, safe_text(header.name))
        example = row.get(header.name)
        if example:
            sheet.write_string(1, column, safe_text(example))
    definitions = workbook.add_worksheet(DEFINITIONS_SHEET)
    for column, label in enumerate(DEFINITION_COLUMNS):
        definitions.write_string(0, column, label)
    for number, header in enumerate(template.headers, start=1):
        definitions.write_string(number, 0, safe_text(header.name))
        definitions.write_string(number, 1, header.type)
        definitions.write_boolean(number, 2, header.required)
        definitions.write_string(number, 3, ", ".join(header.rule_ids))
    workbook.close()
    return buffer.getvalue()


def header_names(template: Template) -> Sequence[str]:
    return [header.name for header in template.headers]
