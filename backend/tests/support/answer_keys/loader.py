"""Answer-key discovery, loading, cross-validation and selection (docs/dev-guide.md §9.5.8).

``discover`` lists the key files under the corpus root; ``load`` parses one file with a YAML loader
that resolves only null and bool, rejects duplicate mapping keys, and validates the result against
:class:`support.answer_keys.models.AnswerKey` (DG-AK-30, DG-AK-31; EKC-8). It then cross-validates
the key against its owners (DG-AK-32) and applies the consideration-payable encoding (DG-AK-34) and
the report row keys (DG-AK-35) (EKC-9). Every failure is an :class:`AnswerKeyError` naming the file
and a JSON Pointer (RFC 6901) into the document. ``load_all`` collects the errors of every file into
one ``ExceptionGroup`` and applies the DG-AK-42 selection. ``coverage`` reports the DG-AK-33 corpus
gaps against the register and POLICIES as they read when it runs (EKC-10).

Reference data is read at run time: enumeration literals from the StrEnum mirrors, POL keys and
levels from ``POLICY_PARAMETERS``, REQ ids from docs/03-REQUIREMENTS.md, POL and CHK ids from
docs/accounting/POLICIES.md, and the payload members (§16.3), obligation columns (T-CON-11) and
finding codes (§15.4) from docs/04-DATA_MODEL.md.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml
from erev_api import enums as api_enums
from erev_api.enums import RegistryScope
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine import enums as engine_enums
from erev_engine.currencies import ISO_4217
from pydantic import JsonValue, ValidationError
from pydantic_core import ErrorDetails
from support.answer_keys.models import (
    FAMILY_CODES,
    AnswerKey,
    BalanceAmounts,
    BalanceRow,
    Checkpoint,
    CommandItem,
    ConsiderationPayable,
    Contract,
    ContractBlock,
    ContractLine,
    Estimate,
    EventItem,
    Judgement,
    Modification,
    MoneyAmount,
    PeriodStateItem,
    PolicyValue,
    ReportBlock,
    SubledgerBlock,
)
from support.answer_keys.models import SCHEMA_ID as MODEL_SCHEMA_ID
from support.answer_keys.terms import CHANGE, terms_line_action

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
ANSWER_KEY_ROOT: Final[Path] = REPO_ROOT / "docs" / "accounting" / "answer-keys"
SCHEMA_ID: Final = MODEL_SCHEMA_ID
COVERAGE_DIR: Final = "_coverage"
ROOT_README: Final = "README.md"
REQUIREMENTS_DOC: Final = REPO_ROOT / "docs" / "03-REQUIREMENTS.md"
POLICIES_DOC: Final = REPO_ROOT / "docs" / "accounting" / "POLICIES.md"
DATA_MODEL_DOC: Final = REPO_ROOT / "docs" / "04-DATA_MODEL.md"

_NULL_TAG = "tag:yaml.org,2002:null"
_BOOL_TAG = "tag:yaml.org,2002:bool"

Tokens = Sequence[str | int]


@dataclass(frozen=True, slots=True)
class LoadedKey:
    key: AnswerKey
    path: Path
    sha256: str


class AnswerKeyError(Exception):
    """A corpus file that cannot be discovered, parsed or validated."""

    def __init__(self, path: Path, pointer: str, message: str) -> None:
        super().__init__(f"{path}: {pointer or '/'}: {message}")
        self.path = path
        self.pointer = pointer
        self.message = message


@dataclass(frozen=True, slots=True)
class Finding:
    """One DG-AK-32 violation: a JSON Pointer into the key and a message."""

    pointer: str
    message: str


class KeyYamlLoader(yaml.SafeLoader):
    """DG-AK-31: implicit resolvers for null and bool only; every other scalar is a string."""

    yaml_implicit_resolvers: dict[str | None, list[tuple[str, re.Pattern[str]]]] = {}


KeyYamlLoader.add_implicit_resolver(
    _NULL_TAG, re.compile(r"^(?:~|null|Null|NULL|)$"), ["~", "n", "N", ""]
)
KeyYamlLoader.add_implicit_resolver(
    _BOOL_TAG, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


def escape_pointer_token(token: str | int) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def pointer_of(tokens: Tokens) -> str:
    return "".join(f"/{escape_pointer_token(token)}" for token in tokens)


def _check_duplicate_keys(node: yaml.Node, tokens: list[str | int], path: Path) -> None:
    """Walk the composed node graph so a duplicate key is reported with its full pointer."""
    pending: list[tuple[yaml.Node, list[str | int]]] = [(node, tokens)]
    seen: set[int] = set()
    while pending:
        current, where = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, yaml.MappingNode):
            names: set[str] = set()
            for key_node, value_node in current.value:
                if not isinstance(key_node, yaml.ScalarNode):
                    raise AnswerKeyError(path, pointer_of(where), "mapping keys are scalars")
                name = str(key_node.value)
                if name in names:
                    raise AnswerKeyError(
                        path,
                        pointer_of([*where, name]),
                        f"duplicate mapping key {name!r} (line {key_node.start_mark.line + 1})",
                    )
                names.add(name)
                pending.append((value_node, [*where, name]))
        elif isinstance(current, yaml.SequenceNode):
            pending.extend((item, [*where, index]) for index, item in enumerate(current.value))


def parse_yaml(text: str, *, path: Path) -> object:
    """Parse one YAML document with :class:`KeyYamlLoader` (DG-AK-31)."""
    loader = KeyYamlLoader(text)
    try:
        node = loader.get_single_node()
        if node is None:
            return None
        _check_duplicate_keys(node, [], path)
        return loader.construct_document(node)
    except yaml.YAMLError as error:
        raise AnswerKeyError(path, "", f"invalid YAML: {error}") from error
    finally:
        loader.dispose()


def discover(root: Path = ANSWER_KEY_ROOT) -> list[Path]:
    """Every ``<family>/<id>.yaml`` under ``root``, sorted by path (DG-AK-01, DG-AK-30)."""
    if not root.is_dir():
        raise AnswerKeyError(root, "", "answer-key root is not a directory")
    found: list[Path] = []
    for entry in root.rglob("*"):
        relative = entry.relative_to(root)
        if relative.parts[0] == COVERAGE_DIR:
            continue
        if entry.is_dir():
            if len(relative.parts) > 1:
                raise AnswerKeyError(entry, "", "family directories hold key files only")
            continue
        if len(relative.parts) == 1:
            if relative.name != ROOT_README:
                raise AnswerKeyError(entry, "", "the root holds README.md and family directories")
            continue
        if len(relative.parts) > 2 or entry.suffix != ".yaml":
            raise AnswerKeyError(entry, "", "expected <family>/<id>.yaml")
        found.append(entry)
    return sorted(found)


def _pointer_from_loc(data: object, error: ErrorDetails) -> str:
    """Follow the error location through the raw document, skipping union and validator tags."""
    tokens: list[str | int] = []
    node = data
    loc = error["loc"]
    for index, token in enumerate(loc):
        if isinstance(node, dict) and isinstance(token, str) and token in node:
            tokens.append(token)
            node = node[token]
        elif isinstance(node, list) and isinstance(token, int) and 0 <= token < len(node):
            tokens.append(token)
            node = node[token]
        elif index == len(loc) - 1 and error["type"] == "missing" and isinstance(token, str):
            tokens.append(token)
    return pointer_of(tokens)


def _without_container_echoes(details: list[ErrorDetails]) -> list[ErrorDetails]:
    """Drop `too_short` errors that only echo an invalid item inside the same container."""
    kept = [
        item
        for item in details
        if item["type"] != "too_short"
        or not any(
            other is not item and other["loc"][: len(item["loc"])] == item["loc"]
            for other in details
        )
    ]
    return kept or details


def _summarise(first: tuple[str, str], others: Sequence[tuple[str, str]]) -> str:
    """The first message, then a count and the pointer and message of every other error."""
    if not others:
        return first[1]
    rest = "; ".join(f"{pointer or '/'}: {message}" for pointer, message in others)
    return f"{first[1]} ({len(others)} more: {rest})"


def validate(data: object, *, path: Path) -> AnswerKey:
    """Validate a parsed document; the first error gives the pointer, the message counts all."""
    if not isinstance(data, dict):
        raise AnswerKeyError(path, "", "an answer key is a YAML mapping")
    try:
        return AnswerKey.model_validate(data)
    except ValidationError as error:
        details = [
            (_pointer_from_loc(data, item), item["msg"])
            for item in _without_container_echoes(error.errors(include_url=False))
        ]
        raise AnswerKeyError(path, details[0][0], _summarise(details[0], details[1:])) from error


# Reference data (DG-AK-32)


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


_ENUM_DOCSTRING = re.compile(r"^E-[0-9]+ ``([a-z0-9_]+)``")


@functools.cache
def enum_literals() -> Mapping[str, frozenset[str]]:
    """04 §3 enumeration name → literals, from the StrEnums of ``erev_api`` and ``erev_engine``."""
    found: dict[str, set[str]] = {}
    for module in (api_enums, engine_enums):
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, StrEnum) and value.__doc__:
                match = _ENUM_DOCSTRING.match(value.__doc__)
                if match:
                    found.setdefault(match.group(1), set()).update(item.value for item in value)
    return MappingProxyType({name: frozenset(values) for name, values in found.items()})


@functools.cache
def requirement_ids() -> frozenset[str]:
    """REQ ids of the register rows of docs/03-REQUIREMENTS.md (DG-AK-19)."""
    text = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    return frozenset(re.findall(r"^\| (REQ-[A-Z]+-[0-9]{3}) \|", text, re.MULTILINE))


@functools.cache
def policy_ids() -> frozenset[str]:
    """POL ids of the POLICIES.md §1 rows, retired rows included (DG-AK-20)."""
    text = POLICIES_DOC.read_text(encoding="utf-8")
    return frozenset(re.findall(r"^\| (POL-[0-9]{3}) \|", text, re.MULTILINE))


_CHK_ID = re.compile(r"\b(CHK-[0-9]{3}[a-z]?)\b")


@functools.cache
def chk_ids() -> frozenset[str]:
    """CHK ids named in POLICIES.md (DG-AK-04; the List C ids of DG-AK-33)."""
    return frozenset(_CHK_ID.findall(POLICIES_DOC.read_text(encoding="utf-8")))


@functools.cache
def payload_members() -> Mapping[str, frozenset[str]]:
    """04 §16.3 "Event payloads": event type → the payload member names of its row."""
    text = _between(DATA_MODEL_DOC.read_text(encoding="utf-8"), "**Event payloads**", "### 16.4 ")
    members: dict[str, frozenset[str]] = {}
    for line in text.splitlines():
        match = re.match(r"^\| `([A-Z_]+)` \| (.*?) \| ", line)
        if match:
            cell = match.group(2).replace("`memo_1..3`", "`memo_1`, `memo_2`, `memo_3`")
            members[match.group(1)] = frozenset(re.findall(r"`([a-z][a-z0-9_]*)`", cell))
    return MappingProxyType(members)


def _table_columns(start: str, end: str) -> Mapping[str, str]:
    """Column → type of the 04 table section between two headings."""
    text = _between(DATA_MODEL_DOC.read_text(encoding="utf-8"), start, end)
    rows = re.findall(r"^\| `([a-z0-9_]+)` \| ([^|]*) \|", text, re.MULTILINE)
    return MappingProxyType({name: kind.strip() for name, kind in rows})


@functools.cache
def obligation_columns() -> Mapping[str, str]:
    """04 T-CON-11 ``obligation_version`` column → type (§9.5.6 obligation rows)."""
    return _table_columns("### T-CON-11 `obligation_version`", "### T-CON-12 `estimate`")


@functools.cache
def contract_version_columns() -> Mapping[str, str]:
    """04 T-CON-08 ``contract_version`` column → type (§9.5.6 version blocks; DG-AK-50)."""
    return _table_columns(
        "### T-CON-08 `contract_version`", "### T-CON-09 `contract_version_balance`"
    )


@functools.cache
def balance_columns() -> Mapping[str, str]:
    """04 T-CON-09 ``contract_version_balance`` column → type (DG-KRN-EXP-01 scope; D-97 (8))."""
    return _table_columns("### T-CON-09 `contract_version_balance`", "### T-CON-10 `obligation`")


@functools.cache
def finding_codes() -> frozenset[str]:
    """Finding and exception codes of the 04 §15.4 catalogue tables."""
    text = _between(
        DATA_MODEL_DOC.read_text(encoding="utf-8"),
        "### 15.4 Finding and exception code catalogue",
        "## 16. ",
    )
    return frozenset(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", text, re.MULTILINE))


# D-14a: reserved roles may be mapped but never appear in subledger or journal lines.
RESERVED_ACCOUNT_ROLES: Final = frozenset({"RETAINED_EARNINGS", "FINANCING_OBLIGATION"})
BILLING_CLEARING: Final = "BILLING_CLEARING"
# §9.5.5: handle members a payload may carry beside the 04 §16.3 members.
HANDLE_PAYLOAD_MEMBERS: Final = frozenset(
    {"modification", "estimate", "version_no", "judgement", "obligation_key"}
)
# 04 §16.3 payload members typed Money.
MONEY_PAYLOAD_MEMBERS: Final = frozenset({
    "amount", "refund_amount", "tax_amount", "additional_consideration", "rated_amount",
    "expected_collectible_amount", "fair_value_contract_liability",
})  # fmt: skip
TAX_LINE_MEMBERS: Final = frozenset({"tax_type", "amount", "principal_or_agent"})
TAX_PRINCIPAL_OR_AGENT: Final = frozenset({"PRINCIPAL", "AGENT"})
VERSION_MONEY_MEMBERS: Final = (
    "transaction_price", "fixed_consideration", "vc_constrained_amount", "vc_excluded_amount",
    "expected_returns_amount", "consideration_payable_amount", "financing_adjustment_amount",
    "noncash_consideration_amount", "sales_tax_excluded_amount", "out_of_scope_amount",
    "revenue_cum", "billed_cum", "rpo_amount", "scheduled_amount", "awaiting_trigger_amount",
)  # fmt: skip
# §9.5.6 rev 1.3 (S04-R-02): memo members asserted with their sign, never positive.
NON_POSITIVE_VERSION_MEMBERS: Final = ("expected_returns_amount", "consideration_payable_amount")
ESTIMATE_MONEY_MEMBERS: Final = (
    "unconstrained_amount", "most_conservative_amount", "constrained_amount",
    "expected_total_amount",
)  # fmt: skip
# 04 T-CON-06 questionnaire members per obligation key.
MODIFICATION_QUESTIONNAIRE_MEMBERS: Final = frozenset(
    {"added_goods_distinct", "priced_at_ssp", "remaining_goods_distinct_from_transferred"}
)
PRICE_CHANGE_SETTLEMENTS: Final = frozenset({"FUTURE_PRICING", "CREDIT_OR_REFUND"})

# 04 T-CON-13 "Parameter schemas by estimate kind": member → type, and the required members.
ESTIMATE_PARAMETER_SCHEMAS: Final[Mapping[str, tuple[Mapping[str, str], frozenset[str]]]] = {
    "RETURN_RATE": (
        {"carrying_cost_per_unit": "decimal", "recovery_cost_per_unit": "decimal",
         "window_end_date": "date"},
        frozenset({"carrying_cost_per_unit", "recovery_cost_per_unit", "window_end_date"}),
    ),
    "VARIABLE_CONSIDERATION": (
        {"no_change_attestation": "bool", "refund_liability_target": "decimal"}, frozenset()
    ),
    "ROYALTY_ACCRUAL": (
        {"usage_period_start_date": "date", "usage_period_end_date": "date"},
        frozenset({"usage_period_start_date", "usage_period_end_date"}),
    ),
    "BREAKAGE": ({}, frozenset()),
    "EAC": ({"uninstalled_materials_cost": "decimal"}, frozenset()),
    "EXERCISE_LIKELIHOOD": ({}, frozenset()),
    "IMPLICIT_PRICE_CONCESSION": ({}, frozenset()),
    "RENEWAL_EXPECTATION": ({}, frozenset()),
    "EXPECTED_PURCHASES": ({}, frozenset()),
    "SHARE_BASED_CONSIDERATION": (
        {"grant_date": "date", "grant_date_fair_value": "decimal", "vesting_probable": "bool",
         "expected_forfeiture_ratio": "decimal"},
        frozenset({"grant_date", "grant_date_fair_value", "vesting_probable"}),
    ),
}  # fmt: skip

# 04 T-CON-19 "Questionnaire schemas by topic": member → type, and the required members. Types:
# bool, date, decimal; handles obligation, obligation-or-contract ("" = the contract), estimate,
# product, bundle; `enum:<04 §3 name>`; `one-of:<literal>|…`.
QUESTIONNAIRE_SCHEMAS: Final[Mapping[str, tuple[Mapping[str, str], frozenset[str]]]] = {
    "COLLECTIBILITY": ({}, frozenset()),
    "NOT_A_CONTRACT": (
        {"consideration_nonrefundable": "bool", "event_c_met_on": "date"},
        frozenset({"consideration_nonrefundable"}),
    ),
    "CONTRACT_TERM": (
        {"enforceable_end_date": "date", "termination_penalty_substantive": "bool"},
        frozenset({"enforceable_end_date", "termination_penalty_substantive"}),
    ),
    "COMBINATION": ({}, frozenset()),
    "POB_DISTINCT_OVERRIDE": (
        {"obligation_key": "obligation", "distinctness": "enum:distinctness",
         "integrates_into_obligation_key": "obligation"},
        frozenset({"obligation_key", "distinctness"}),
    ),
    "SERIES_CLASSIFICATION": (
        {"obligation_key": "obligation",
         "series_increment_unit": "one-of:day|month|transaction|unit"},
        frozenset({"obligation_key", "series_increment_unit"}),
    ),
    "PRINCIPAL_AGENT": (
        {"product_code": "product", "obligation_key": "obligation",
         "conclusion": "enum:principal_agent",
         "gross_to_net_basis": "one-of:COMMISSION_RATE|FIXED_FEE|SUPPLIER_COST",
         "rate": "decimal", "amount": "decimal"},
        frozenset({"conclusion"}),
    ),
    "LICENCE_NATURE": (
        {"obligation_key": "obligation", "nature": "enum:licence_nature",
         "activities_significantly_affect_ip": "bool",
         "functionality_expected_to_change_substantively": "bool",
         "customer_required_to_use_updated_ip": "bool"},
        frozenset({"obligation_key", "nature"}),
    ),
    "WARRANTY_TYPE": (
        {"obligation_key": "obligation", "warranty_type": "enum:warranty_type"},
        frozenset({"obligation_key", "warranty_type"}),
    ),
    "SFC_ASSESSMENT": (
        {"obligation_key": "obligation-or-contract", "significant": "bool",
         "exception_32_17": "one-of:A|B|C|NONE"},
        frozenset({"obligation_key", "significant", "exception_32_17"}),
    ),
    "CONSTRAINT": ({"estimate_key": "estimate", "remote": "bool"},
                   frozenset({"estimate_key", "remote"})),
    "REPURCHASE_CLASSIFICATION": (
        {"obligation_key": "obligation", "outcome": "one-of:FINANCING|LEASE|RIGHT_OF_RETURN|SALE"},
        frozenset({"obligation_key", "outcome"}),
    ),
    "BILL_AND_HOLD": (
        {"obligation_key": "obligation", "reason_substantive": "bool",
         "identified_as_customer_product": "bool", "ready_for_physical_transfer": "bool",
         "cannot_use_or_direct_to_another_customer": "bool"},
        frozenset({"obligation_key", "reason_substantive", "identified_as_customer_product",
                   "ready_for_physical_transfer", "cannot_use_or_direct_to_another_customer"}),
    ),
    "OTHER": (
        {"pol_044_override": "bool", "claim_enforceable": "bool", "returns_immaterial": "bool",
         "estimate_key": "estimate", "obligation_key": "obligation",
         "discount_exception_bundle": "bundle"},
        frozenset(),
    ),
    "MODIFICATION_TREATMENT_OVERRIDE": ({}, frozenset()),
    "SSP_OVERRIDE": ({}, frozenset()),
    "ESTIMATE_VS_ERROR": ({}, frozenset()),
}  # fmt: skip

# §9.5.6 "Report cell keys": column keys per report code; `rpo` columns follow the POL-201 bands.
REPORT_COLUMNS: Final[Mapping[str, frozenset[str]]] = {
    "contract_balance_rollforward": frozenset({
        "opening_contract_liability", "billings", "revenue_from_opening_liability",
        "revenue_from_period_billings", "fx", "closing_contract_liability",
    }),
    "revenue_from_opening_liability": frozenset(
        {"opening_contract_liability", "revenue_recognized", "revenue_from_opening_liability"}
    ),
    "disaggregation": frozenset({"revenue"}),
}  # fmt: skip
RPO_BANDS_KEY: Final = "rpo.time_bands"
RELEASE_BASIS_KEY: Final = "cpc.incentive_asset_release_basis"

_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_UNSIGNED_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# DG-AK-52: decimal places of exact values and of rates.
EXACT_PLACES: Final = 18
RATE_PLACES: Final = 12
_SUBJECT = re.compile(r"ssp:([^:]+):(.+):([^:]+)")


def _money_parts(value: object, currency: str | None) -> tuple[object, str | None, bool]:
    """(amount, currency, nested): a money field is `{amount, currency}` or a string (§9.5.4)."""
    if isinstance(value, MoneyAmount):
        return value.amount, value.currency, True
    if isinstance(value, dict):
        return value.get("amount"), value.get("currency"), True
    return value, currency, False


def _removes_every_unit_priced(line: ContractLine) -> bool:
    """D-97 (1c): a terms-form CHANGE line with quantity 0 removes every unit, so it prices 0.
    Malformed or non-finite numbers are left to the conversion, as before the rule."""
    amount, _, _ = _money_parts(line.total_price, None)
    if not isinstance(amount, str):
        return False  # DG-AK-03 reports a money field that is not a decimal string
    try:
        quantity, price = Decimal(line.quantity), Decimal(amount)
    except InvalidOperation:
        return False  # the conversion reports the malformed number (pre-existing boundary)
    if not (quantity.is_finite() and price.is_finite()):
        return False
    return quantity == 0 and price != 0


def _in_force_before(contract: Contract) -> dict[int, frozenset[str]]:
    """Per modification index, the obligation keys in force at its date as the runner folds them
    (``runners._terms_conversions``): the booked lines, then the lines of the earlier modifications
    in (effective date, key order); a malformed date sorts last."""
    keys = {line.obligation_key for line in contract.lines}
    modifications = list(enumerate(contract.modifications or ()))

    def order(pair: tuple[int, Modification]) -> tuple[date, int]:
        try:
            return date.fromisoformat(pair[1].effective_date), pair[0]
        except (TypeError, ValueError):
            return date.max, pair[0]

    before: dict[int, frozenset[str]] = {}
    for index, modification in sorted(modifications, key=order):
        before[index] = frozenset(keys)
        keys.update(line.obligation_key for line in modification.lines)
    return before


def _terms_actions(modification: Modification, in_force: frozenset[str]) -> tuple[str, ...] | None:
    """The conversion's action of every terms-form line of ``modification`` (``terms_line_action``),
    or None when the lines are not terms-form or a date is malformed (the conversion reports it)."""
    lines = [line for line in modification.lines if isinstance(line, ContractLine)]
    if not lines or len(lines) != len(modification.lines):
        return None
    try:
        effective = date.fromisoformat(modification.effective_date)
        return tuple(
            terms_line_action(
                modification.kind,
                line,
                in_force=line.obligation_key in in_force,
                effective_date=effective,
            )
            for line in lines
        )
    except (TypeError, ValueError):
        return None


def _first_version(estimate: Estimate) -> Estimate | None:
    return estimate if estimate.versions else None


def maps_to_consideration_payable(estimate: Estimate) -> bool:
    """DG-AK-34: an `EXPECTED_PURCHASES` element whose version 1 carries `unconstrained_amount`."""
    return (
        estimate.estimate_kind == "EXPECTED_PURCHASES"
        and bool(estimate.versions)
        and estimate.versions[0].unconstrained_amount is not None
    )


def rpo_bands(key: AnswerKey, parameters: Mapping[str, JsonValue]) -> list[int]:
    """POL-201 bands: report `time_bands`, else the tenant value, else the registry default."""
    bands: object = parameters.get("time_bands")
    if bands is None:
        bands = key.world.policies.tenant.get(RPO_BANDS_KEY)
    if bands is None:
        bands = POLICY_PARAMETERS[RPO_BANDS_KEY].default_asc606
    if not isinstance(bands, list | tuple) or not bands:
        raise ValueError(f"time_bands {bands!r} is not a list of month counts (POL-201)")
    result: list[int] = []
    for band in bands:
        if isinstance(band, bool) or not re.fullmatch(r"[0-9]+", str(band)):
            raise ValueError(f"time band {band!r} is not a month count (POL-201)")
        result.append(int(band))
    if result != sorted(set(result)) or result[0] < 1:
        raise ValueError(f"time bands {result} are not ascending positive month counts (POL-201)")
    return result


def report_columns(key: AnswerKey, report: ReportBlock) -> frozenset[str] | None:
    """Column keys of the "Report cell keys" table; None for codes the table leaves open."""
    if report.report_code == "rpo":
        bands = rpo_bands(key, report.parameters)
        between = {
            f"months_{low + 1}_to_{high}" for low, high in zip(bands, bands[1:], strict=False)
        }
        return frozenset(
            {f"within_{bands[0]}_months", *between, f"after_{bands[-1]}_months", "total"}
        )
    return REPORT_COLUMNS.get(report.report_code)


def report_row_key(key: AnswerKey, report: ReportBlock, row_key: str) -> str:
    """DG-AK-35: the normalised row key of a report cell; ValueError when it cannot be resolved."""
    if ":" in row_key:
        return row_key
    if row_key == "TOTAL":
        currencies = sorted({contract.transaction_currency for contract in key.contracts})
        if len(currencies) != 1:
            raise ValueError(
                f"TOTAL with transaction currencies {', '.join(currencies)}; "
                "write TOTAL:<ISO code> (DG-AK-35)"
            )
        return f"TOTAL:{currencies[0]}"
    is_contract = any(contract.external_id == row_key for contract in key.contracts)
    is_entity = any(entity.code == row_key for entity in key.world.entities)
    if is_contract and is_entity:
        raise ValueError(
            f"row key {row_key!r} is both a contract handle and an entity code (DG-AK-35)"
        )
    if is_contract:
        return f"contract:{row_key}"
    if is_entity:
        if report.parameters.get("entity_codes") != [row_key]:
            raise ValueError(
                f"entity row key {row_key!r} needs parameters.entity_codes [{row_key}] (DG-AK-35)"
            )
        return f"entity:{row_key}"
    raise ValueError(
        f"row key {row_key!r} is neither a contract handle nor an entity code (DG-AK-35)"
    )


class _CrossValidator:
    """Collects the DG-AK-32 findings of one key, in document order."""

    def __init__(self, key: AnswerKey, path: Path) -> None:
        self.key = key
        self.path = path
        self.findings: list[Finding] = []
        world = key.world
        self.entities = {entity.code: entity for entity in world.entities}
        self.accounts = {account.code for account in world.gl_accounts}
        self.customers = {customer.code for customer in world.customers}
        self.templates = {template.code for template in world.pob_templates}
        # D-93 (4): a series product's SSP entry declares its E-49 basis (fail closed; dev-guide
        # §9.5.3 `ssp_books`).
        self.series_templates = {
            template.code for template in world.pob_templates if template.distinctness == "series"
        }
        self.products = {product.code: product for product in world.products}
        self.contracts = {contract.external_id: contract for contract in key.contracts}
        self.groups = {c.combination_group for c in key.contracts if c.combination_group}
        self.obligations = {c.external_id: self._obligation_keys(c) for c in key.contracts}
        self.ssp_labels = {
            (book.code, version.legacy_version_label or version.effective_from_date)
            for book in world.ssp_books
            for version in book.versions
        }

    def _obligation_keys(self, contract: Contract) -> frozenset[str]:
        """Booked lines, modification lines and `new_lines` of exercised material rights."""
        keys = {line.obligation_key for line in contract.lines}
        for modification in contract.modifications or ():
            keys.update(line.obligation_key for line in modification.lines)
        for item in self.key.timeline:
            if isinstance(item, EventItem) and item.contract == contract.external_id:
                new_lines = item.payload.get("new_lines")
                for line in new_lines if isinstance(new_lines, list) else ():
                    if isinstance(line, dict) and isinstance(line.get("obligation_key"), str):
                        keys.add(str(line["obligation_key"]))
        return frozenset(keys)

    # helpers

    def add(self, tokens: Tokens, message: str) -> None:
        self.findings.append(Finding(pointer_of(tokens), message))

    def literal(self, tokens: Tokens, value: object, enumeration: str) -> None:
        if value is not None and value not in enum_literals()[enumeration]:
            self.add(tokens, f"{value!r} is not a `{enumeration}` literal (04 §3)")

    def handle(self, tokens: Tokens, value: object, known: Iterable[object], what: str) -> None:
        if value is not None and value not in known:
            self.add(tokens, f"{what} {value!r} does not resolve (DG-AK-32)")

    def currency(self, tokens: Tokens, code: object) -> None:
        if code is not None and code not in ISO_4217:
            self.add(tokens, f"{code!r} is not an ISO 4217 currency code")

    def money(self, tokens: Tokens, value: object, currency: str | None) -> None:
        """DG-AK-51: a decimal string with exactly the minor-unit places of its currency."""
        if value is None:
            return
        amount, code, nested = _money_parts(value, currency)
        at = [*tokens, "amount"] if nested else list(tokens)
        if nested:
            self.currency([*tokens, "currency"], code)
        if not isinstance(amount, str) or not _DECIMAL.fullmatch(amount):
            self.add(at, f"money {amount!r} is not a decimal string (DG-AK-03)")
            return
        spec = ISO_4217.get(code) if isinstance(code, str) else None
        if spec is None:
            return
        places = len(amount.partition(".")[2])
        if places != spec.minor_unit:
            self.add(
                at,
                f"{amount} has {places} decimal places; {code} has {spec.minor_unit} (DG-AK-51)",
            )

    def places(self, tokens: Tokens, value: object, limit: int) -> None:
        """DG-AK-52: an exact value has at most 18 decimal places, a rate at most 12."""
        if value is None:
            return
        if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
            self.add(tokens, f"{value!r} is not a decimal string (DG-AK-03)")
            return
        places = len(value.partition(".")[2])
        if places > limit:
            what = "a rate" if limit == RATE_PLACES else "an exact value"
            self.add(
                tokens,
                f"{value} has {places} decimal places; {what} has at most {limit} (DG-AK-52)",
            )

    def role(self, tokens: Tokens, role: str) -> None:
        """An account-role key: an E-01 literal, or `BILLING_CLEARING:<clearing purpose>`."""
        base, _, purpose = role.partition(":")
        self.literal(tokens, base, "account_role")
        if purpose and (
            base != BILLING_CLEARING or purpose not in enum_literals()["clearing_purpose"]
        ):
            self.add(tokens, f"role key {role!r} names a clearing purpose outside BILLING_CLEARING")

    def clearing_purpose(self, tokens: Tokens, role: str, purpose: str | None) -> None:
        """D-14a: `clearing_purpose` appears exactly on `BILLING_CLEARING` rows."""
        at = [*tokens, "clearing_purpose"]
        if role == BILLING_CLEARING and purpose is None:
            self.add(at, "a BILLING_CLEARING row carries clearing_purpose (D-14a)")
        elif role != BILLING_CLEARING and purpose is not None:
            self.add(
                at, f"clearing_purpose appears only on BILLING_CLEARING rows, not {role} (D-14a)"
            )
        else:
            self.literal(at, purpose, "clearing_purpose")

    def policy_value(
        self,
        key_tokens: Tokens,
        value_tokens: Tokens,
        name: str,
        value: PolicyValue,
        scope: RegistryScope,
    ) -> None:
        """DG-AK-32: the key exists in POLICY_PARAMETERS and the level is allowed."""
        spec = POLICY_PARAMETERS.get(name)
        if spec is None:
            self.add(key_tokens, f"unknown policy key {name!r} (POLICIES §1)")
            return
        if scope not in spec.allowed_levels:
            levels = ", ".join(sorted(level.value for level in spec.allowed_levels))
            self.add(
                key_tokens,
                f"{name} ({spec.pol_id}) is set at level {scope.value}; allowed {levels}",
            )
        options = spec.value_schema.get("enum")
        literal = value.get("option") if isinstance(value, dict) else value
        if isinstance(options, list) and isinstance(literal, str) and literal not in options:
            self.add(value_tokens, f"{literal!r} is not an option of {name} (POLICIES §1)")

    def policy_values(
        self, tokens: Tokens, values: Mapping[str, PolicyValue] | None, scope: RegistryScope
    ) -> None:
        for name, value in (values or {}).items():
            self.policy_value([*tokens, name], [*tokens, name], name, value, scope)

    # document sections

    def run(self) -> list[Finding]:
        self.header()
        self.world()
        for index, contract in enumerate(self.key.contracts):
            self.contract(["contracts", index], contract)
        self.timeline()
        for index, checkpoint in enumerate(self.key.checkpoints):
            self.checkpoint(["checkpoints", index], checkpoint)
        return self.findings

    def header(self) -> None:
        key = self.key
        family = key.families[0]
        if self.path.parent.name != family.lower():
            self.add(
                ["families", 0],
                f"families[0] {family} does not match directory {self.path.parent.name!r}"
                " (DG-AK-01)",
            )
        if not key.id.startswith(f"{family}-"):
            self.add(["id"], f"the id prefix is not families[0] {family} (DG-AK-04)")
        elif self.path.stem != key.id:
            self.add(["id"], f"the file name {self.path.name!r} does not equal the id (DG-AK-04)")
        for index, requirement in enumerate(key.requirements):
            self.handle(["requirements", index], requirement, requirement_ids(), "requirement")
        for index, policy in enumerate(key.policy_refs):
            self.handle(["policy_refs", index], policy, policy_ids(), "policy")
        for index, chk in enumerate(key.derived_from.chk):
            if chk not in chk_ids():
                self.add(["derived_from", "chk", index], f"{chk} is not defined in POLICIES.md")
            elif chk.upper() not in key.id.upper():
                self.add(
                    ["derived_from", "chk", index], f"{chk} is not contained in the id (DG-AK-04)"
                )
        for index, book in enumerate(key.books):
            self.literal(["books", index], book, "book_code")

    def world(self) -> None:
        world = self.key.world
        at: list[str | int] = ["world"]
        self.currency([*at, "tenant", "reporting_currency"], world.tenant.reporting_currency)
        for index, code in enumerate(world.currencies):
            self.currency([*at, "currencies", index], code)
        for index, entity in enumerate(world.entities):
            where = [*at, "entities", index]
            self.currency([*where, "functional_currency"], entity.functional_currency)
            self.literal(
                [*where, "calendar", "pattern"], entity.calendar.pattern, "calendar_pattern"
            )
            for book_index, book in enumerate(entity.books):
                self.literal([*where, "books", book_index], book, "book_code")
            self.handle([*where, "parent_code"], entity.parent_code, self.entities, "entity")
        for index, state in enumerate(world.period_states):
            where = [*at, "period_states", index]
            self.handle([*where, "entity"], state.entity, self.entities, "entity")
            self.literal([*where, "book"], state.book, "book_code")
            self.literal([*where, "state"], state.state, "period_state")
        for index, account in enumerate(world.gl_accounts):
            self.literal(
                [*at, "gl_accounts", index, "account_type"], account.account_type, "account_type"
            )
        for index, row in enumerate(world.account_mapping):
            where = [*at, "account_mapping", index]
            self.literal([*where, "account_role"], row.account_role, "account_role")
            self.clearing_purpose(where, row.account_role, row.clearing_purpose)
            self.handle([*where, "account"], row.account, self.accounts, "account")
            self.handle([*where, "entity"], row.entity, self.entities, "entity")
            self.literal([*where, "book_code"], row.book_code, "book_code")
            self.handle([*where, "product"], row.product, self.products, "product")
        for index, template in enumerate(world.pob_templates):
            where = [*at, "pob_templates", index]
            for member, enumeration in (
                ("obligation_kind", "obligation_kind"),
                ("distinctness", "distinctness"),
                ("satisfaction_pattern", "satisfaction_pattern"),
                ("over_time_criterion", "over_time_criterion"),
                ("recognition_method", "recognition_method"),
                ("principal_agent", "principal_agent"),
                ("warranty_type", "warranty_type"),
                ("licence_nature", "licence_nature"),
            ):
                self.literal([*where, member], getattr(template, member), enumeration)
            for role in template.account_role_overrides or {}:
                self.role([*where, "account_role_overrides", role], role)
            self.policy_values(
                [*where, "policy_values"], template.policy_values, RegistryScope.PRODUCT
            )
        for index, product in enumerate(world.products):
            where = [*at, "products", index]
            self.handle([*where, "pob_template"], product.pob_template, self.templates, "template")
            self.literal([*where, "principal_agent"], product.principal_agent, "principal_agent")
            self.literal(
                [*where, "distinctness_default"], product.distinctness_default, "distinctness"
            )
            for component_index, component in enumerate(product.components or ()):
                self.handle(
                    [*where, "components", component_index, "product"],
                    component.product,
                    self.products,
                    "product",
                )
            self.policy_values(
                [*where, "policy_values"], product.policy_values, RegistryScope.PRODUCT
            )
        # D-97 (3): the E-125 quantity_unit declared per (book, product), for the agreement check.
        units: dict[tuple[str, str], tuple[str, list[str | int]]] = {}
        for index, book in enumerate(world.ssp_books):
            where = [*at, "ssp_books", index]
            self.handle([*where, "entity"], book.entity, self.entities, "entity")
            self.currency([*where, "currency"], book.currency)
            for version_index, version in enumerate(book.versions):
                for entry_index, entry in enumerate(version.entries):
                    entry_at = [*where, "versions", version_index, "entries", entry_index]
                    self.handle([*entry_at, "product"], entry.product, self.products, "product")
                    self.currency([*entry_at, "currency"], entry.currency)
                    self.literal([*entry_at, "method"], entry.method, "ssp_method")
                    self.literal([*entry_at, "distinctness"], entry.distinctness, "distinctness")
                    self.literal([*entry_at, "value_basis"], entry.value_basis, "ssp_value_basis")
                    self.literal(
                        [*entry_at, "quantity_unit"], entry.quantity_unit, "ssp_quantity_unit"
                    )
                    if entry.value_basis == "PER_INCREMENT" and entry.quantity_unit is None:
                        # D-97 (3): what the line's quantity counts is declared, never inferred.
                        self.add(
                            [*entry_at, "quantity_unit"],
                            f"the PER_INCREMENT SSP entry of product {entry.product!r} declares no "
                            "`quantity_unit` (E-125: SERVICE_UNITS or INCREMENTS; D-97 (3) fails "
                            "closed)",
                        )
                    elif entry.value_basis != "PER_INCREMENT" and entry.quantity_unit is not None:
                        self.add(
                            [*entry_at, "quantity_unit"],
                            f"`quantity_unit` is meaningful for a PER_INCREMENT entry only, not "
                            f"{entry.value_basis or 'AMOUNT'!r} (D-97 (3))",
                        )
                    if entry.quantity_unit is not None:
                        unit_key = (book.code, entry.product)
                        seen = units.setdefault(unit_key, (entry.quantity_unit, entry_at))
                        if seen[0] != entry.quantity_unit:
                            self.add(
                                [*entry_at, "quantity_unit"],
                                f"quantity_unit {entry.quantity_unit!r} disagrees with "
                                f"{pointer_of(seen[1])} ({seen[0]!r}) for product "
                                f"{entry.product!r} in SSP book {book.code!r} (D-97 (3))",
                            )
                    product = self.products.get(entry.product)
                    if (
                        entry.value_basis is None
                        and product is not None
                        and product.pob_template in self.series_templates
                    ):
                        # D-93 (4) / ENGINE_SPEC S06-R-11 series row: an omitted basis is not an
                        # AMOUNT declaration; the corpus entries are annotated (lane ENG-C1b).
                        self.add(
                            [*entry_at, "value_basis"],
                            f"the SSP entry of series product {entry.product!r} declares no "
                            "`value_basis` (E-49: AMOUNT, PER_INCREMENT or PER_BOOKED_TERM; "
                            "D-93 (4) fails closed)",
                        )
                    if entry.population is not None and self.key.runner != "engine":
                        self.add(
                            [*entry_at, "population"], "population appears only with runner engine"
                        )
        for index, rate_set in enumerate(world.fx_rate_sets):
            self.literal([*at, "fx_rate_sets", index, "rate_type"], rate_set.rate_type, "rate_type")
            for rate_index, rate in enumerate(rate_set.rates):
                where = [*at, "fx_rate_sets", index, "rates", rate_index, "rate"]
                self.places(where, rate.rate, RATE_PLACES)
        for index, rule_set in enumerate(world.rule_sets):
            self.literal([*at, "rule_sets", index, "kind"], rule_set.kind, "rule_set_kind")
        for index, portfolio in enumerate(world.portfolios):
            where = [*at, "portfolios", index]
            for member_index, member in enumerate(portfolio.members):
                self.handle([*where, "members", member_index], member, self.contracts, "contract")
            self.estimates([*where, "estimates"], portfolio.estimates, None, None)
        policies = world.policies
        self.policy_values([*at, "policies", "tenant"], policies.tenant, RegistryScope.TENANT)
        for code, values in policies.entities.items():
            where = [*at, "policies", "entities", code]
            self.handle(where, code, self.entities, "entity")
            self.policy_values(where, values, RegistryScope.ENTITY)
        for code, values in policies.books.items():
            where = [*at, "policies", "books", code]
            self.literal(where, code, "book_code")
            self.policy_values(where, values, RegistryScope.BOOK)

    def contract(self, at: list[str | int], contract: Contract) -> None:
        handle = contract.external_id
        currency = contract.transaction_currency
        obligations = self.obligations[handle]
        if sum(1 for other in self.key.contracts if other.external_id == handle) > 1:
            self.add([*at, "external_id"], f"contract handle {handle!r} is not unique")
        self.handle([*at, "customer"], contract.customer, self.customers, "customer")
        self.handle(
            [*at, "contracting_entity"], contract.contracting_entity, self.entities, "entity"
        )
        if currency not in self.key.world.currencies:
            self.add([*at, "transaction_currency"], f"{currency} is not listed in world.currencies")
        self.handle([*at, "renewal_of"], contract.renewal_of, self.contracts, "contract")
        for index, line in enumerate(contract.lines):
            where = [*at, "lines", index]
            self.handle([*where, "product_code"], line.product_code, self.products, "product")
            self.handle(
                [*where, "performing_entity_code"],
                line.performing_entity_code,
                self.entities,
                "entity",
            )
            self.literal([*where, "scope_flag"], line.scope_flag, "scope_flag")
            self.money([*where, "total_price"], line.total_price, currency)
            self.money([*where, "out_of_scope_amount"], line.out_of_scope_amount, currency)
            for role, account in (line.account_overrides or {}).items():
                self.role([*where, "account_overrides", role], role)
                self.handle([*where, "account_overrides", role], account, self.accounts, "account")
        for index, override in enumerate(contract.policy_overrides or ()):
            where = [*at, "policy_overrides", index]
            scope = RegistryScope.OBLIGATION if override.obligation_key else RegistryScope.CONTRACT
            self.policy_value(
                [*where, "policy_key"],
                [*where, "value"],
                override.policy_key,
                override.value,
                scope,
            )
            self.handle(
                [*where, "obligation_key"], override.obligation_key, obligations, "obligation"
            )
        for index, judgement in enumerate(contract.judgements or ()):
            self.judgement([*at, "judgements", index], judgement, contract)
        dates = [point.date for point in contract.payment_schedule or ()]
        if dates != sorted(dates):
            self.add([*at, "payment_schedule"], "payment_schedule dates are not ascending (§9.5.4)")
        for index, point in enumerate(contract.payment_schedule or ()):
            self.money([*at, "payment_schedule", index, "amount"], point.amount, currency)
        for index, payable in enumerate(contract.consideration_payable or ()):
            where = [*at, "consideration_payable", index]
            self.money([*where, "amount"], payable.amount, currency)
            self.money(
                [*where, "distinct_good_fair_value"], payable.distinct_good_fair_value, currency
            )
            self.money([*where, "committed_purchases"], payable.committed_purchases, currency)
            for key_index, obligation in enumerate(payable.related_obligation_keys):
                self.handle(
                    [*where, "related_obligation_keys", key_index],
                    obligation,
                    obligations,
                    "obligation",
                )
        if contract.consideration_payable and any(
            maps_to_consideration_payable(estimate) for estimate in contract.estimates or ()
        ):
            self.add(
                [*at, "consideration_payable"],
                "a contract with consideration_payable has an EXPECTED_PURCHASES element that "
                "DG-AK-34 would map; use one encoding",
            )
        self.estimates([*at, "estimates"], contract.estimates, currency, contract)
        estimate_codes = {estimate.element_code for estimate in contract.estimates or ()}
        for index, right in enumerate(contract.material_rights or ()):
            where = [*at, "material_rights", index]
            self.handle([*where, "obligation_key"], right.obligation_key, obligations, "obligation")
            self.literal([*where, "option_type"], right.option_type, "option_type")
            self.handle(
                [*where, "likelihood_estimate"],
                right.likelihood_estimate,
                estimate_codes,
                "estimate",
            )
            self.money(
                [*where, "expected_purchase_amount"], right.expected_purchase_amount, currency
            )
        in_force_before = _in_force_before(contract)
        for index, modification in enumerate(contract.modifications or ()):
            where = [*at, "modifications", index]
            actions = _terms_actions(modification, in_force_before[index])
            self.literal([*where, "kind"], modification.kind, "modification_kind")
            self.literal(
                [*where, "template_mode"], modification.template_mode, "modification_template_mode"
            )
            forms = {"action" in line.model_fields_set for line in modification.lines}
            if len(forms) > 1:
                self.add(
                    [*where, "lines"], "modification lines mix the delta and terms forms (§9.5.4)"
                )
            for line_index, line in enumerate(modification.lines):
                self.handle(
                    [*where, "lines", line_index, "product_code"],
                    line.product_code,
                    self.products,
                    "product",
                )
                if (
                    isinstance(line, ContractLine)
                    and actions is not None
                    and actions[line_index] == CHANGE
                    and _removes_every_unit_priced(line)
                ):
                    self.add(
                        [*where, "lines", line_index, "quantity"],
                        "a terms-form CHANGE line with quantity 0 carries a non-zero total_price; "
                        "a removal of every unit prices 0 (D-97 (1c))",
                    )
            for obligation, answers in (modification.questionnaire or {}).items():
                q_at = [*where, "questionnaire", obligation]
                self.handle(q_at, obligation, obligations, "obligation")
                for member, answer in answers.items():
                    if member == "price_change_settlement":
                        if answer not in PRICE_CHANGE_SETTLEMENTS:
                            self.add(
                                [*q_at, member], f"{answer!r} is not a price_change_settlement"
                            )
                    elif member not in MODIFICATION_QUESTIONNAIRE_MEMBERS:
                        self.add(
                            [*q_at, member], f"04 T-CON-06 lists no questionnaire member {member!r}"
                        )
                    elif not isinstance(answer, bool):
                        self.add([*q_at, member], f"{member} is a boolean")
            for obligation, treatment in (modification.chosen_treatments or {}).items():
                self.literal(
                    [*where, "chosen_treatments", obligation], treatment, "modification_treatment"
                )

    def estimates(
        self,
        at: list[str | int],
        estimates: Sequence[Estimate] | None,
        currency: str | None,
        contract: Contract | None,
    ) -> None:
        obligations = self.obligations[contract.external_id] if contract is not None else None
        for index, estimate in enumerate(estimates or ()):
            where = [*at, index]
            self.literal([*where, "estimate_kind"], estimate.estimate_kind, "estimate_kind")
            self.literal([*where, "method"], estimate.method, "estimate_method")
            if obligations is not None:
                self.handle(
                    [*where, "obligation_key"], estimate.obligation_key, obligations, "obligation"
                )
                for key_index, obligation in enumerate(estimate.target_obligation_keys or ()):
                    self.handle(
                        [*where, "target_obligation_keys", key_index],
                        obligation,
                        obligations,
                        "obligation",
                    )
            mapped = (
                contract is not None
                and not contract.consideration_payable
                and maps_to_consideration_payable(estimate)
            )
            first = estimate.versions[0]
            for version_index, version in enumerate(estimate.versions):
                version_at = [*where, "versions", version_index]
                self.currency([*version_at, "currency"], version.currency)
                for member in ESTIMATE_MONEY_MEMBERS:
                    self.money(
                        [*version_at, member],
                        getattr(version, member),
                        version.currency or currency,
                    )
                self.parameters(version_at, estimate.estimate_kind, version.parameters)
                if version.scenarios:
                    probabilities = [scenario.probability for scenario in version.scenarios]
                    if not all(_UNSIGNED_DECIMAL.fullmatch(value) for value in probabilities):
                        self.add(
                            [*version_at, "scenarios"], "scenario probabilities are decimal strings"
                        )
                    elif (total := sum(map(Decimal, probabilities), Decimal(0))) != 1:
                        self.add(
                            [*version_at, "scenarios"],
                            f"scenario probabilities sum to {total}, not 1",
                        )
                if mapped and version_index > 0:
                    for member in ("unconstrained_amount", "constrained_amount"):
                        if getattr(version, member) != getattr(first, member):
                            self.add(
                                [*version_at, member],
                                f"a later EXPECTED_PURCHASES version changes {member} (DG-AK-34)",
                            )

    def parameters(
        self, at: list[str | int], kind: str, parameters: Mapping[str, object] | None
    ) -> None:
        """04 T-CON-13: the parameter members of the estimate kind, typed, with required members."""
        schema = ESTIMATE_PARAMETER_SCHEMAS.get(kind)
        if schema is None:
            return
        members, required = schema
        where = [*at, "parameters"]
        for name, value in (parameters or {}).items():
            member_type = members.get(name)
            if member_type is None:
                self.add([*where, name], f"{kind} parameters have no member {name!r} (04 T-CON-13)")
            elif not _typed(member_type, value):
                self.add([*where, name], f"{kind} parameter {name} is not a {member_type}")
        missing = sorted(required - set(parameters or {}))
        if missing:
            self.add(where, f"{kind} parameters require {', '.join(missing)} (04 T-CON-13)")

    def judgement(self, at: list[str | int], judgement: Judgement, contract: Contract) -> None:
        obligations = self.obligations[contract.external_id]
        topic = judgement.topic
        self.literal([*at, "topic"], topic, "judgement_topic")
        if judgement.book_code is not None and judgement.book_code not in self.key.books:
            self.add([*at, "book_code"], f"book_code {judgement.book_code} is not one of books")
        self.handle(
            [*at, "subject_obligation_key"],
            judgement.subject_obligation_key,
            obligations,
            "obligation",
        )
        schema = QUESTIONNAIRE_SCHEMAS.get(topic)
        if schema is None:
            return
        members, required = schema
        where = [*at, "questionnaire"]
        questionnaire = judgement.questionnaire
        if questionnaire is None:
            if required:
                self.add(
                    where,
                    f"topic {topic} requires a questionnaire with {', '.join(sorted(required))} "
                    "(04 T-CON-19)",
                )
            return
        estimates = {estimate.element_code for estimate in contract.estimates or ()}
        for name, value in questionnaire.items():
            member_type = members.get(name)
            if member_type is None:
                self.add([*where, name], f"04 T-CON-19 lists no member {name!r} for topic {topic}")
                continue
            problem = self.questionnaire_value(member_type, value, obligations, estimates)
            if problem:
                self.add([*where, name], f"{name} {problem} (04 T-CON-19)")
        missing = sorted(required - set(questionnaire))
        if missing:
            self.add(where, f"topic {topic} requires {', '.join(missing)} (04 T-CON-19)")
        if topic == "PRINCIPAL_AGENT":
            if ("product_code" in questionnaire) == ("obligation_key" in questionnaire):
                self.add(
                    where, "PRINCIPAL_AGENT names exactly one of product_code and obligation_key"
                )
            if questionnaire.get("conclusion") == "AGENT":
                basis = questionnaire.get("gross_to_net_basis")
                measure = "rate" if basis == "COMMISSION_RATE" else "amount"
                if basis is None or measure not in questionnaire:
                    self.add(
                        where, f"AGENT requires gross_to_net_basis and {measure} (04 T-CON-19)"
                    )
        if topic == "OTHER":
            if {"pol_044_override", "claim_enforceable"} & set(
                questionnaire
            ) and "estimate_key" not in questionnaire:
                self.add(where, "pol_044_override and claim_enforceable come with estimate_key")
            if "returns_immaterial" in questionnaire and "obligation_key" not in questionnaire:
                self.add(where, "returns_immaterial comes with obligation_key")

    def questionnaire_value(
        self, member_type: str, value: object, obligations: frozenset[str], estimates: set[str]
    ) -> str | None:
        if member_type in ("bool", "date", "decimal"):
            return None if _typed(member_type, value) else f"is not a {member_type}"
        if member_type.startswith("enum:"):
            literals = enum_literals()[member_type.removeprefix("enum:")]
            return None if value in literals else f"{value!r} is not a literal"
        if member_type.startswith("one-of:"):
            return (
                None
                if value in member_type.removeprefix("one-of:").split("|")
                else f"{value!r} is not a literal"
            )
        known: object = {
            "obligation": obligations,
            "obligation-or-contract": {"", *obligations},
            "estimate": estimates,
            "product": self.products,
            "bundle": {code for code, product in self.products.items() if product.is_bundle},
        }[member_type]
        return None if value in known else f"{value!r} does not resolve"  # type: ignore[operator]

    def timeline(self) -> None:
        key = self.key
        previous_recorded: str | None = None
        gap_reported = False
        booked: dict[str, int] = {}
        for index, item in enumerate(key.timeline):
            at: list[str | int] = ["timeline", index]
            if item.seq != index + 1 and not gap_reported:
                self.add(
                    [*at, "seq"],
                    f"seq {item.seq} breaks the sequence 1, 2, 3, … at {index + 1} (DG-AK-32)",
                )
                gap_reported = True
            if item.recorded_at is not None:
                if previous_recorded is not None and item.recorded_at <= previous_recorded:
                    self.add(
                        [*at, "recorded_at"], "recorded_at is not strictly increasing (§9.5.5)"
                    )
                previous_recorded = item.recorded_at
            if isinstance(item, EventItem):
                self.event(at, item, booked)
            elif isinstance(item, PeriodStateItem):
                self.handle([*at, "entity"], item.entity, self.entities, "entity")
                self.literal([*at, "book"], item.book, "book_code")
                self.literal([*at, "state"], item.state, "period_state")
            elif isinstance(item, CommandItem) and key.runner != "platform":
                self.add(
                    [*at, "command"], "command items appear only with runner platform (DG-AK-32)"
                )
        for index, contract in enumerate(key.contracts):
            renewed = contract.renewal_of
            if renewed in booked and contract.external_id in booked:
                if booked[renewed] >= booked[contract.external_id]:
                    self.add(
                        ["contracts", index, "renewal_of"],
                        f"{renewed} is not booked before {contract.external_id} (§9.5.4)",
                    )

    def event(self, at: list[str | int], item: EventItem, booked: dict[str, int]) -> None:
        contract = self.contracts.get(item.contract)
        if contract is None:
            self.handle([*at, "contract"], item.contract, self.contracts, "contract")
            return
        event_type = item.event_type
        payload = item.payload
        if event_type not in enum_literals()["contract_event_type"]:
            self.literal([*at, "event_type"], event_type, "contract_event_type")
            return
        if event_type in ("CONTRACT_BOOKED", "CONTRACT_ACTIVATED"):
            if payload:
                self.add([*at, "payload"], f"{event_type} carries payload {{}} (§9.5.5)")
            if event_type == "CONTRACT_BOOKED":
                booked.setdefault(contract.external_id, item.seq)
            return
        where = [*at, "payload"]
        allowed = payload_members().get(event_type, frozenset()) | HANDLE_PAYLOAD_MEMBERS
        for name in payload:
            if name not in allowed:
                self.add([*where, name], f"04 §16.3 lists no {event_type} payload member {name!r}")
        if "tax_lines" in payload and "tax_amount" in payload:
            self.add(
                [*where, "tax_amount"],
                "tax_lines and tax_amount never appear in one payload (DG-AK-32)",
            )
        currency = contract.transaction_currency
        for name in sorted(MONEY_PAYLOAD_MEMBERS & set(payload)):
            self.money([*where, name], payload[name], currency)
        tax_lines = payload.get("tax_lines")
        for index, line in enumerate(tax_lines if isinstance(tax_lines, list) else ()):
            line_at = [*where, "tax_lines", index]
            if not isinstance(line, dict):
                self.add(line_at, "a tax line is a mapping")
                continue
            for name in line:
                if name not in TAX_LINE_MEMBERS:
                    self.add(
                        [*line_at, name],
                        f"tax lines carry exactly {', '.join(sorted(TAX_LINE_MEMBERS))}",
                    )
            missing = sorted(TAX_LINE_MEMBERS - set(line))
            if missing:
                self.add(line_at, f"tax line without {', '.join(missing)} (04 §16.3)")
            self.money([*line_at, "amount"], line.get("amount"), currency)
            if (
                "principal_or_agent" in line
                and line["principal_or_agent"] not in TAX_PRINCIPAL_OR_AGENT
            ):
                self.add(
                    [*line_at, "principal_or_agent"], "principal_or_agent is PRINCIPAL or AGENT"
                )
        if "estimate" in payload:
            self.estimate_handle(where, contract, payload)
        references = {modification.reference for modification in contract.modifications or ()}
        self.handle(
            [*where, "modification"], payload.get("modification"), references, "modification"
        )
        handles = {judgement.handle for judgement in contract.judgements or ()}
        self.handle([*where, "judgement"], payload.get("judgement"), handles, "judgement")
        new_lines = payload.get("new_lines")
        for index, line in enumerate(new_lines if isinstance(new_lines, list) else ()):
            if isinstance(line, dict):
                line_at = [*where, "new_lines", index]
                self.handle(
                    [*line_at, "product_code"], line.get("product_code"), self.products, "product"
                )
                self.money([*line_at, "total_price"], line.get("total_price"), currency)

    def estimate_handle(
        self, where: list[str | int], contract: Contract, payload: Mapping[str, JsonValue]
    ) -> None:
        """§9.5.3: an estimate handle resolves in the contract, then in portfolios listing it."""
        code = payload.get("estimate")
        hits = [estimate for estimate in contract.estimates or () if estimate.element_code == code]
        for portfolio in self.key.world.portfolios:
            if contract.external_id in portfolio.members:
                hits.extend(e for e in portfolio.estimates or () if e.element_code == code)
        if not hits:
            self.add([*where, "estimate"], f"estimate {code!r} does not resolve (DG-AK-32)")
        elif len(hits) > 1:
            self.add([*where, "estimate"], f"estimate {code!r} resolves in two places (§9.5.3)")
        elif payload.get("version_no") not in {
            str(version.version_no) for version in hits[0].versions
        }:
            self.add(
                [*where, "version_no"],
                f"version_no {payload.get('version_no')!r} of estimate {code!r} does not resolve",
            )

    def checkpoint(self, at: list[str | int], checkpoint: Checkpoint) -> None:
        key = self.key
        if checkpoint.after_seq not in {item.seq for item in key.timeline}:
            self.add(
                [*at, "after_seq"],
                f"after_seq {checkpoint.after_seq} names no timeline item (DG-AK-32)",
            )
        if checkpoint.book not in key.books:
            self.add([*at, "book"], f"book {checkpoint.book} is not one of books (DG-AK-23)")
        for name in ("journals", "reports", "period_states"):
            if getattr(checkpoint, name) is not None and key.runner != "platform":
                self.add([*at, name], f"{name} appear only with runner platform (DG-AK-32)")
        for index, block in enumerate(checkpoint.contracts or ()):
            self.contract_block([*at, "contracts", index], block)
        for index, subledger in enumerate(checkpoint.subledger or ()):
            self.subledger([*at, "subledger", index], subledger)
        for index, group in enumerate(checkpoint.groups or ()):
            where = [*at, "groups", index]
            if group.group not in self.groups:
                self.add(
                    [*where, "group"], f"{group.group!r} is not a combination_group of contracts[]"
                )
            currencies = {
                c.transaction_currency for c in key.contracts if c.combination_group == group.group
            }
            single = next(iter(currencies)) if len(currencies) == 1 else None
            for row_index, row in enumerate(group.balances):
                self.balance([*where, "balances", row_index], row, single)
        for index, exception in enumerate(checkpoint.exceptions or ()):
            where = [*at, "exceptions", index]
            if exception.code not in finding_codes():
                self.add([*where, "code"], f"{exception.code} is not a 04 §15.4 code")
            self.handle([*where, "contract"], exception.contract, self.contracts, "contract")
            if exception.subject is not None:
                match = _SUBJECT.fullmatch(exception.subject)
                if (
                    not match
                    or (match[1], match[2]) not in self.ssp_labels
                    or match[3] not in self.products
                ):
                    self.add(
                        [*where, "subject"],
                        f"subject {exception.subject!r} does not resolve (§9.5.6)",
                    )
        for index, report in enumerate(checkpoint.reports or ()):
            self.report([*at, "reports", index], report)
        for index, state in enumerate(checkpoint.period_states or ()):
            where = [*at, "period_states", index]
            self.handle([*where, "entity"], state.entity, self.entities, "entity")
            self.literal([*where, "book"], state.book, "book_code")
            self.literal([*where, "state"], state.state, "period_state")

    def contract_block(self, at: list[str | int], block: ContractBlock) -> None:
        contract = self.contracts.get(block.contract)
        if contract is None:
            self.handle([*at, "contract"], block.contract, self.contracts, "contract")
            return
        currency = contract.transaction_currency
        self.literal([*at, "status_in_book"], block.status_in_book, "contract_status")
        if block.version is not None:
            for member in VERSION_MONEY_MEMBERS:
                self.money([*at, "version", member], getattr(block.version, member), currency)
            for member in NON_POSITIVE_VERSION_MEMBERS:
                amount, _, _ = _money_parts(getattr(block.version, member), currency)
                if isinstance(amount, str) and _DECIMAL.fullmatch(amount) and Decimal(amount) > 0:
                    self.add(
                        [*at, "version", member],
                        f"{member} {amount} is positive; the member is never positive (S04-R-02)",
                    )
            self.places([*at, "version", "total_ssp"], block.version.total_ssp, EXACT_PLACES)
        columns = obligation_columns()
        literals = enum_literals()
        for index, row in enumerate(block.obligations or ()):
            where = [*at, "obligations", index]
            for name, value in row.items():
                if name == "obligation_key" or value is None:
                    continue
                column_type = columns.get(name)
                if column_type is None:
                    self.add([*where, name], f"{name!r} is not a T-CON-11 column (§9.5.6)")
                elif column_type == "erev.money":
                    self.money([*where, name], value, currency)
                elif column_type in ("erev.exact", "erev.fx_rate"):
                    limit = RATE_PLACES if column_type == "erev.fx_rate" else EXACT_PLACES
                    self.places([*where, name], value, limit)
                elif (
                    column_type.startswith("erev.")
                    and column_type.removeprefix("erev.") in literals
                ):
                    self.literal([*where, name], value, column_type.removeprefix("erev."))
        for index, row in enumerate(block.balances or ()):
            self.balance([*at, "balances", index], row, currency)
        for index, schedule in enumerate(block.schedule or ()):
            where = [*at, "schedule", index]
            self.literal([*where, "schedule_kind"], schedule.schedule_kind, "schedule_kind")
            self.literal([*where, "line_type"], schedule.line_type, "schedule_line_type")
            for period_key, amount in (schedule.amounts or {}).items():
                self.money([*where, "amounts", period_key], amount, currency)
            self.money([*where, "amount"], schedule.amount, currency)
            self.money([*where, "cumulative_amount"], schedule.cumulative_amount, currency)
            self.places([*where, "quantity"], schedule.quantity, EXACT_PLACES)
        references = {modification.reference for modification in contract.modifications or ()}
        for index, modification in enumerate(block.modifications or ()):
            where = [*at, "modifications", index]
            self.handle([*where, "reference"], modification.reference, references, "modification")
            for obligation, treatment in modification.proposed_treatments.items():
                self.literal(
                    [*where, "proposed_treatments", obligation], treatment, "modification_treatment"
                )
        for index, assertion in enumerate(block.trace or ()):
            self.places([*at, "trace", index, "value"], assertion.value, EXACT_PLACES)

    def balance(self, at: list[str | int], row: BalanceRow, currency: str | None) -> None:
        entity = self.entities.get(row.entity)
        self.handle([*at, "entity"], row.entity, self.entities, "entity")
        for name in BalanceAmounts.model_fields:
            self.money([*at, name], getattr(row, name), currency)
            if row.functional is not None:
                functional = entity.functional_currency if entity is not None else None
                self.money([*at, "functional", name], getattr(row.functional, name), functional)

    def subledger(self, at: list[str | int], block: SubledgerBlock) -> None:
        key = self.key
        self.handle([*at, "entity"], block.entity, self.entities, "entity")
        self.handle([*at, "contract"], block.contract, self.contracts, "contract")
        currencies = {contract.transaction_currency for contract in key.contracts}
        contract = self.contracts.get(block.contract) if block.contract else None
        if contract is not None:
            currency: str | None = contract.transaction_currency
        else:
            currency = next(iter(currencies)) if len(currencies) == 1 else None
        entity = self.entities.get(block.entity)
        functional = entity.functional_currency if entity is not None else None
        for index, line in enumerate(block.lines):
            where = [*at, "lines", index]
            role = line.account_role
            if role not in enum_literals()["account_role"]:
                self.literal([*where, "account_role"], role, "account_role")
            elif role in RESERVED_ACCOUNT_ROLES:
                self.add(
                    [*where, "account_role"],
                    f"reserved role {role} never appears in subledger lines (D-14a)",
                )
            self.clearing_purpose(where, role, line.clearing_purpose)
            self.literal([*where, "entry_kind"], line.entry_kind, "subledger_entry_kind")
            self.handle([*where, "account"], line.account, self.accounts, "account")
            self.handle(
                [*where, "counterparty_entity"], line.counterparty_entity, self.entities, "entity"
            )
            self.money([*where, "dr"], line.dr, currency)
            self.money([*where, "cr"], line.cr, currency)
            self.money([*where, "functional_dr"], line.functional_dr, functional)
            self.money([*where, "functional_cr"], line.functional_cr, functional)

    def report(self, at: list[str | int], report: ReportBlock) -> None:
        try:
            columns = report_columns(self.key, report)
        except ValueError as error:
            self.add([*at, "parameters", "time_bands"], str(error))
            columns = None
        for index, cell in enumerate(report.cells):
            where = [*at, "cells", index]
            try:
                report_row_key(self.key, report, cell.row_key)
            except ValueError as error:
                self.add([*where, "row_key"], str(error))
            if columns is not None and cell.column_key not in columns:
                self.add(
                    [*where, "column_key"],
                    f"{cell.column_key!r} is not a {report.report_code} column key (DG-AK-35)",
                )


def _typed(member_type: str, value: object) -> bool:
    if member_type == "bool":
        return isinstance(value, bool)
    if member_type == "date":
        return isinstance(value, str) and bool(_DATE.fullmatch(value))
    return isinstance(value, str) and bool(_UNSIGNED_DECIMAL.fullmatch(value))


def cross_validation_findings(key: AnswerKey, path: Path) -> list[Finding]:
    """Every DG-AK-32 violation of a schema-valid key, in document order."""
    return _CrossValidator(key, path).run()


# Encodings (DG-AK-34, DG-AK-35)


def release_basis(key: AnswerKey, contract: Contract) -> str:
    """POL-049 for the contract: contract override, then entity and tenant values, then default."""
    for override in contract.policy_overrides or ():
        if override.policy_key == RELEASE_BASIS_KEY and override.obligation_key is None:
            return str(override.value)
    policies = key.world.policies
    for values in (policies.entities.get(contract.contracting_entity, {}), policies.tenant):
        if RELEASE_BASIS_KEY in values:
            return str(values[RELEASE_BASIS_KEY])
    return str(POLICY_PARAMETERS[RELEASE_BASIS_KEY].default_asc606)


def consideration_payable_items(
    key: AnswerKey, contract: Contract
) -> tuple[ConsiderationPayable, ...]:
    """DG-AK-34: the `consideration_payable` items of the mapped EXPECTED_PURCHASES elements."""
    committed = release_basis(key, contract) == "COMMITTED_PURCHASES"
    every_obligation = tuple(dict.fromkeys(line.obligation_key for line in contract.lines))
    items: list[ConsiderationPayable] = []
    for estimate in contract.estimates or ():
        if not maps_to_consideration_payable(estimate):
            continue
        first = estimate.versions[0]
        amount = str(first.unconstrained_amount)
        fair_value = None
        if first.constrained_amount is not None and Decimal(first.constrained_amount) < Decimal(
            amount
        ):
            fair_value = str(Decimal(amount) - Decimal(first.constrained_amount))
        if estimate.target_obligation_keys:
            related = tuple(estimate.target_obligation_keys)
        elif estimate.obligation_key is not None:
            related = (estimate.obligation_key,)
        else:
            related = every_obligation
        items.append(
            ConsiderationPayable(
                amount=amount,
                promise_date=first.effective_date,
                related_obligation_keys=related,
                distinct_good_fair_value=fair_value,
                committed_purchases=first.expected_total_amount if committed else None,
                share_based=False,
            )
        )
    return tuple(items)


def _encode_contract(key: AnswerKey, contract: Contract) -> Contract:
    """DG-AK-34: map EXPECTED_PURCHASES promises to `consideration_payable`; the elements keep only
    `expected_total_amount` as the release base."""
    if contract.consideration_payable:
        return contract
    items = consideration_payable_items(key, contract)
    if not items:
        return contract
    estimates = tuple(
        estimate.model_copy(
            update={
                "versions": tuple(
                    version.model_copy(
                        update={"unconstrained_amount": None, "constrained_amount": None}
                    )
                    for version in estimate.versions
                )
            }
        )
        if maps_to_consideration_payable(estimate)
        else estimate
        for estimate in contract.estimates or ()
    )
    return contract.model_copy(update={"consideration_payable": items, "estimates": estimates})


def _encode_checkpoint(key: AnswerKey, checkpoint: Checkpoint) -> Checkpoint:
    """DG-AK-35: rewrite report row keys to the report-run row keys."""
    if not checkpoint.reports:
        return checkpoint
    reports = tuple(
        report.model_copy(
            update={
                "cells": tuple(
                    cell.model_copy(update={"row_key": report_row_key(key, report, cell.row_key)})
                    for cell in report.cells
                )
            }
        )
        for report in checkpoint.reports
    )
    return checkpoint.model_copy(update={"reports": reports})


def apply_encodings(key: AnswerKey) -> AnswerKey:
    """The DG-AK-34 and DG-AK-35 rewrites of a cross-validated key."""
    return key.model_copy(
        update={
            "contracts": tuple(_encode_contract(key, contract) for contract in key.contracts),
            "checkpoints": tuple(_encode_checkpoint(key, cp) for cp in key.checkpoints),
        }
    )


def load(path: Path) -> LoadedKey:
    """Read, parse, validate, cross-validate and encode one key file (§9.5.2 to §9.5.8)."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AnswerKeyError(path, "", f"not UTF-8: {error}") from error
    if "\r" in text:
        raise AnswerKeyError(path, "", "line endings are LF (DG-AK-03)")
    key = validate(parse_yaml(text, path=path), path=path)
    findings = [(item.pointer, item.message) for item in cross_validation_findings(key, path)]
    if findings:
        raise AnswerKeyError(path, findings[0][0], _summarise(findings[0], findings[1:]))
    return LoadedKey(key=apply_encodings(key), path=path, sha256=hashlib.sha256(raw).hexdigest())


# Corpus loading and selection (DG-AK-32, DG-AK-42)

SELECTION_VARIABLES: Final = {"FAMILY": "families", "ID": "ids", "REQ": "requirements"}


def load_all(
    *,
    families: Iterable[str] = (),
    ids: Iterable[str] = (),
    requirements: Iterable[str] = (),
    include_withdrawn: bool = False,
    root: Path = ANSWER_KEY_ROOT,
) -> list[LoadedKey]:
    """Load every key, raise one ExceptionGroup of every error, then select (DG-AK-42).

    Filters combine with AND: `families` matches `families[0]`, `ids` the key id, `requirements`
    any listed requirement. A filter value that selects no key raises ValueError.
    """
    errors: list[AnswerKeyError] = []
    loaded: list[LoadedKey] = []
    try:
        paths = discover(root)
    except AnswerKeyError as error:
        raise ExceptionGroup("answer-key corpus cannot be discovered", [error]) from None
    first_path: dict[str, Path] = {}
    for path in paths:
        try:
            item = load(path)
        except AnswerKeyError as error:
            errors.append(error)
            continue
        if item.key.id in first_path:
            errors.append(
                AnswerKeyError(
                    path, "/id", f"id {item.key.id} is also used by {first_path[item.key.id]}"
                )
            )
            continue
        first_path[item.key.id] = path
        loaded.append(item)
    if errors:
        raise ExceptionGroup(f"{len(errors)} invalid answer-key files", errors)
    return select_keys(
        loaded,
        families=families,
        ids=ids,
        requirements=requirements,
        include_withdrawn=include_withdrawn,
    )


def select_keys(
    loaded: Sequence[LoadedKey],
    *,
    families: Iterable[str] = (),
    ids: Iterable[str] = (),
    requirements: Iterable[str] = (),
    include_withdrawn: bool = False,
) -> list[LoadedKey]:
    """The DG-AK-42 selection among loaded keys, as `load_all` applies it."""
    selected = [item for item in loaded if include_withdrawn or item.key.status == "active"]
    wanted = {
        "families": {value.upper() for value in families},
        "ids": set(ids),
        "requirements": set(requirements),
    }
    unknown_families = sorted(wanted["families"] - set(FAMILY_CODES))
    if unknown_families:
        raise ValueError(f"unknown family codes {', '.join(unknown_families)} (POLICIES §0.7)")
    if wanted["families"]:
        selected = [item for item in selected if item.key.families[0] in wanted["families"]]
    if wanted["ids"]:
        selected = [item for item in selected if item.key.id in wanted["ids"]]
    if wanted["requirements"]:
        selected = [
            item for item in selected if wanted["requirements"] & set(item.key.requirements)
        ]
    matched = {
        "families": {item.key.families[0] for item in selected},
        "ids": {item.key.id for item in selected},
        "requirements": {req for item in selected for req in item.key.requirements},
    }
    for name, values in wanted.items():
        missing = sorted(values - matched[name])
        if missing:
            raise ValueError(f"{name} {', '.join(missing)} select no answer key")
    return selected


def selection_from_env(environ: Mapping[str, str] | None = None) -> dict[str, tuple[str, ...]]:
    """`FAMILY`, `ID` and `REQ` (comma-separated) as `load_all` keyword arguments (DG-AK-42)."""
    source = os.environ if environ is None else environ
    return {
        argument: tuple(
            part.strip() for part in source.get(variable, "").split(",") if part.strip()
        )
        for variable, argument in SELECTION_VARIABLES.items()
    }


def active_selection(environ: Mapping[str, str] | None = None) -> list[LoadedKey]:
    """The active keys of the `FAMILY`, `ID` and `REQ` selection (DG-AK-13; D-79).

    Withdrawn keys take part in the selection, so a withdrawn id is validated and reported but
    never collected. An unknown family, id or requirement still raises ValueError.
    """
    selected = select_keys(
        load_all(include_withdrawn=True), include_withdrawn=True, **selection_from_env(environ)
    )
    return [item for item in selected if item.key.status == "active"]


def selection_is_filtered(selection: Mapping[str, Iterable[str]]) -> bool:
    """DG-AK-42: a filtered run skips the coverage check."""
    return any(tuple(values) for values in selection.values())


# Corpus coverage (DG-AK-33)

COVERAGE_HEADING: Final = "Corpus gaps (supervisor)"
_REQ_ROW = re.compile(r"^\| (REQ-[A-Z]+-[0-9]{3}) \|")
_AK_HINT = re.compile(r"\bAK:([A-Z0-9][A-Z0-9-]*[A-Z0-9])")
_AK_FAM_HINT = re.compile(r"\bAK-FAM:([a-z0-9]+(?:-[a-z0-9]+)*)")
_HANDLE = re.compile(r"^[A-Z0-9][A-Z0-9-]*[A-Z0-9]$")
_COVERAGE_CONDITION = re.compile(
    r"^`(derived_from\.research04|derived_from\.research05|families)` contains "
    r"(?:a listed id|`([A-Z0-9-]+)`)(?: \([^()]*\))?$"
)


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """One corpus gap: the COV id, hint, family code or CHK id, the REQ rows citing it, and why."""

    subject: str
    message: str
    requirements: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CoverageCount:
    covered: int
    total: int


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Per-list counts (``List A``, ``List B``, ``List C``, ``AK: hints``, ``AK-FAM: slugs``,
    ``family codes``) and the gaps, in that list order."""

    counts: Mapping[str, CoverageCount]
    gaps: tuple[CoverageGap, ...]

    @property
    def ok(self) -> bool:
        return not self.gaps

    def render(self) -> str:
        summary = "; ".join(f"{name} {n.covered} of {n.total}" for name, n in self.counts.items())
        lines = [f"Corpus coverage: {summary}"]
        if self.gaps:
            lines += ["", COVERAGE_HEADING, *(f"- {gap.message}" for gap in self.gaps)]
        return "\n".join(lines)


def _register_hints(text: str, pattern: re.Pattern[str]) -> dict[str, tuple[str, ...]]:
    """Hint → the REQ ids of the register rows that carry it, over the whole register."""
    found: dict[str, set[str]] = {}
    for line in text.splitlines():
        row = _REQ_ROW.match(line)
        for hint in pattern.findall(line):
            found.setdefault(hint, set()).update([row.group(1)] if row else [])
    return {hint: tuple(sorted(reqs)) for hint, reqs in sorted(found.items())}


def _coverage_rows(text: str, start: str, end: str, prefix: str) -> list[tuple[str, list[str]]]:
    """The `COV-<list>-nn` rows of one §12 table: id and the remaining cells, stripped."""
    rows: list[tuple[str, list[str]]] = []
    for line in _between(text, start, end).splitlines():
        match = re.match(rf"^\| ({prefix}-[0-9]+) \|(.*)\|$", line)
        if match:
            rows.append((match.group(1), [cell.strip() for cell in match.group(2).split("|")]))
    return rows


def _unparsed(cov_id: str) -> CoverageGap:
    return CoverageGap(cov_id, f"unparsed coverage row {cov_id}")


def coverage(
    keys: Sequence[LoadedKey],
    *,
    requirements_doc: Path = REQUIREMENTS_DOC,
    policies_doc: Path = POLICIES_DOC,
) -> CoverageReport:
    """DG-AK-33 corpus gaps of the active keys among `keys` (unfiltered runs only).

    The register and POLICIES are read when this runs: `AK:` and `AK-FAM:` hints anywhere in the
    register, List A (§12.1), List B (§12.2) and List C (every CHK id POLICIES names). A family code
    counts when an active key lists it anywhere in `families`.
    """
    active = [item.key for item in keys if item.key.status == "active"]
    index: dict[str, set[str]] = {
        "derived_from.research04": {x for k in active for x in k.derived_from.research04},
        "derived_from.research05": {x for k in active for x in k.derived_from.research05},
        "families": {x for k in active for x in k.families},
    }
    tags = {tag for k in active for tag in k.tags}
    upper_ids = [k.id.upper() for k in active]
    register = requirements_doc.read_text(encoding="utf-8")
    counts: dict[str, CoverageCount] = {}
    gaps: list[CoverageGap] = []

    def tally(name: str, total: int, new_gaps: list[CoverageGap]) -> None:
        counts[name] = CoverageCount(total - len(new_gaps), total)
        gaps.extend(new_gaps)

    list_a: list[CoverageGap] = []
    rows_a = _coverage_rows(register, "### 12.1 ", "### 12.2 ", "COV-A")
    for cov_id, cells in rows_a:
        if len(cells) != 3 or not _HANDLE.match(cells[1]):
            list_a.append(_unparsed(cov_id))
        elif cells[1] not in index["derived_from.research05"]:
            message = f"{cov_id}: no active key whose derived_from.research05 contains {cells[1]}"
            list_a.append(CoverageGap(cov_id, message))
    tally("List A", len(rows_a), list_a)

    list_b: list[CoverageGap] = []
    rows_b = _coverage_rows(register, "### 12.2 ", "### 12.3 ", "COV-B")
    for cov_id, cells in rows_b:
        condition = _COVERAGE_CONDITION.match(cells[2]) if len(cells) == 3 else None
        ids = [condition.group(2)] if condition and condition.group(2) else []
        if condition and not ids:
            ids = re.findall(r"`([A-Z0-9-]+)`", cells[1])
        if condition is None or not ids:
            list_b.append(_unparsed(cov_id))
        elif not index[condition.group(1)] & set(ids):
            wanted = ", ".join(ids)
            message = f"{cov_id}: no active key whose {condition.group(1)} contains one of {wanted}"
            list_b.append(CoverageGap(cov_id, message))
    tally("List B", len(rows_b), list_b)

    chks = sorted(set(_CHK_ID.findall(policies_doc.read_text(encoding="utf-8"))))
    list_c = [
        CoverageGap(chk, f"List C {chk}: no active key whose id contains {chk}")
        for chk in chks
        if not any(chk.upper() in key_id for key_id in upper_ids)
    ]
    tally("List C", len(chks), list_c)

    ak_hints = _register_hints(register, _AK_HINT)
    tally(
        "AK: hints",
        len(ak_hints),
        [
            CoverageGap(
                f"AK:{hint}",
                f"AK:{hint} ({', '.join(reqs)}): no active key whose derived_from.research04 "
                f"contains {hint}",
                reqs,
            )
            for hint, reqs in ak_hints.items()
            if hint not in index["derived_from.research04"]
        ],
    )

    slugs = _register_hints(register, _AK_FAM_HINT)
    tally(
        "AK-FAM: slugs",
        len(slugs),
        [
            CoverageGap(
                f"AK-FAM:{slug}",
                f"AK-FAM:{slug} ({', '.join(reqs)}): no active key tagged {slug}",
                reqs,
            )
            for slug, reqs in slugs.items()
            if slug not in tags
        ],
    )

    tally(
        "family codes",
        len(FAMILY_CODES),
        [
            CoverageGap(code, f"family code {code}: no active key lists it in families")
            for code in FAMILY_CODES
            if code not in index["families"]
        ],
    )
    return CoverageReport(counts=MappingProxyType(counts), gaps=tuple(gaps))
