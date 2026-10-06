"""Answer-key cross-validation, encodings and selection (docs/dev-guide.md §9.5.8 DG-AK-32,
DG-AK-34, DG-AK-35, DG-AK-42; BUILD_SPEC EKC-9)."""

from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import erev_engine
import pytest
import yaml
from erev_engine.canonical import sha256_hex
from pydantic import ValidationError
from support.answer_keys.loader import (
    ANSWER_KEY_ROOT,
    REPO_ROOT,
    SCHEMA_ID,
    AnswerKeyError,
    active_selection,
    cross_validation_findings,
    load,
    load_all,
    selection_from_env,
    selection_is_filtered,
    validate,
)
from support.answer_keys.models import AnswerKey, ConsiderationPayable, ContractLine
from support.answer_keys.runners import _build_checkpoint_bundles
from support.answer_keys.terms import ADD, CHANGE, REMOVE, terms_line_action

Key = dict[str, Any]


@pytest.fixture
def scratch_root() -> Iterator[Path]:
    base = REPO_ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="answer-keys-", dir=base))
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _write_key(root: Path, data: Key, name: str = "rnd/RND-CHK-001.yaml") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _base_key() -> Key:
    """A small valid engine key: one contract, a booking, an invoice and one checkpoint."""
    return {
        "schema": SCHEMA_ID,
        "id": "RND-CHK-001",
        "title": "Synthetic key for the cross-validation tests",
        "status": "active",
        "families": ["RND"],
        "summary": "One product sold for USD 100.00 and invoiced.",
        "authority": {"codification": [], "ifrs": [], "practice": ["synthetic"], "urls": []},
        "derived_from": {"chk": ["CHK-001"]},
        "requirements": ["REQ-ALC-001"],
        "policy_refs": ["POL-002"],
        "review": {
            "author": "loader-test",
            "authored_on": "2026-09-12",
            "reviewer": None,
            "reviewed_on": None,
            "status": "pending",
        },
        "runner": "engine",
        "books": ["ASC606"],
        "world": {
            "tenant": {"reporting_currency": "USD", "preset": "DEFAULT"},
            "currencies": ["USD"],
            "entities": [
                {
                    "code": "US01",
                    "name": "US entity",
                    "functional_currency": "USD",
                    "time_zone": "America/New_York",
                    "calendar": {"pattern": "MONTHLY", "fiscal_year_start_month": "1"},
                    "books": ["ASC606"],
                }
            ],
            "periods": {"from": "2026-01", "to": "2026-12"},
            "gl_accounts": [
                {"code": "2060", "name": "Clearing - billing", "account_type": "LIABILITY"},
                {"code": "2100", "name": "Contract liability", "account_type": "LIABILITY"},
                {"code": "4000", "name": "Revenue", "account_type": "REVENUE"},
            ],
            "account_mapping": [
                {"account_role": "REVENUE", "account": "4000"},
                {"account_role": "CONTRACT_LIABILITY", "account": "2100"},
                {
                    "account_role": "BILLING_CLEARING",
                    "clearing_purpose": "BILLING",
                    "account": "2060",
                },
            ],
            "customers": [{"code": "CUST-1", "name": "Customer"}],
            "pob_templates": [
                {
                    "code": "TPL-PIT",
                    "obligation_kind": "STANDARD",
                    "distinctness": "distinct",
                    "satisfaction_pattern": "POINT_IN_TIME",
                    "over_time_criterion": "NOT_APPLICABLE",
                    "recognition_method": "POINT_IN_TIME",
                }
            ],
            "products": [{"code": "PROD-1", "name": "Product 1", "pob_template": "TPL-PIT"}],
            "policies": {"tenant": {"billing.posting": "ERP"}},
        },
        "contracts": [
            {
                "external_id": "C1",
                "customer": "CUST-1",
                "contracting_entity": "US01",
                "transaction_currency": "USD",
                "inception_date": "2026-01-01",
                "lines": [
                    {
                        "obligation_key": "L1",
                        "product_code": "PROD-1",
                        "quantity": "1",
                        "total_price": "100.00",
                    }
                ],
            }
        ],
        "timeline": [
            {
                "seq": "1",
                "kind": "event",
                "contract": "C1",
                "event_type": "CONTRACT_BOOKED",
                "effective_date": "2026-01-01",
                "payload": {},
            },
            {
                "seq": "2",
                "kind": "event",
                "contract": "C1",
                "event_type": "BILLING_RECORDED",
                "effective_date": "2026-01-15",
                "payload": {
                    "invoice_number": "INV-1",
                    "line_external_id": "1",
                    "amount": "100.00",
                    "issue_date": "2026-01-15",
                },
            },
        ],
        "checkpoints": [
            {
                "name": "after-billing",
                "after_seq": "2",
                "as_of": "2026-01-31",
                "book": "ASC606",
                "contracts": [{"contract": "C1", "version": {"transaction_price": "100.00"}}],
                "subledger": [
                    {
                        "period_key": "FY2026-P01",
                        "entity": "US01",
                        "match": "subset",
                        "lines": [{"account_role": "CONTRACT_LIABILITY", "cr": "100.00"}],
                    }
                ],
            }
        ],
    }


def _seq_gap(key: Key) -> None:
    key["timeline"][1]["seq"] = "3"
    key["checkpoints"][0]["after_seq"] = "3"


def _jpy_amount(key: Key) -> None:
    key["world"]["currencies"].append("JPY")
    key["contracts"][0]["payment_schedule"] = [
        {"date": "2026-01-01", "amount": {"amount": "1200.00", "currency": "JPY"}}
    ]


def _journals_with_engine(key: Key) -> None:
    key["checkpoints"][0]["journals"] = [
        {
            "run": {
                "entity": "US01",
                "period_key": "FY2026-P01",
                "mode": "GROSS",
                "grain": "SUMMARY",
            },
            "match": "subset",
            "lines": [{"account": "2100", "cr": "100.00"}],
        }
    ]


def _tax_lines_and_tax_amount(key: Key) -> None:
    payload = key["timeline"][1]["payload"]
    payload["tax_amount"] = "8.00"
    payload["tax_lines"] = [{"tax_type": "SALES", "amount": "8.00", "principal_or_agent": "AGENT"}]


def _tax_line_jurisdiction(key: Key) -> None:
    key["timeline"][1]["payload"]["tax_lines"] = [
        {"tax_type": "SALES", "jurisdiction": "CA", "amount": "8.00", "principal_or_agent": "AGENT"}
    ]


def _judgement(questionnaire: dict[str, object] | None) -> Callable[[Key], None]:
    def mutate(key: Key) -> None:
        judgement: dict[str, object] = {
            "handle": "J1",
            "topic": "NOT_A_CONTRACT",
            "conclusion": "No contract yet",
        }
        if questionnaire is not None:
            judgement["questionnaire"] = questionnaire
        key["contracts"][0]["judgements"] = [judgement]

    return mutate


def _vc_scenarios(key: Key) -> None:
    key["contracts"][0]["estimates"] = [
        {
            "element_code": "VC1",
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "method": "EXPECTED_VALUE",
            "vc_element_type": "BONUS",
            "obligation_key": "L1",
            "versions": [
                {
                    "version_no": "1",
                    "effective_date": "2026-01-01",
                    "scenarios": [
                        {"outcome": "met", "probability": "0.5", "amount": "10.00"},
                        {"outcome": "missed", "probability": "0.4", "amount": "0.00"},
                    ],
                    "rationale": "Bonus scenarios",
                }
            ],
        }
    ]


def _terms_modification(
    *,
    kind: str = "PRICE_CHANGE",
    obligation_key: str = "L1",
    quantity: str = "0",
    total_price: str = "100.00",
    end_date: str | None = None,
) -> dict[str, Any]:
    """A terms-form modification of C1 effective 2026-01-10 with one line (L1 is booked)."""
    line: dict[str, Any] = {
        "obligation_key": obligation_key,
        "product_code": "PROD-1",
        "quantity": quantity,
        "total_price": total_price,
    }
    if end_date is not None:
        line["end_date"] = end_date
    return {
        "reference": "MOD-1",
        "effective_date": "2026-01-10",
        "kind": kind,
        "lines": [line],
        "price_change_amount": "100.00",
    }


def _with_terms_modification(**members: Any) -> Callable[[Key], None]:
    def mutate(key: Key) -> None:
        key["contracts"][0]["modifications"] = [_terms_modification(**members)]

    return mutate


def _set(path: tuple[str | int, ...], value: object) -> Callable[[Key], None]:
    def mutate(key: Key) -> None:
        node: Any = key
        for token in path[:-1]:
            node = node[token]
        node[path[-1]] = value

    return mutate


# (rule, mutation, file name, JSON Pointer, message fragment)
def _series_entry_without_basis(key: Key) -> None:
    """D-93 (4): a series product's SSP entry must declare its E-49 ``value_basis``; the loader
    refuses an omitted one (fail closed) while an explicit ``AMOUNT`` is the remaining-increments
    reading (dev-guide §9.5.3 `ssp_books`; Codex PRODUCTION-C1B-SERIES-BASIS-77cc618 §3)."""
    world = key["world"]
    world["pob_templates"].append(
        {
            "code": "TPL-SER",
            "obligation_kind": "STANDARD",
            "distinctness": "series",
            "satisfaction_pattern": "OVER_TIME",
            "over_time_criterion": "OT_A",
            "recognition_method": "TIME_ELAPSED",
            "ratable_convention": "MONTHLY_EVEN",
            "series_increment_unit": "month",
        }
    )
    world["products"].append({"code": "PROD-S", "name": "Subscription", "pob_template": "TPL-SER"})
    world["ssp_books"] = [
        {
            "code": "SSP-1",
            "resolution_mode": "EFFECTIVE_DATE",
            "versions": [
                {
                    "effective_from_date": "2025-01-01",
                    "methodology_label": "Observable standalone prices",
                    "entries": [
                        {
                            "product": "PROD-S",
                            "currency": "USD",
                            "method": "observable",
                            "distinctness": "distinct",
                            "ranges": [{"point_value": "1200.00"}],
                        },
                        {
                            "product": "PROD-1",
                            "currency": "USD",
                            "method": "observable",
                            "distinctness": "distinct",
                            "ranges": [{"point_value": "100.00"}],
                        },
                    ],
                }
            ],
        }
    ]


def _series_entry_with_amount(key: Key) -> None:
    _series_entry_without_basis(key)
    key["world"]["ssp_books"][0]["versions"][0]["entries"][0]["value_basis"] = "AMOUNT"


def _per_increment_without_quantity_unit(key: Key) -> None:
    """D-97 (3): a PER_INCREMENT entry declares E-125 ``quantity_unit``; never inferred."""
    _series_entry_without_basis(key)
    key["world"]["ssp_books"][0]["versions"][0]["entries"][0]["value_basis"] = "PER_INCREMENT"


def _per_increment_with_quantity_unit(key: Key, unit: str = "SERVICE_UNITS") -> None:
    _per_increment_without_quantity_unit(key)
    key["world"]["ssp_books"][0]["versions"][0]["entries"][0]["quantity_unit"] = unit


def _amount_with_quantity_unit(key: Key) -> None:
    """D-97 (3): ``quantity_unit`` is meaningful for a PER_INCREMENT entry only."""
    _series_entry_with_amount(key)
    key["world"]["ssp_books"][0]["versions"][0]["entries"][0]["quantity_unit"] = "SERVICE_UNITS"


def _per_increment_units_disagree(key: Key) -> None:
    """Two entries of one product in one book (a second version) declaring different units."""
    _per_increment_with_quantity_unit(key)
    book = key["world"]["ssp_books"][0]
    first = book["versions"][0]
    second = copy.deepcopy(first)
    second["effective_from_date"] = "2026-06-01"
    second["entries"][0]["quantity_unit"] = "INCREMENTS"
    book["versions"].append(second)


CASES: list[tuple[str, Callable[[Key], None], str, str, str]] = [
    ("series entry without value_basis", _series_entry_without_basis, "rnd/RND-CHK-001.yaml",
     "/world/ssp_books/0/versions/0/entries/0/value_basis", "declares no `value_basis`"),
    ("PER_INCREMENT entry without quantity_unit", _per_increment_without_quantity_unit,
     "rnd/RND-CHK-001.yaml", "/world/ssp_books/0/versions/0/entries/0/quantity_unit",
     "declares no `quantity_unit`"),
    ("quantity_unit disagrees within a book", _per_increment_units_disagree,
     "rnd/RND-CHK-001.yaml", "/world/ssp_books/0/versions/1/entries/0/quantity_unit",
     "disagrees with"),
    ("quantity_unit with another basis", _amount_with_quantity_unit, "rnd/RND-CHK-001.yaml",
     "/world/ssp_books/0/versions/0/entries/0/quantity_unit", "meaningful for a PER_INCREMENT"),
    ("path family", lambda key: None, "ssp/RND-CHK-001.yaml", "/families/0", "directory 'ssp'"),
    ("seq gap", _seq_gap, "rnd/RND-CHK-001.yaml", "/timeline/1/seq", "breaks the sequence"),
    ("unknown after_seq", _set(("checkpoints", 0, "after_seq"), "7"), "rnd/RND-CHK-001.yaml",
     "/checkpoints/0/after_seq", "names no timeline item"),
    ("unresolved handle", _set(("contracts", 0, "lines", 0, "product_code"), "PROD-9"),
     "rnd/RND-CHK-001.yaml", "/contracts/0/lines/0/product_code",
     "product 'PROD-9' does not resolve"),
    ("unknown E-01 literal", _set(("world", "account_mapping", 0, "account_role"), "SALES_REVENUE"),
     "rnd/RND-CHK-001.yaml", "/world/account_mapping/0/account_role", "`account_role` literal"),
    ("unknown POL key", _set(("world", "policies", "tenant"), {"billing.postings": "ERP"}),
     "rnd/RND-CHK-001.yaml", "/world/policies/tenant/billing.postings", "unknown policy key"),
    ("unknown REQ id", _set(("requirements",), ["REQ-ALC-999"]), "rnd/RND-CHK-001.yaml",
     "/requirements/0", "requirement 'REQ-ALC-999'"),
    ("CHK absent from id", _set(("derived_from", "chk"), ["CHK-004"]), "rnd/RND-CHK-001.yaml",
     "/derived_from/chk/0", "not contained in the id"),
    ("JPY amount places", _jpy_amount, "rnd/RND-CHK-001.yaml",
     "/contracts/0/payment_schedule/0/amount/amount", "JPY has 0"),
    ("journals with engine runner", _journals_with_engine, "rnd/RND-CHK-001.yaml",
     "/checkpoints/0/journals", "only with runner platform"),
    ("reserved role in subledger",
     _set(("checkpoints", 0, "subledger", 0, "lines", 0, "account_role"), "RETAINED_EARNINGS"),
     "rnd/RND-CHK-001.yaml", "/checkpoints/0/subledger/0/lines/0/account_role", "reserved role"),
    ("clearing_purpose on REVENUE",
     _set(("world", "account_mapping", 0, "clearing_purpose"), "BILLING"),
     "rnd/RND-CHK-001.yaml", "/world/account_mapping/0/clearing_purpose", "not REVENUE"),
    ("tax_lines with tax_amount", _tax_lines_and_tax_amount, "rnd/RND-CHK-001.yaml",
     "/timeline/1/payload/tax_amount", "never appear in one payload"),
    ("tax line jurisdiction", _tax_line_jurisdiction, "rnd/RND-CHK-001.yaml",
     "/timeline/1/payload/tax_lines/0/jurisdiction", "tax lines carry exactly"),
    ("questionnaire member not listed",
     _judgement({"consideration_nonrefundable": True, "credit_grade": "A"}), "rnd/RND-CHK-001.yaml",
     "/contracts/0/judgements/0/questionnaire/credit_grade", "lists no member 'credit_grade'"),
    ("NOT_A_CONTRACT without questionnaire", _judgement(None), "rnd/RND-CHK-001.yaml",
     "/contracts/0/judgements/0/questionnaire", "consideration_nonrefundable"),
    ("positive expected_returns_amount",
     _set(("checkpoints", 0, "contracts", 0, "version", "expected_returns_amount"), "300.00"),
     "rnd/RND-CHK-001.yaml", "/checkpoints/0/contracts/0/version/expected_returns_amount",
     "is positive"),
    ("scenario probabilities", _vc_scenarios, "rnd/RND-CHK-001.yaml",
     "/contracts/0/estimates/0/versions/0/scenarios", "sum to 0.9"),
    ("terms-form CHANGE line removing every unit priced", _with_terms_modification(),
     "rnd/RND-CHK-001.yaml", "/contracts/0/modifications/0/lines/0/quantity",
     "removal of every unit prices 0"),
]  # fmt: skip


def test_cross_validation_rules(scratch_root: Path) -> None:
    base = _write_key(scratch_root, _base_key())
    assert load(base).key.id == "RND-CHK-001"
    base.unlink()

    for rule, mutate, name, pointer, fragment in CASES:
        data = _base_key()
        mutate(data)
        path = _write_key(scratch_root, data, name)
        findings = cross_validation_findings(validate(data, path=path), path)
        assert [finding.pointer for finding in findings] == [pointer], (rule, findings)
        with pytest.raises(AnswerKeyError) as raised:
            load(path)
        assert raised.value.path == path, rule
        assert raised.value.pointer == pointer, (rule, raised.value.message)
        assert fragment in raised.value.message, (rule, raised.value.message)
        path.unlink()

    # D-93 (4): an explicit AMOUNT on the series entry (and the non-series entry's omitted basis,
    # the T-REF-30 default) load; only the omitted series basis is refused.
    for mutate in (_series_entry_with_amount, _per_increment_with_quantity_unit):
        data = _base_key()
        mutate(data)
        declared = _write_key(scratch_root, data)
        assert cross_validation_findings(validate(data, path=declared), declared) == []
        assert load(declared).key.id == "RND-CHK-001"
        declared.unlink()

    # DG-AK-04 rev 1.2: the containment check is case-insensitive.
    data = _base_key()
    data["id"] = "RND-CHK-003A"
    data["derived_from"]["chk"] = ["CHK-003a"]
    assert load(_write_key(scratch_root, data, "rnd/RND-CHK-003A.yaml")).key.id == "RND-CHK-003A"


CORRECTED_DISC = (
    ANSWER_KEY_ROOT / "disc" / "DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION.yaml"
)


def _compiled(loaded: Any, *, compute: bool) -> tuple[str, ...]:
    """Digests of every checkpoint bundle of ``loaded`` and, with ``compute``, of its output."""
    digest: list[str] = []
    for checkpoint in _build_checkpoint_bundles(loaded):
        for bundle in checkpoint.bundles:
            digest.append(sha256_hex(bundle))
            if compute:
                digest.append(sha256_hex(erev_engine.compute(bundle)))
    assert digest
    return tuple(digest)


def test_dg_ak_59_notes_are_documentary(scratch_root: Path) -> None:
    """DG-AK-59 (D-97 (2) v3): ``notes`` is an optional top-level member — absent, ``[]`` and a list
    of strings load; a scalar, ``null``, a mapping, non-string elements and an unknown member are
    refused — and the compiled ``InputBundle`` and every calculation are identical with and
    without it (the raw source hash may change)."""
    accepted: dict[str, list[str] | None] = {
        "absent": None,
        "empty": [],
        "strings": [
            "The world input is authored as ruled by D-97 (1); the oracle is unchanged.",
            "",
        ],
    }
    compiled: set[tuple[str, ...]] = set()
    for name, notes in accepted.items():
        data = _base_key()
        if notes is not None:
            data["notes"] = notes
        path = _write_key(scratch_root, data)
        assert cross_validation_findings(validate(data, path=path), path) == [], name
        loaded = load(path)
        assert loaded.key.notes == tuple(notes or ()), name
        compiled.add(_compiled(loaded, compute=False))
        path.unlink()
    assert len(compiled) == 1  # identical compiled bundles across the three variants
    # The corrected DISC-CATCH-UP key (its notes cite D-97 (1)) computes identically without notes
    # and with empty notes: canonical bundle and engine output digests.
    source = yaml.safe_load(CORRECTED_DISC.read_text(encoding="utf-8"))
    assert source["notes"]
    outputs: set[tuple[str, ...]] = {_compiled(load(CORRECTED_DISC), compute=True)}
    for notes in (None, []):
        variant = copy.deepcopy(source)
        variant.pop("notes")
        if notes is not None:
            variant["notes"] = notes
        path = _write_key(scratch_root, variant, f"disc/{CORRECTED_DISC.name}")
        outputs.add(_compiled(load(path), compute=True))
        path.unlink()
    assert len(outputs) == 1  # identical bundles and calculations with and without notes
    data = _base_key()  # DG-AK-31: a YAML scalar element is a string, so [1] loads as ("1",)
    data["notes"] = [1]
    assert load(_write_key(scratch_root, data)).key.notes == ("1",)
    with pytest.raises(ValidationError):  # the model itself takes strings only
        AnswerKey.model_validate(data)
    rejected: dict[str, object] = {
        "scalar": "text",
        "null": None,
        "mapping": {"a": "b"},
        "mapping element": [{"a": "b"}],
        "nested list": [["x"]],
        "boolean element": [True],
    }
    for name, notes in rejected.items():
        data = _base_key()
        data["notes"] = notes
        path = _write_key(scratch_root, data)
        with pytest.raises(AnswerKeyError) as raised:
            load(path)
        assert raised.value.pointer.startswith("/notes"), (name, raised.value.pointer)
        path.unlink()
    data = _base_key()
    data["note"] = ["unknown member"]
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, data))
    assert (raised.value.pointer, "Extra inputs" in raised.value.message) == ("/note", True)


# (control, terms-form modification members, the action the conversion gives the line)
GUARD_CONTROLS: list[tuple[str, dict[str, Any], str]] = [
    ("ADD on a new line", {"obligation_key": "L2"}, ADD),
    ("REMOVE_OBLIGATION", {"kind": "REMOVE_OBLIGATION"}, REMOVE),
    ("TERMINATION", {"kind": "TERMINATION"}, REMOVE),
    ("PRICE_CHANGE with end_date before the effective date", {"end_date": "2026-01-09"}, REMOVE),
    ("zero-price CHANGE", {"total_price": "0.00"}, CHANGE),
    ("malformed quantity (pre-existing admission)", {"quantity": "not-a-number"}, CHANGE),
    ("malformed price NaN (pre-existing admission)", {"total_price": "NaN"}, CHANGE),
]


@pytest.mark.parametrize(
    ("control", "members", "action"), GUARD_CONTROLS, ids=[item[0] for item in GUARD_CONTROLS]
)
def test_dg_ak_terms_form_guard_is_change_only(
    scratch_root: Path, control: str, members: dict[str, Any], action: str
) -> None:
    """D-97 (1c) v3 (Codex loader review of 4a42914): the guard refuses only a terms-form line the
    conversion reads as CHANGE with quantity 0 and a non-zero finite total_price; ADD, REMOVE and
    TERMINATION lines, zero-price lines and malformed numbers load as before (the two malformed
    admissions are a pre-existing boundary, recorded, not widened here)."""
    modification = _terms_modification(**members)
    line = ContractLine.model_validate(modification["lines"][0])
    classified = terms_line_action(
        modification["kind"],
        line,
        in_force=line.obligation_key == "L1",
        effective_date=date(2026, 1, 10),
    )
    assert classified == action, control
    data = _base_key()
    _with_terms_modification(**members)(data)
    path = _write_key(scratch_root, data)
    assert cross_validation_findings(validate(data, path=path), path) == [], control
    assert load(path).key.id == "RND-CHK-001", control


def test_dg_ak_terms_form_guard_negative_is_a_change_line() -> None:
    """The CASES negative (quantity "0", total_price 100.00 on booked L1 under PRICE_CHANGE) is
    the CHANGE line the guard targets, classified by the same function."""
    negative = ContractLine.model_validate(_terms_modification()["lines"][0])
    assert (
        terms_line_action("PRICE_CHANGE", negative, in_force=True, effective_date=date(2026, 1, 10))
        == CHANGE
    )


NEGATIVE_CONTROL = (
    Path(__file__).parent
    / "negative"
    / "disc"
    / "DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION.yaml"
)
NEGATIVE_CONTROL_SHA256 = "89755696abde70c676bc1ffdcfffcded2ab34fbb02395bad0b7e2d89f4430022"


def test_disc_catch_up_original_bytes_are_the_guard_negative_control() -> None:
    """D-97 (1) v3: the original DISC-CATCH-UP bytes (before the input correction of c45b2f7) are
    kept as the loader rule's negative control, outside the corpus: refused at the exact line
    pointer; the corrected key under docs/ is the input-corrected publication."""
    assert hashlib.sha256(NEGATIVE_CONTROL.read_bytes()).hexdigest() == NEGATIVE_CONTROL_SHA256
    with pytest.raises(AnswerKeyError) as raised:
        load(NEGATIVE_CONTROL)
    assert raised.value.pointer == "/contracts/0/modifications/0/lines/0/quantity"
    assert "removal of every unit prices 0" in raised.value.message
    corrected = load(
        ANSWER_KEY_ROOT / "disc" / "DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION.yaml"
    )
    (line,) = corrected.key.contracts[0].modifications[0].lines
    assert isinstance(line, ContractLine)
    assert (line.quantity, str(line.total_price)) == ("1", "20000.00")
    assert any("D-97 (1)" in note for note in corrected.key.notes)


def _expected_purchases_key(*, committed: bool = False, constrained: str = "1500000.00") -> Key:
    data = _base_key()
    contract = data["contracts"][0]
    contract["lines"][0]["total_price"] = "15000000.00"
    contract["estimates"] = [
        {
            "element_code": "SHELF-1",
            "estimate_kind": "EXPECTED_PURCHASES",
            "method": "ENTERED_AMOUNT",
            "obligation_key": "L1",
            "versions": [
                {
                    "version_no": "1",
                    "effective_date": "2026-01-01",
                    "unconstrained_amount": "1500000.00",
                    "constrained_amount": constrained,
                    "expected_total_amount": "15000000.00",
                    "rationale": "Nonrefundable shelving payment",
                }
            ],
        }
    ]
    if committed:
        contract["policy_overrides"] = [
            {
                "policy_key": "cpc.incentive_asset_release_basis",
                "value": "COMMITTED_PURCHASES",
                "rationale": "Committed minimum purchases",
            }
        ]
    return data


def test_dg_ak_34_consideration_payable_mapping(scratch_root: Path) -> None:
    loaded = load(_write_key(scratch_root, _expected_purchases_key()))
    contract = loaded.key.contracts[0]
    assert contract.consideration_payable == (
        ConsiderationPayable(
            amount="1500000.00",
            promise_date="2026-01-01",
            related_obligation_keys=("L1",),
            distinct_good_fair_value=None,
            committed_purchases=None,
            share_based=False,
        ),
    )
    assert contract.estimates is not None
    version = contract.estimates[0].versions[0]
    assert (version.unconstrained_amount, version.constrained_amount) == (None, None)
    assert version.expected_total_amount == "15000000.00"

    committed = load(_write_key(scratch_root, _expected_purchases_key(committed=True)))
    payable = committed.key.contracts[0].consideration_payable
    assert payable is not None and payable[0].committed_purchases == "15000000.00"

    partial = load(_write_key(scratch_root, _expected_purchases_key(constrained="1000000.00")))
    payable = partial.key.contracts[0].consideration_payable
    assert payable is not None and payable[0].distinct_good_fair_value == "500000.00"

    changed = _expected_purchases_key()
    versions = changed["contracts"][0]["estimates"][0]["versions"]
    versions.append(
        {
            **versions[0],
            "version_no": "2",
            "effective_date": "2026-03-01",
            "unconstrained_amount": "1600000.00",
        }
    )
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, changed))
    assert raised.value.pointer == "/contracts/0/estimates/0/versions/1/unconstrained_amount"
    assert "DG-AK-34" in raised.value.message

    both = _expected_purchases_key()
    both["contracts"][0]["consideration_payable"] = [
        {
            "amount": "1500000.00",
            "promise_date": "2026-01-01",
            "related_obligation_keys": ["L1"],
            "share_based": False,
        }
    ]
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, both))
    assert raised.value.pointer == "/contracts/0/consideration_payable"


def _report_key(cells: list[dict[str, str]], entity_codes: list[str]) -> Key:
    data = _base_key()
    data["runner"] = "platform"
    data["checkpoints"][0]["reports"] = [
        {
            "report_code": "rpo",
            "parameters": {
                "entity_codes": entity_codes,
                "book": "ASC606",
                "period_key": "FY2026-P12",
            },
            "cells": cells,
        }
    ]
    return data


def test_dg_ak_35_report_row_keys(scratch_root: Path) -> None:
    cells = [
        {"row_key": "C1", "column_key": "within_12_months", "value": "100.00"},
        {"row_key": "TOTAL", "column_key": "total", "value": "100.00"},
        {"row_key": "US01", "column_key": "total", "value": "100.00"},
        {"row_key": "contract:C1", "column_key": "months_13_to_24", "value": "0.00"},
    ]
    loaded = load(_write_key(scratch_root, _report_key(cells, ["US01"])))
    reports = loaded.key.checkpoints[0].reports
    assert reports is not None
    assert [cell.row_key for cell in reports[0].cells] == [
        "contract:C1",
        "TOTAL:USD",
        "entity:US01",
        "contract:C1",
    ]

    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, _report_key(cells, ["US01", "GB01"])))
    assert raised.value.pointer == "/checkpoints/0/reports/0/cells/2/row_key"
    assert "entity_codes" in raised.value.message

    both = _report_key([{"row_key": "US01", "column_key": "total", "value": "100.00"}], ["US01"])
    both["contracts"][0]["external_id"] = "US01"
    for item in both["timeline"]:
        item["contract"] = "US01"
    both["checkpoints"][0]["contracts"][0]["contract"] = "US01"
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, both))
    assert raised.value.pointer == "/checkpoints/0/reports/0/cells/0/row_key"
    assert "both a contract handle and an entity code" in raised.value.message

    columns = _report_key(
        [{"row_key": "C1", "column_key": "bucket_0_30", "value": "1.00"}], ["US01"]
    )
    with pytest.raises(AnswerKeyError) as raised:
        load(_write_key(scratch_root, columns))
    assert raised.value.pointer == "/checkpoints/0/reports/0/cells/0/column_key"


def test_load_all_collects_every_error(scratch_root: Path) -> None:
    unknown_requirement = _base_key()
    unknown_requirement["requirements"] = ["REQ-ALC-999"]
    first = _write_key(scratch_root, unknown_requirement)
    gap = _base_key()
    gap["id"] = "RND-CHK-002"
    gap["derived_from"]["chk"] = ["CHK-002"]
    _seq_gap(gap)
    second = _write_key(scratch_root, gap, "rnd/RND-CHK-002.yaml")

    with pytest.raises(ExceptionGroup) as raised:
        load_all(root=scratch_root)
    errors = raised.value.exceptions
    assert len(errors) == 2
    assert all(isinstance(error, AnswerKeyError) for error in errors)
    assert {
        (error.path, error.pointer) for error in errors if isinstance(error, AnswerKeyError)
    } == {
        (first, "/requirements/0"),
        (second, "/timeline/1/seq"),
    }


def test_selection_from_env() -> None:
    families = selection_from_env({"FAMILY": "RND"})
    assert families == {"families": ("RND",), "ids": (), "requirements": ()}
    selected = load_all(**families)
    assert len(selected) == 25
    assert {item.path.parent for item in selected} == {ANSWER_KEY_ROOT / "rnd"}
    assert {item.key.status for item in selected} == {"active"}

    ids = selection_from_env({"ID": "RND-CHK-001, SSP-CHK-035-TC-SETUP"})
    assert sorted(item.key.id for item in load_all(**ids)) == [
        "RND-CHK-001",
        "SSP-CHK-035-TC-SETUP",
    ]

    requirement = selection_from_env({"REQ": "REQ-REC-019"})
    chosen = {item.key.id for item in load_all(**requirement)}
    expected = {item.key.id for item in load_all() if "REQ-REC-019" in item.key.requirements}
    assert chosen == expected and chosen

    # DG-AK-42: a filtered selection disables the coverage check.
    assert all(selection_is_filtered(selection) for selection in (families, ids, requirement))
    assert not selection_is_filtered(selection_from_env({}))
    with pytest.raises(ValueError, match="RND-CHK-999"):
        load_all(ids=("RND-CHK-999",))


def test_dg_ak_13_withdrawn_ids_are_never_collected() -> None:
    mixed = active_selection({"ID": "RND-CHK-001,POS-S9-PRESENTATION-EX38-CASEA"})
    assert [item.key.id for item in mixed] == ["RND-CHK-001"]
    assert active_selection({"ID": "POS-S9-PRESENTATION-EX38-CASEA"}) == []
    with pytest.raises(ValueError, match="NO-SUCH-KEY"):
        active_selection({"ID": "NO-SUCH-KEY"})


def test_corpus_cross_validates() -> None:
    # 243 + eight ENG-D1 + three ENG-C6 keys (D-91, D-97) + one of R-116 (a)
    assert len(load_all(include_withdrawn=True)) == 255
    active = load_all()
    assert len(active) == 253
    assert {item.key.status for item in active} == {"active"}
    assert copy.deepcopy(active[0].key) == active[0].key
