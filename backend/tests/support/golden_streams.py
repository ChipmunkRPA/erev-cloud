"""Golden event streams for engine tests (BUILD_SPEC ENB-1; B3-BS2-08; DG-PAR-02).

``stream(contract, through_step)`` replays the legacy UAT uploads of golden steps 01 to
``through_step`` for one legacy contract. It returns the ``ContractInput``, ``SspVersionInput`` and
``EventInput`` tuples of the replay, with the products and estimate versions they reference.
Template rows map to events by ENGINE_SPEC S01-R-05 to S01-R-09 (04 LM-TPL-SETUP, LM-TPL-PROG,
LM-TPL-MOD).

The helper reads ``docs/legacy/golden/NN-<slug>/step.json`` and the committed workbook
``backend/tests/fixtures/legacy_uat/NN-<slug>/<basename>`` read-only. Each file is opened once in a
read mode; the workbook bytes are checked against ``step.json`` ``file_sha256`` and parsed from
memory, and nothing is written. It is test support, never product code: the DIN importer does not
import it, and GPA cross-checks the same figures through the real import pipeline.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

import openpyxl
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    ContractInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    MaterialRightInput,
    ModificationInput,
    ProductInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.canonical import sha256_hex
from erev_engine.dates import month_start
from erev_engine.stages.s01_canonicalize import encode_key, obligation_subject_key
from support import bundles

__all__ = [
    "CURRENCY",
    "SSP_BOOK",
    "GoldenStep",
    "GoldenStream",
    "parity_templates",
    "steps",
    "stream",
]

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
GOLDEN_ROOT: Final = REPO_ROOT / "docs" / "legacy" / "golden"
FIXTURE_ROOT: Final = REPO_ROOT / "backend" / "tests" / "fixtures" / "legacy_uat"
SSP_BOOK: Final = "LEGACY-SKU-SSP"  # S01-R-05
CURRENCY: Final = "USD"  # tenant reporting currency of the replay (S01-R-06)
EVENT_ORIGIN: Final = "IMPORT"  # T-CON-05 origin of template uploads
TEMPLATE_VERSION: Final = "1"
_STEP_DIRECTORY: Final = re.compile(r"(?P<number>[0-9]{2})-[a-z0-9-]+")

# step.json handler -> (template code, E-24 template mode)
HANDLERS: Final[Mapping[str, tuple[str, str | None]]] = {
    "browse_file_SSPs": ("legacy_sku_ssp", None),
    "browse_file_Contracts": ("legacy_contract_setup", None),
    "browse_file_Deliveries": ("legacy_progress_tracking", None),
    "browse_file_ProsMod": ("legacy_contract_modification", "prospective"),
    "browse_file_RetroMod": ("legacy_contract_modification", "retrospective"),
    "browse_file_POB_specific_VC": ("legacy_contract_modification", "pob_price_change"),
}
# S01-R-09: the chosen treatment of every obligation under POL-100 USER_SELECTED_TEMPLATE.
TREATMENTS: Final[Mapping[str, str]] = {
    "prospective": "LEGACY_PROSPECTIVE",
    "retrospective": "LEGACY_RETROSPECTIVE",
    "pob_price_change": "LEGACY_POB_VC",
}
# 04 T-IMP-01 header sets (IPL-03).
HEADERS: Final[Mapping[str, tuple[str, ...]]] = {
    "legacy_sku_ssp": (
        "SKU Unique ID",
        "SKU Name",
        "Distinct or Nondistinct",
        "SKU Unit List Price",
        "ASC 606 Stratification",
        "Midpoint Discount Percentage",
        "SSP Range Method (+-)",
        "SSP Version",
        "Revenue Account",
    ),
    "legacy_contract_setup": (
        "Contract Unique Name",
        "POB Unique ID",
        "SKU Name",
        "POB Start Date",
        "POB End Date",
        "ASC 606 Stratification",
        "Original POB Total Selling Price",
        "Original POB Total Qty",
        "Selling Entity",
        "SSP Version",
        "Deferred Revenue Account",
        "Unbilled A/R Account",
        "Current Period",
        "Memo 1",
        "Memo 2",
        "Memo 3",
    ),
    "legacy_progress_tracking": (
        "Contract Unique Name",
        "POB Unique ID",
        "SKU Name",
        "Current Delivery",
        "Current Billing",
        "Current Pre-ASC606 Revenue (Net Design Only)",
        "Memo 1",
        "Memo 2",
        "Memo 3",
    ),
    "legacy_contract_modification": (
        "Contract Unique Name",
        "POB Unique ID",
        "SKU Name",
        "Mod Start Date",
        "Mod End Date",
        "ASC 606 Stratification",
        "Mod Billing",
        "Mod Qty",
        "Selling Entity",
        "Deferred Revenue Account",
        "Unbilled A/R Account",
        "SSP Version",
        "Memo 1",
        "Memo 2",
        "Memo 3",
    ),
}
_DISTINCT_FLAGS: Final = {"Distinct": "distinct", "Nondistinct": "nondistinct"}  # LM-SSP-03
_MEMOS: Final = (("Memo 1", "memo_1"), ("Memo 2", "memo_2"), ("Memo 3", "memo_3"))
# The migration mapping profile of the golden tenant marks these SKUs as material rights (S03-R-18).
_MATERIAL_RIGHT_PREFIX: Final = "Material Right"
LEGACY_MATERIAL_RIGHT: Final = "LEGACY-MATERIAL-RIGHT"

Row = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GoldenStep:
    """One golden step: the upload handler, its date parameter and the verified workbook."""

    number: str  # "01" to "14"
    directory: Path
    template_code: str
    mode: str | None  # E-24 for modification uploads
    date_input: date | None
    workbook: Path
    file_sha256: str


@dataclass(frozen=True, slots=True)
class GoldenStream:
    """The replay of one legacy contract through a golden step (B3-BS2-08)."""

    contract: str
    through_step: str
    contracts: tuple[ContractInput, ...]
    ssp_versions: tuple[SspVersionInput, ...]
    events: tuple[EventInput, ...]  # ENG-06 order
    products: tuple[ProductInput, ...]  # code
    estimate_versions: tuple[EstimateVersionInput, ...]  # (estimate_key, version_no)
    warnings: tuple[tuple[str, str, int], ...]  # (code, step, worksheet row), S01-R-07

    def booking_lines(self, contract_key: str | None = None) -> tuple[Mapping[str, object], ...]:
        """The API-S-ContractLine members of the contract's ``CONTRACT_BOOKED`` payload."""
        key = self.contract if contract_key is None else contract_key
        for event in self.events:
            if event.contract_key == key and event.event_type == "CONTRACT_BOOKED":
                lines = event.payload["lines"]
                if not isinstance(lines, list | tuple):
                    raise TypeError("booking member lines is not an array")
                return tuple(line for line in lines if isinstance(line, Mapping))
        raise ValueError(f"{key} has no CONTRACT_BOOKED event in the stream")

    def input_bundle(
        self,
        *,
        preset: str = "LEGACY_PARITY",
        books: Sequence[str] = ("ASC606",),
        templates: Iterable[TemplateInput] | None = None,
        trigger: str = "COMMAND",
        months: int = 24,
    ) -> InputBundle:
        """An ``InputBundle`` of the stream with the ``support.bundles`` calendar, books and
        policies of ``preset``, and the seeded parity templates unless ``templates`` is given."""
        header = self.contracts[0]
        calendar = bundles.entity(
            header.contracting_entity_code,
            start=month_start(header.inception_date),
            months=months,
            books=books,
        )
        latest = max(event.recorded_at for event in self.events)
        seeded = parity_templates(header.inception_date) if templates is None else templates
        return InputBundle(
            format_version=1,
            engine_version=ENGINE_VERSION,
            trigger=trigger,
            known_at=latest + timedelta(hours=1),
            tenant_preset=preset,
            currencies=bundles.currencies(CURRENCY),
            books=tuple(bundles.book(code, preset=preset, entity=calendar) for code in books),
            entities=(calendar,),
            group=bundles.group(
                self.contracts, group_key=f"CG-{self.contract}", products=self.products
            ),
            contracts=self.contracts,
            events=self.events,
            ssp_versions=self.ssp_versions,
            pob_template_versions=tuple(
                sorted(seeded, key=lambda template: (template.template_code, template.version_no))
            ),
            rule_set_versions=(),
            estimate_versions=self.estimate_versions,
            fx_rates=(),
            posted=(),
        )


def parity_templates(effective_from: date) -> tuple[TemplateInput, ...]:
    """The seeded parity POB templates, all ``UNITS_DELIVERED`` (04 T-MIG-01; S03-R-18)."""
    rows = (
        ("LEGACY-DISTINCT", "STANDARD", "distinct"),
        (LEGACY_MATERIAL_RIGHT, "MATERIAL_RIGHT", "distinct"),
        ("LEGACY-NONDISTINCT", "STANDARD", "nondistinct"),
        ("LEGACY-VC", "VC_LINE", "distinct"),
    )
    return tuple(
        TemplateInput(
            template_code=code,
            version_key=f"{code}@v1",
            version_no=1,
            content_sha256=sha256_hex({"template_code": code, "version_no": 1}),
            obligation_kind=kind,
            distinctness=flag,
            series_increment_unit=None,
            satisfaction_pattern="POINT_IN_TIME",
            over_time_criterion="NOT_APPLICABLE",
            recognition_method="UNITS_DELIVERED",
            ratable_convention=None,
            start_date_rule="LINE_START",
            end_date_rule="LINE_END",
            term_months=None,
            principal_agent="PRINCIPAL",
            warranty_type="NONE",
            licence_nature="NOT_APPLICABLE",
            sfc_assessment_required=False,
            revenue_category=None,
            disaggregation={},
            account_role_overrides={},
            stratification_label=None,
            is_excluded_from_netting_attribution=False,
            policy_values={},
            effective_from=effective_from,
            effective_to=None,
        )
        for code, kind, flag in rows
    )


def steps(through_step: str) -> tuple[GoldenStep, ...]:
    """Golden steps 01 to ``through_step`` in order, from their ``step.json`` (DG-PAR-02)."""
    if not re.fullmatch(r"[0-9]{2}", through_step):
        raise ValueError(f"through_step {through_step!r} is not a two-digit step number")
    found: list[GoldenStep] = []
    for directory in sorted(GOLDEN_ROOT.iterdir()):
        matched = _STEP_DIRECTORY.fullmatch(directory.name)
        if matched is None or not directory.is_dir():
            continue
        number = matched.group("number")
        if number == "00" or number > through_step:
            continue
        spec = json.loads((directory / "step.json").read_text(encoding="utf-8"))
        handler = spec["handler"]
        if handler not in HANDLERS:
            raise ValueError(f"step {number}: unknown handler {handler!r}")
        template_code, mode = HANDLERS[handler]
        raw_date = spec.get("date_input")
        found.append(
            GoldenStep(
                number=number,
                directory=directory,
                template_code=template_code,
                mode=mode,
                date_input=None if raw_date is None else date.fromisoformat(raw_date),
                workbook=FIXTURE_ROOT / directory.name / Path(spec["file"]).name,
                file_sha256=spec["file_sha256"],
            )
        )
    return tuple(found)


def stream(contract: str, through_step: str) -> GoldenStream:
    """The golden replay of ``contract`` through ``through_step`` (B3-BS2-08)."""
    replay = _Replay(contract)
    for step in steps(through_step):
        rows = _rows(step)
        match step.template_code:
            case "legacy_sku_ssp":
                replay.ssp(step, rows)
            case "legacy_contract_setup":
                replay.setup(step, rows)
            case "legacy_progress_tracking":
                replay.progress(step, rows)
            case _:
                replay.modification(step, rows)
    return replay.result(through_step)


# --- Workbook reading ----------------------------------------------------------------------------


def _rows(step: GoldenStep) -> tuple[tuple[int, Row], ...]:
    """The non-blank rows of the first worksheet as (worksheet row number, header -> value)."""
    data = step.workbook.read_bytes()
    if hashlib.sha256(data).hexdigest() != step.file_sha256:
        raise ValueError(f"{step.workbook.name}: SHA-256 differs from step.json (DG-PAR-02)")
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        values = workbook.worksheets[0].iter_rows(values_only=True)
        header = tuple(next(values))
        names = tuple(name for name in header if name is not None)
        if set(names) != set(HEADERS[step.template_code]) or len(names) != len(set(names)):
            raise ValueError(f"step {step.number}: header differs from T-IMP-01 (IPL-03)")
        rows: list[tuple[int, Row]] = []
        for number, row in enumerate(values, start=2):
            if all(cell is None or cell == "" for cell in row):
                continue
            cells = {str(name): cell for name, cell in zip(header, row, strict=False) if name}
            rows.append((number, cells))
    finally:
        workbook.close()
    return tuple(rows)


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _decimal(value: object, name: str) -> Decimal:
    """A cell number through its shortest decimal string (REQ-DAT-007)."""
    if isinstance(value, bool):
        raise ValueError(f"{name} is not a number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str) and value.strip():
        return Decimal(value.strip())
    raise ValueError(f"{name} is not a number")


def _amount(value: object, name: str) -> Decimal:
    """A progress or modification number; a blank cell is 0."""
    return Decimal(0) if _blank(value) else _decimal(value, name)


def _day(value: object, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip()[:10])
    raise ValueError(f"{name} is not a date")


def _code(value: object, name: str) -> str:
    """A code cell as text: names, account numbers and entity codes."""
    if isinstance(value, bool) or _blank(value):
        raise ValueError(f"{name} is blank")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value).strip()


def _label(value: object, name: str) -> str:
    """An ``SSP Version`` label; a date cell gives its ISO date (legacy ``2023-01-01``)."""
    if isinstance(value, datetime | date):
        return _day(value, name).isoformat()
    return _code(value, name)


def _accounts(row: Row) -> dict[str, str]:
    """S01-R-06 account overrides from the deferred revenue and unbilled A/R accounts."""
    deferred = _code(row["Deferred Revenue Account"], "Deferred Revenue Account")
    unbilled = _code(row["Unbilled A/R Account"], "Unbilled A/R Account")
    return {
        "CONTRACT_ASSET": unbilled,
        "CONTRACT_LIABILITY": deferred,
        "UNBILLED_RECEIVABLE": unbilled,
    }


def _memos(row: Row) -> dict[str, str]:
    return {member: str(row[column]) for column, member in _MEMOS if not _blank(row.get(column))}


# --- Replay --------------------------------------------------------------------------------------


@dataclass
class _Replay:
    contract: str
    products: dict[str, ProductInput] = field(default_factory=dict)
    versions: dict[str, SspVersionInput] = field(default_factory=dict)  # label -> version
    header: ContractInput | None = None
    material_rights: list[MaterialRightInput] = field(default_factory=list)
    modifications: list[ModificationInput] = field(default_factory=list)
    estimates: list[EstimateVersionInput] = field(default_factory=list)
    events: list[EventInput] = field(default_factory=list)
    obligations: dict[str, str] = field(default_factory=dict)  # obligation key -> product code
    referenced: set[str] = field(default_factory=set)  # product codes of lines
    ordinals: dict[tuple[str, str], int] = field(default_factory=dict)
    warnings: list[tuple[str, str, int]] = field(default_factory=list)

    def ssp(self, step: GoldenStep, rows: Sequence[tuple[int, Row]]) -> None:
        """S01-R-05: one BY_LABEL version per label; one legacy_range entry per row."""
        labels = sorted({_label(row["SSP Version"], "SSP Version") for _, row in rows})
        for number, label in enumerate(labels, start=len(self.versions) + 1):
            version_key = f"{SSP_BOOK}@v{number}"
            entries = [
                self._entry(version_key, row)
                for _, row in rows
                if _label(row["SSP Version"], "SSP Version") == label
            ]
            entries.sort(key=lambda entry: (entry.product_code, entry.stratification))
            self.versions[label] = SspVersionInput(
                ssp_book_code=SSP_BOOK,
                version_key=version_key,
                version_no=number,
                resolution_mode="BY_LABEL",
                legacy_version_label=label,
                effective_from_date=None,
                effective_to_date=None,
                status="APPROVED",
                approved_at=datetime.combine(_label_day(label, step), datetime.min.time(), UTC),
                content_sha256=sha256_hex({"label": label, "entries": entries}),
                scope_entity_code=None,
                scope_currency=None,
                scope_channel=None,
                scope_segment=None,
                entries=tuple(entries),
            )

    def _entry(self, version_key: str, row: Row) -> SspEntryInput:
        product = _code(row["SKU Name"], "SKU Name")
        stratification = _code(row["ASC 606 Stratification"], "ASC 606 Stratification")
        flag = _DISTINCT_FLAGS.get(str(row["Distinct or Nondistinct"]))
        if flag is None:
            raise ValueError(f"{product}: SSP_DISTINCT_FLAG_INVALID (DEV-025)")
        list_price = _decimal(row["SKU Unit List Price"], "SKU Unit List Price")
        discount = _decimal(row["Midpoint Discount Percentage"], "Midpoint Discount Percentage")
        spread = _decimal(row["SSP Range Method (+-)"], "SSP Range Method (+-)")
        mid = list_price * (1 - discount)
        if product not in self.products:
            self.products[product] = ProductInput(
                code=product,
                sku_number=_code(row["SKU Unique ID"], "SKU Unique ID"),
                product_family=None,
                revenue_category=None,
                default_template_code=LEGACY_MATERIAL_RIGHT
                if product.startswith(_MATERIAL_RIGHT_PREFIX)
                else None,
                principal_agent="PRINCIPAL",
                distinctness_default=flag,
                unit_of_measure="EA",
                is_bundle=False,
                policy_values={},
                assurance_cost_per_unit=None,
                components=(),
            )
        return SspEntryInput(
            entry_key=f"{version_key}/{product}/{stratification}/-/{CURRENCY}",
            product_code=product,
            stratification=stratification,
            region=None,
            channel=None,
            segment=None,
            deal_size_band=None,
            term_band=None,
            currency=CURRENCY,
            method="legacy_range",
            value_basis="AMOUNT",
            unit_list_price=list_price,
            midpoint_discount_ratio=discount,
            range_ratio=spread,
            cost_basis=None,
            margin_ratio=None,
            distinctness=flag,
            revenue_account_code=_code(row["Revenue Account"], "Revenue Account"),
            observable_point=None,
            ranges=(
                SspRangeInput(
                    "NONE", None, None, None, mid * (1 - spread), mid, mid * (1 + spread)
                ),
            ),
        )

    def setup(self, step: GoldenStep, rows: Sequence[tuple[int, Row]]) -> None:
        """S01-R-06: one CONTRACT_BOOKED per contract; VC rows add an estimate element."""
        mine = [
            row
            for _, row in rows
            if _code(row["Contract Unique Name"], "contract") == self.contract
        ]
        if not mine:
            return
        if self.header is not None:
            raise ValueError(f"{self.contract}: SETUP_CONTRACT_EXISTS")
        inception = min(_day(row["Current Period"], "Current Period") for row in mine)
        entity = _code(mine[0]["Selling Entity"], "Selling Entity")
        lines: list[dict[str, object]] = []
        pinned: list[EstimateVersionInput] = []
        for row in mine:
            key = _code(row["POB Unique ID"], "POB Unique ID")
            product = _code(row["SKU Name"], "SKU Name")
            stratification = _code(row["ASC 606 Stratification"], "ASC 606 Stratification")
            if key in self.obligations:
                raise ValueError(f"{self.contract}: obligation {key} repeats in the setup file")
            price = _decimal(row["Original POB Total Selling Price"], "price")
            line: dict[str, object] = {
                "obligation_key": key,
                "product_code": product,
                "stratification": stratification,
                "quantity": _decimal(row["Original POB Total Qty"], "quantity"),
                "total_price": price,
                "start_date": _day(row["POB Start Date"], "POB Start Date"),
                "end_date": _day(row["POB End Date"], "POB End Date"),
                "performing_entity_code": _code(row["Selling Entity"], "Selling Entity"),
                "ssp_version_label": _label(row["SSP Version"], "SSP Version"),
                "account_overrides": _accounts(row),
                **_memos(row),
            }
            if stratification == "VC":
                pinned.append(self._vc_element(key, price, inception))
            if product.startswith(_MATERIAL_RIGHT_PREFIX):
                self.material_rights.append(_material_right(key))
            self.obligations[key] = product
            self.referenced.add(product)
            lines.append(line)
        self.header = ContractInput(
            external_id=self.contract,
            customer_code=f"LEGACY-{self.contract}",
            related_party_group=None,
            contracting_entity_code=entity,
            transaction_currency=CURRENCY,
            inception_date=inception,
            signature_date=None,
            document_ref=None,
            termination_party=None,
            termination_has_penalty=None,
            termination_notice_days=None,
            has_commercial_substance=True,
            region=None,
            channel=None,
            contract_type=None,
            renewal_of_contract_key=None,
            judgements=(),
            material_rights=(),
            modifications=(),
            noncash_consideration=(),
            consideration_payable=(),
            payment_schedule=(),
            scope_605_35=False,
        )
        payload: dict[str, object] = {
            "contracting_entity_code": entity,
            "transaction_currency": CURRENCY,
            "inception_date": inception,
            "lines": lines,
        }
        keys = [str(line["obligation_key"]) for line in lines]
        self._append(step, "CONTRACT_BOOKED", inception, payload, self.contract, keys)
        for version in pinned:  # the platform applies version 1 on activation (S01-R-18)
            payload = {"estimate_version_id": version.version_key}
            self._append(
                step,
                "ESTIMATE_CHANGED",
                inception,
                payload,
                self.contract,
                (),
                estimate_version_key=version.version_key,
            )
            self.estimates.append(version)

    def _vc_element(self, key: str, price: Decimal, inception: date) -> EstimateVersionInput:
        """S01-R-06: element ``<contract>/VC-<obligation_key>``, ENTERED_AMOUNT, version 1 with the
        signed golden price and no ``direction`` (the L5 parity representation; ENC-VC-direction
        Q-3 keeps the CTR-12 |price| + DECREASE form as a supervisor question)."""
        element = f"VC-{key}"
        estimate_key = obligation_subject_key(self.contract, element)
        version_key = f"{estimate_key}@v1"
        return EstimateVersionInput(
            estimate_key=estimate_key,
            estimate_kind="VARIABLE_CONSIDERATION",
            element_code=element,
            method="ENTERED_AMOUNT",
            vc_element_type=None,
            allocation_target="CONTRACT",
            target_obligation_keys=(),
            obligation_key=None,
            version_key=version_key,
            version_no=1,
            status="APPROVED",
            effective_date=inception,
            scenarios=(),
            parameters={},
            unconstrained_amount=None,
            most_conservative_amount=None,
            constrained_amount=price,
            rate=None,
            expected_total_amount=None,
            expected_quantity=None,
            amortization_months=None,
            currency=CURRENCY,
            supersedes_version_key=None,
            judgement_key=None,
            content_sha256=sha256_hex({"version_key": version_key, "constrained_amount": price}),
        )

    def progress(self, step: GoldenStep, rows: Sequence[tuple[int, Row]]) -> None:
        """S01-R-07 aggregation and S01-R-08 events at the upload date."""
        effective = step.date_input
        if effective is None:
            raise ValueError(f"step {step.number}: a progress upload needs date_input")
        totals: dict[tuple[str, str], list[Decimal]] = {}
        memos: dict[tuple[str, str], dict[str, str]] = {}
        for number, row in rows:
            if _code(row["Contract Unique Name"], "contract") != self.contract:
                continue
            key = (_code(row["POB Unique ID"], "POB"), _code(row["SKU Name"], "SKU Name"))
            sums = totals.setdefault(key, [Decimal(0), Decimal(0), Decimal(0)])
            sums[0] += _amount(row["Current Delivery"], "Current Delivery")
            sums[1] += _amount(row["Current Billing"], "Current Billing")
            sums[2] += _amount(row["Current Pre-ASC606 Revenue (Net Design Only)"], "pre-606")
            latest = memos.setdefault(key, {})
            for column, member in _MEMOS:
                if _blank(row.get(column)):
                    self.warnings.append(("PROGRESS_MEMO_BLANK", step.number, number))
                else:
                    latest[member] = str(row[column])
        for obligation, product in sorted(totals):
            if self.obligations.get(obligation) != product:
                raise ValueError(f"{self.contract} / {obligation} / {product}: unknown key")
            business_key = f"{self.contract} / {obligation} / {product}"
            delivered, billed, pre_standard = totals[(obligation, product)]
            reference = f"golden-{step.number}:{self.contract}:{obligation}"
            keys = (obligation,)
            if delivered > 0:
                payload: dict[str, object] = {
                    "obligation_key": obligation,
                    "quantity": delivered,
                    "trigger": "DELIVERY",
                }
                self._append(step, "DELIVERY_RECORDED", effective, payload, business_key, keys)
            elif delivered < 0:
                payload = {"obligation_key": obligation, "quantity": -delivered}
                self._append(step, "RETURN_RECORDED", effective, payload, business_key, keys)
            if billed > 0:
                payload = {
                    "invoice_number": reference,
                    "line_external_id": reference,
                    "obligation_key": obligation,
                    "amount": billed,
                    "issue_date": effective,
                    "source_invoice_id": reference,
                }
                self._append(step, "BILLING_RECORDED", effective, payload, business_key, keys)
            elif billed < 0:
                payload = {
                    "credit_memo_number": reference,
                    "credited_invoice_number": reference,
                    "obligation_key": obligation,
                    "amount": -billed,
                    "issue_date": effective,
                }
                self._append(step, "CREDIT_MEMO_RECORDED", effective, payload, business_key, keys)
            if pre_standard != 0:
                payload = {"obligation_key": obligation, "amount": pre_standard}
                event_type = "PRE_STANDARD_REVENUE_RECORDED"
                self._append(step, event_type, effective, payload, business_key, keys)
            if memos[(obligation, product)]:
                payload = {"obligation_key": obligation, **memos[(obligation, product)]}
                self._append(step, "MEMO_UPDATED", effective, payload, business_key, keys)

    def modification(self, step: GoldenStep, rows: Sequence[tuple[int, Row]]) -> None:
        """S01-R-09: one modification per contract; CONTRACT_AMENDED after approval."""
        effective, mode = step.date_input, step.mode
        if effective is None or mode is None:
            raise ValueError(f"step {step.number}: a modification upload needs date and mode")
        mine = [
            row
            for _, row in rows
            if _code(row["Contract Unique Name"], "contract") == self.contract
        ]
        if not mine:
            return
        if self.header is None:
            raise ValueError(f"{self.contract}: POB_NOT_FOUND (the contract is not set up)")
        lines: list[dict[str, object]] = []
        added: dict[str, str] = {}
        for row in mine:
            line = self._modification_line(row)
            if line["action"] == "ADD":
                added[str(line["obligation_key"])] = str(line["product_code"])
            lines.append(line)
        self.obligations.update(added)
        treatment = TREATMENTS[mode]
        treatments = {key: treatment for key in sorted(self.obligations)}
        ssp_basis = {
            str(line["obligation_key"]): {
                "is_override": "false",
                "justification": "",
                "ssp_version_key": self._version_key(line.get("ssp_version_label")),
            }
            for line in lines
        }
        modification_key = f"MOD-{step.number}"
        kind = (
            "VC_CHANGE"
            if mode == "pob_price_change"
            else "ADD_OBLIGATION"
            if added
            else "QUANTITY_CHANGE"
        )
        self.modifications.append(
            ModificationInput(
                modification_key=modification_key,
                effective_date=effective,
                kind=kind,
                template_mode=mode,
                status="APPLIED",
                reference=f"golden-{step.number}",
                questionnaire={},
                lines=tuple(lines),
                price_change_amount=None,
                noncash_consideration=None,
                consideration_payable=None,
                scope_605_35=None,
                currency=CURRENCY,
                proposed_treatments={},
                chosen_treatments=treatments,
                treatment_summary=treatment,
                ssp_basis=ssp_basis,
                judgement_key=None,
                content_sha256=sha256_hex({"key": modification_key, "lines": lines}),
            )
        )
        payload: dict[str, object] = {
            "modification_id": modification_key,
            "treatments": treatments,
            "lines": lines,
            "ssp_basis": ssp_basis,
        }
        keys = sorted({str(line["obligation_key"]) for line in lines})
        self._append(
            step,
            "CONTRACT_AMENDED",
            effective,
            payload,
            self.contract,
            keys,
            modification_key=modification_key,
        )

    def _modification_line(self, row: Row) -> dict[str, object]:
        key = _code(row["POB Unique ID"], "POB Unique ID")
        product = _code(row["SKU Name"], "SKU Name")
        quantity = _amount(row["Mod Qty"], "Mod Qty")
        consideration = _amount(row["Mod Billing"], "Mod Billing")
        attributes = (
            "Mod Start Date",
            "Mod End Date",
            "ASC 606 Stratification",
            "Selling Entity",
            "Deferred Revenue Account",
            "Unbilled A/R Account",
            "SSP Version",
        )
        complete = all(not _blank(row.get(name)) for name in attributes)
        label = None if _blank(row.get("SSP Version")) else _label(row["SSP Version"], "SSP")
        stratification = (
            None
            if _blank(row.get("ASC 606 Stratification"))
            else _code(row["ASC 606 Stratification"], "ASC 606 Stratification")
        )
        resolves = self._resolves(label, product, stratification)
        known = key in self.obligations
        adds = not known and quantity > 0 and consideration >= 0 and complete and resolves
        if not adds and not known:
            raise ValueError(f"{self.contract} / {key}: POB_NOT_FOUND")
        line: dict[str, object] = {
            "obligation_key": key,
            "action": "ADD" if adds else "CHANGE",
            "product_code": product,
            "quantity_delta": quantity,
            "consideration_delta": consideration,
        }
        if not _blank(row.get("Mod Start Date")):
            line["start_date"] = _day(row["Mod Start Date"], "Mod Start Date")
        if not _blank(row.get("Mod End Date")):
            line["end_date"] = _day(row["Mod End Date"], "Mod End Date")
        if stratification is not None:
            line["stratification"] = stratification
        if not _blank(row.get("Selling Entity")):
            line["selling_entity_code"] = _code(row["Selling Entity"], "Selling Entity")
        if not _blank(row.get("Deferred Revenue Account")) and not _blank(
            row.get("Unbilled A/R Account")
        ):
            line["account_codes"] = _accounts(row)
        if label is not None:
            line["ssp_version_label"] = label
        line.update(_memos(row))
        self.referenced.add(product)
        return line

    def _resolves(self, label: str | None, product: str, stratification: str | None) -> bool:
        version = None if label is None else self.versions.get(label)
        return version is not None and any(
            entry.product_code == product and entry.stratification == stratification
            for entry in version.entries
        )

    def _version_key(self, label: object) -> str:
        version = self.versions.get(label) if isinstance(label, str) else None
        return "" if version is None else version.version_key

    def _append(
        self,
        step: GoldenStep,
        event_type: str,
        effective: date,
        payload: Mapping[str, object],
        business_key: str,
        obligation_keys: Iterable[str],
        *,
        modification_key: str | None = None,
        estimate_version_key: str | None = None,
    ) -> None:
        """One event with the CV-22 key and the S01-R-03 import idempotency key."""
        sequence = len(self.events) + 1
        position = (step.number, business_key)
        ordinal = self.ordinals[position] = self.ordinals.get(position, 0) + 1
        seed = (
            f"{step.file_sha256}:{step.template_code}:{TEMPLATE_VERSION}:{business_key}:{ordinal}"
        )
        noon = datetime.combine(effective, datetime.min.time(), UTC) + timedelta(hours=12)
        self.events.append(
            EventInput(
                event_key=f"{encode_key(self.contract)}/EV-{sequence:06d}",
                contract_key=self.contract,
                stream_version=sequence,
                event_type=event_type,
                schema_version=1,
                effective_date=effective,
                recorded_at=noon + timedelta(seconds=sequence),
                record_seq=sequence,
                origin=EVENT_ORIGIN,
                is_manual=False,
                obligation_keys=tuple(obligation_keys),
                payload=payload,
                payload_sha256=sha256_hex(payload),
                idempotency_key="imp:" + hashlib.sha256(seed.encode("utf-8")).hexdigest(),
                supersedes_event_key=None,
                modification_key=modification_key,
                estimate_version_key=estimate_version_key,
                manual_adjustment_key=None,
            )
        )

    def result(self, through_step: str) -> GoldenStream:
        if self.header is None:
            raise ValueError(f"{self.contract} is not set up by step {through_step}")
        header = ContractInput(
            **{
                **{name: getattr(self.header, name) for name in ContractInput.__dataclass_fields__},
                "material_rights": tuple(sorted(self.material_rights, key=_obligation_key)),
                "modifications": tuple(
                    sorted(self.modifications, key=lambda item: item.modification_key)
                ),
            }
        )
        missing = sorted(self.referenced - set(self.products))
        if missing:
            raise ValueError(f"{self.contract}: products without an SSP upload row {missing}")
        return GoldenStream(
            contract=self.contract,
            through_step=through_step,
            contracts=(header,),
            ssp_versions=tuple(sorted(self.versions.values(), key=lambda v: v.version_no)),
            events=tuple(
                sorted(self.events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))
            ),
            products=tuple(self.products[code] for code in sorted(self.referenced)),
            estimate_versions=tuple(
                sorted(self.estimates, key=lambda v: (v.estimate_key, v.version_no))
            ),
            warnings=tuple(self.warnings),
        )


def _obligation_key(right: MaterialRightInput) -> str:
    return right.obligation_key


def _material_right(key: str) -> MaterialRightInput:
    """Parity option terms of a legacy material-right line (S03-R-07 ``ENTERED_AMOUNT``)."""
    return MaterialRightInput(
        obligation_key=key,
        option_type="OTHER",
        incremental_discount_ratio=None,
        is_discount_available_without_contract=False,
        expected_purchase_amount=None,
        currency=CURRENCY,
        ssp_method="ENTERED_AMOUNT",
        expiry_date=None,
        likelihood_estimate_key=None,
        is_legacy_quantity_ssp_dollars=True,
    )


def _label_day(label: str, step: GoldenStep) -> date:
    try:
        return date.fromisoformat(label)
    except ValueError:
        return step.date_input or date(2023, 1, 1)
