"""CV-21 canonical identity of the engine's lookups (ENGINE_SPEC CV-21 rev 1.23; D-98 candidate 76;
ENG-COST-ENC-1, Codex PRODUCTION-F-RPS-STAGE11-REVIEW-0937e17).

Stage 01 indexes the estimate pins by the CV-21 encoded element key
``<encoded external id>/<encoded element code>``; stage 11 filtered that index with the RAW
contract key (``key.startswith(f"{contract_key}/")``), so a contract whose id carries ``/`` never
found its approved ``RENEWAL_EXPECTATION`` and amortised over the contract term. The fix keys every
pin lookup on ``EstimatePins.of_contract`` (the encoded prefix) and refuses an unencoded index entry
by name. No database; the answer-key file is read, never modified.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import date

import pytest
from erev_engine import compute
from erev_engine.errors import EngineError
from erev_engine.money import format_money
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s11_costs_loss import capitalise, impair, loss
from erev_engine.stages.s14_posting import RoleKey
from erev_engine.stages.s14_posting.accounts import missing
from erev_engine.stages.state import EstimatePin, EstimatePins, malformed_estimate_key
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.models import AnswerKey
from support.answer_keys.runners import _Assembler
from support.recognition import allocated_state, book_context, contract_view, estimate_version

ENCODED_ID = "C-COST/2"  # the Codex relabel: its encoded form is C-COST%2F2
JANUARY = date(2026, 1, 1)


def _pins(*versions) -> EstimatePins:
    grouped: dict[str, list[EstimatePin]] = {}
    for seq, version in enumerate(versions, start=1):
        order_key = (version.effective_date, seq, f"{encode_key(ENCODED_ID)}/EV-{seq:06d}")
        grouped.setdefault(version.estimate_key, []).append(EstimatePin(version, order_key))
    return EstimatePins({key: tuple(pins) for key, pins in grouped.items()})


def _renewal(months: int):
    version = estimate_version(
        f"{encode_key(ENCODED_ID)}/AMORT-PERIOD", "RENEWAL_EXPECTATION", 1, JANUARY
    )
    return dataclasses.replace(version, amortization_months=months)


def test_of_contract_lists_the_encoded_elements_of_the_contract_only() -> None:
    """``EstimatePins.of_contract`` keys on ``<encoded external id>/``: the elements of
    ``C-COST/2`` are the ``C-COST%2F2/…`` keys, not those of a contract ``C-COST`` (whose element
    ``2`` would read ``C-COST/2``) nor of ``C-COST-2``."""
    a = estimate_version(
        f"{encode_key(ENCODED_ID)}/AMORT-PERIOD", "RENEWAL_EXPECTATION", 1, JANUARY
    )
    b = estimate_version(f"{encode_key(ENCODED_ID)}/EAC", "EAC", 1, JANUARY)
    c = estimate_version("C-COST/2", "EAC", 1, JANUARY)  # contract C-COST, element 2
    d = estimate_version("C-COST-2/AMORT-PERIOD", "RENEWAL_EXPECTATION", 1, JANUARY)
    pins = _pins(a, b, c, d)
    assert pins.of_contract(ENCODED_ID) == ("C-COST%2F2/AMORT-PERIOD", "C-COST%2F2/EAC")
    assert pins.of_contract("C-COST") == ("C-COST/2",)
    assert pins.of_contract("C-COST-2") == ("C-COST-2/AMORT-PERIOD",)
    assert pins.of_contract("C-OTHER") == ()


def test_of_contract_refuses_an_unencoded_index_entry_by_name() -> None:
    """An index entry with a second unencoded separator is not a CV-21 element key: the lookup
    refuses it by name (rule CV-21, with the structural reason) instead of silently skipping it."""
    raw = estimate_version("C-COST/2/AMORT-PERIOD", "RENEWAL_EXPECTATION", 1, JANUARY)
    pins = _pins(raw)
    with pytest.raises(EngineError) as refused:
        pins.of_contract(ENCODED_ID)
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.detail == {
        "rule": "CV-21",
        "estimate_key": "C-COST/2/AMORT-PERIOD",
        "contract_key": ENCODED_ID,
        "reason": "the key is not <head>/<element> (one separator)",
    }
    assert refused.value.subject_key == "C-COST%2F2"


def test_stage_11_lookups_find_the_encoded_contracts_estimates() -> None:
    """``renewal_versions`` (S11-R-04 amortisation period), ``impair._eac`` (S11-R-09) and
    ``loss._has_eac`` (POL-151) all resolve the estimates of ``C-COST/2`` through the encoded
    index; before the fix each raw-prefix scan returned nothing for this contract."""
    renewal = _renewal(84)
    eac = dataclasses.replace(
        estimate_version(f"{encode_key(ENCODED_ID)}/EAC", "EAC", 1, JANUARY),
        expected_total_amount=__import__("decimal").Decimal("55000.00"),
    )
    st = allocated_state([], contracts=[contract_view(ENCODED_ID)], estimates=_pins(renewal, eac))
    versions = capitalise.renewal_versions(st, ENCODED_ID)
    assert [v.amortization_months for v in versions] == [84]
    assert capitalise.renewal_at(versions, date(2026, 1, 15)) is renewal
    total, found = impair._eac(st, ENCODED_ID, [], date(2026, 1, 31), 2)
    assert (total, [v.estimate_key for v in found]) == (5500000, ["C-COST%2F2/EAC"])
    assert loss._has_eac(st, ENCODED_ID, date(2026, 1, 31))
    assert not loss._has_eac(st, "C-COST-2", date(2026, 1, 31))
    assert capitalise.renewal_versions(st, "C-COST-2") == ()


def test_account_mapping_missing_names_the_encoded_contract() -> None:
    """S14-R-14: the ``ACCOUNT_MAPPING_MISSING`` detail names the contract of a
    ``<encoded id>@<entity>`` subject; the raw ``external_id@`` prefix never matched an encoded id
    and the finding fell back to the group code."""
    ctx = book_context()
    st = allocated_state([], contracts=[contract_view("C/1")])
    key = RoleKey(
        "ASC606",
        bundles.ENTITY_CODE,
        f"C%2F1@{bundles.ENTITY_CODE}",
        "REVENUE_RECOGNITION",
        "CONTRACT_LIABILITY",
        None,
        None,
    )
    finding = missing(ctx, st, None, key)
    assert finding.code == "ACCOUNT_MAPPING_MISSING"
    assert finding.detail["contract"] == "C/1"


# --- ENG-COST-ENC-1: Codex's three retained worlds, natively ------------------------------

_KEY = ANSWER_KEY_ROOT / "cost" / "COST-S8-CONTRACT-COSTS-EX2.yaml"


def _relabel(value):
    if isinstance(value, dict):
        return {k: _relabel(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_relabel(v) for v in value]
    if isinstance(value, str) and "C-COST-2" in value:
        return value.replace("C-COST-2", ENCODED_ID)
    return value


def _first_checkpoint(data) -> tuple[str, str, tuple[str, ...]]:
    """(P01 cost carrying, P01 amortisation debit, estimate keys) of the first checkpoint of the
    world ``data`` (an AnswerKey model dump); the key file itself is never written."""
    original = load(_KEY)
    loaded = dataclasses.replace(original, key=AnswerKey.model_validate(data))
    checkpoint = _Assembler(loaded).checkpoints()[0]
    assert checkpoint.name == "end-of-january-2026"
    (bundle,) = checkpoint.bundles
    output = compute(bundle)
    book = next(b for b in output.books if b.book_code == checkpoint.book)
    carrying = sum(
        int(b.columns["cost_asset_carrying_txn"])
        for b in book.balances
        if b.period_key == "FY2026-P01"
    )
    amortisation = sum(
        line.amount_txn
        for intent in book.posting_intents
        if intent.posting_period_key == "FY2026-P01"
        and intent.entry_kind == "CONTRACT_COST_AMORTIZATION"
        for line in intent.lines
        if line.side == "D"
    )
    keys = tuple(sorted(v.estimate_key for v in bundle.estimate_versions))
    return format_money(carrying, 2), format_money(amortisation, 2), keys


def test_enc1_three_retained_worlds_amortise_over_the_approved_renewal() -> None:
    """The unmodified COST-S8-CONTRACT-COSTS-EX2 first checkpoint (contract ``C-COST-2``), the
    identity-only relabel ``C-COST/2`` (single entity, every financial and estimate input kept)
    and the relabel plus a supplemental US02 performer all carry 148,214.28 at P01 with the
    first-month amortisation 1,785.72 (the approved 84-month RENEWAL_EXPECTATION). Before the fix
    worlds 2 and 3 carried 147,499.99 (amortisation 2,500.01: the 60-month contract term) because
    the raw prefix ``C-COST/2/`` never matched the pin ``C-COST%2F2/AMORT-PERIOD``. The original
    expected amount is unchanged."""
    base = copy.deepcopy(load(_KEY).key.model_dump(mode="json", by_alias=True))
    encoded = _relabel(copy.deepcopy(base))
    with_performer = copy.deepcopy(encoded)
    us01 = next(e for e in with_performer["world"]["entities"] if e["code"] == "US01")
    with_performer["world"]["entities"].append({**us01, "code": "US02", "name": "US02 performer"})
    for contract in with_performer["contracts"]:
        for line in contract["lines"]:
            line["performing_entity_code"] = "US02"
    original = _first_checkpoint(base)
    relabelled = _first_checkpoint(encoded)
    performer = _first_checkpoint(with_performer)
    assert original == ("148214.28", "1785.72", ("C-COST-2/AMORT-PERIOD",))
    assert relabelled == ("148214.28", "1785.72", ("C-COST%2F2/AMORT-PERIOD",))
    assert performer == ("148214.28", "1785.72", ("C-COST%2F2/AMORT-PERIOD",))


# --- ENG-COST-LOOKUP-R1: raw-prefix overlap is not malformedness -------------------------------


def test_of_contract_selects_only_its_own_contract_when_raw_prefixes_overlap() -> None:
    """Raw ids ``C/2`` (encoded ``C%2F2``) and ``C%2F2`` (a literal percent sequence, encoded
    ``C%252F2``) are distinct contracts. With both keys present each lookup returns exactly its own
    key: the well-formed ``C%2F2/EAC`` sits under the raw prefix ``C%2F2/`` of the second id but is
    the first contract's valid key, never a malformed entry (Codex key-only supplement 4/6 on
    e976cc8c)."""
    slash = estimate_version("C%2F2/EAC", "EAC", 1, JANUARY)  # raw C/2
    percent = estimate_version("C%252F2/EAC", "EAC", 1, JANUARY)  # raw C%2F2
    pins = _pins(slash, percent)
    assert encode_key("C/2") == "C%2F2" and encode_key("C%2F2") == "C%252F2"
    assert pins.of_contract("C/2") == ("C%2F2/EAC",)
    assert pins.of_contract("C%2F2") == ("C%252F2/EAC",)
    assert pins.of_contract("C") == ()


def test_of_contract_refuses_a_structurally_malformed_entry_by_name() -> None:
    """The control: ``C/2/EAC`` carries an unencoded separator (three parts) and is malformed for
    any contract — refused by name with the entry and the requested contract; a well-formed key of
    the same index is unaffected. Malformedness is the entry's structure, not prefix overlap."""
    malformed = estimate_version("C/2/EAC", "EAC", 1, JANUARY)
    valid = estimate_version("C%2F2/AMORT", "RENEWAL_EXPECTATION", 1, JANUARY)
    pins = _pins(malformed, valid)
    with pytest.raises(EngineError) as refused:
        pins.of_contract("C/2")
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.detail["estimate_key"] == "C/2/EAC"
    assert refused.value.detail["contract_key"] == "C/2"
    assert refused.value.detail["rule"] == "CV-21"
    # Other unencoded separators and a bad escape are malformed too; the PORTFOLIO marker is not.
    for key in ("C@1/EAC", "C#1/EAC", "C:1/EAC", "C%2G/EAC", "/EAC", "C%2F2/"):
        with pytest.raises(EngineError):
            _pins(estimate_version(key, "EAC", 1, JANUARY)).of_contract("C/2")
    portfolio = _pins(estimate_version("PORTFOLIO:P-1/RETURN_RATE", "RETURN_RATE", 1, JANUARY))
    assert portfolio.of_contract("C/2") == ()


def test_of_contract_treats_a_lowercase_escape_token_as_malformed() -> None:
    """ENG-COST-LOOKUP-R1a: CV-21 encoding is canonical uppercase (``encode_key("C/2") ==
    "C%2F2"``); the validator compares case-sensitively, so a stored key carrying a lowercase
    escape token (``C%2f2/EAC``) is malformed — refused by name with the same fields — and is never
    normalised into acceptance or selected for ``C/2``."""
    assert encode_key("C/2") == "C%2F2" and encode_key("a@b#c:d%") == "a%40b%23c%3Ad%25"
    lower = estimate_version("C%2f2/EAC", "EAC", 1, JANUARY)
    with pytest.raises(EngineError) as refused:
        _pins(lower).of_contract("C/2")
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.detail["estimate_key"] == "C%2f2/EAC"
    assert refused.value.detail["contract_key"] == "C/2"
    assert refused.value.detail["rule"] == "CV-21"
    assert refused.value.detail["reason"] == "an escape other than %25 %2F %40 %23 %3A"
    for key in ("C%2f2/EAC", "C%4Ax/EAC", "C/E%2fX", "C/E%3a"):
        with pytest.raises(EngineError):
            _pins(estimate_version(key, "EAC", 1, JANUARY)).of_contract("C/2")
    # The canonical uppercase tokens stay valid, including a literal percent (%25).
    assert _pins(estimate_version("C%252F2/EAC", "EAC", 1, JANUARY)).of_contract("C%2F2") == (
        "C%252F2/EAC",
    )


def test_of_contract_accepts_the_canonical_at_escape_and_leaves_it_unselected_elsewhere() -> None:
    """Positive control (Codex, ENG-COST-LOOKUP-R1a): ``%40`` is the canonical encoding of ``@``
    (digits only, no alphabetic case) and is structurally valid, never refused. Raw id ``C@x``
    encodes to ``C%40x``; with ``C%40x/EAC`` and ``C%2F2/EAC`` both present, the lookup of ``C@x``
    selects exactly its own key, and the lookup of ``C/2`` selects ``C%2F2/EAC`` with the ``%40``
    key unselected — not refused."""
    assert encode_key("C@x") == "C%40x"
    at = estimate_version("C%40x/EAC", "EAC", 1, JANUARY)  # raw C@x
    slash = estimate_version("C%2F2/EAC", "EAC", 1, JANUARY)  # raw C/2
    pins = _pins(at, slash)
    assert pins.of_contract("C@x") == ("C%40x/EAC",)
    assert pins.of_contract("C/2") == ("C%2F2/EAC",)
    assert pins.of_contract("C%40x") == ()  # raw C%40x is yet another id (C%2540x): nothing
    assert malformed_estimate_key("C%40x/EAC") is None
    assert malformed_estimate_key("PORTFOLIO:P%40x/RETURN_RATE") is None
