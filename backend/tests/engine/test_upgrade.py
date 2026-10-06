"""``erev_engine.upgrade``: evidence codec, input transforms, CV-25/L1/attribution views and the
L2 representation diff (05 RCP-28a; D-96 (1)-(4), (F); lane P5 preparation slice).

DB-free by rule (DG-ENG-11): bundles come from ``support.bundles`` and the engine runs in process.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import EstimateVersionInput, InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.upgrade import (
    INPUT_TRANSFORMS,
    TransformUnavailable,
    attribution_comparison,
    attribution_input_sha256,
    bundle_from_mapping,
    candidate_input,
    cv25_view,
    decode_input,
    encode_input,
    encode_output,
    input_mapping,
    l1_sha256,
    l1_view,
    normalised_input_sha256,
    output_mapping,
    raw_digest,
    representation_diff,
    transform_chain,
)
from support.billing_lines import checkpoint_bundle
from support.bundles import (
    book,
    booking_line,
    contract,
    entity,
    event,
    group,
    minimal_contract,
    product,
)

# A computable stored-style bundle: the same answer-key checkpoint the stage-01 ledger tests load
# (DG-AK-40); ``minimal_contract`` stops at ``PRODUCT_UNMAPPED`` and serves the codec tests only.
COMPUTABLE = ("mod", "MOD-LEGACY-PROS-GT12", "end-june-after-prospective")


def _computable() -> InputBundle:
    return checkpoint_bundle(*COMPUTABLE)


def _two_book_bundle() -> InputBundle:
    """One entity keeping ASC606 and IFRS15, one booked contract (for the L1 n + 2 count)."""
    calendar = entity(books=("ASC606", "IFRS15"))
    header = contract()
    line = booking_line()
    booked = event(
        header.external_id,
        1,
        "CONTRACT_BOOKED",
        header.inception_date,
        {"lines": [line]},
        obligation_keys=[str(line["obligation_key"])],
    )
    base = minimal_contract()
    return dataclasses.replace(
        base,
        entities=(calendar,),
        books=(book(entity=calendar), book(book_code="IFRS15", entity=calendar)),
        contracts=(header,),
        events=(booked,),
        group=group((header,), products=(product(),)),
    )


def _estimate(direction: str | None) -> EstimateVersionInput:
    return EstimateVersionInput(
        estimate_key="K-1/VC-1",
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code="VC-1",
        method="EXPECTED_VALUE",
        vc_element_type="REBATE",
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=None,
        version_key="K-1/VC-1@v1",
        version_no=1,
        status="APPROVED",
        effective_date=date(2026, 1, 1),
        scenarios=({"amount": Decimal("100.00"), "probability": Decimal("1")},),
        parameters={"note": "x", "cap": Decimal("5.50")},
        unconstrained_amount=Decimal("100.00"),
        most_conservative_amount=None,
        constrained_amount=Decimal("90.00"),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256="0" * 64,
        direction=direction,
    )


# --- evidence codec (T-CON-25; R1) ---------------------------------------------------------------


@pytest.mark.parametrize("preset", ["DEFAULT", "LEGACY_PARITY"])
def test_round_trip_reproduces_the_bundle_and_its_cv25_hash(preset: str) -> None:
    original = minimal_contract(preset)
    evidence = encode_input(original)
    decoded = decode_input(evidence)
    assert decoded == original
    assert decoded.sha256() == original.sha256()
    # The raw digest is a different hash domain from the logical CV-25 hash (R1).
    assert raw_digest(evidence) != original.sha256()
    assert raw_digest(evidence) == raw_digest(encode_input(decoded))


def test_round_trip_of_a_stored_computation_reproduces_the_output_hash() -> None:
    original = _computable()
    decoded = decode_input(encode_input(original))
    assert decoded == original and decoded.sha256() == original.sha256()
    # Re-execution of the decoded bundle reproduces the stored output hash (RCP-28 L0).
    assert compute(decoded).sha256() == compute(original).sha256()


def test_payload_scalar_types_survive_the_round_trip() -> None:
    original = minimal_contract()
    decoded = decode_input(encode_input(original))
    payload = decoded.events[0].payload
    lines = payload["lines"]
    assert isinstance(lines, list)  # JSON arrays stay lists, as bundle assembly hands them over
    line = lines[0]
    assert isinstance(line, dict)
    assert isinstance(line["quantity"], Decimal) and isinstance(line["start_date"], date)
    assert sha256_hex(payload) == decoded.events[0].payload_sha256
    # The tags are visible in the bytes, never in the decoded bundle.
    assert b'"$decimal"' in encode_input(original) and b'"$date"' in encode_input(original)


def test_known_at_only_change_alters_raw_digest_and_attribution_but_not_cv25() -> None:
    original = minimal_contract()
    moved = dataclasses.replace(original, known_at=original.known_at + timedelta(hours=1))
    assert raw_digest(encode_input(original)) != raw_digest(encode_input(moved))
    assert original.sha256() == moved.sha256()  # CV-25 removes known_at
    assert attribution_input_sha256(original) != attribution_input_sha256(moved)  # F keeps it


def test_estimate_direction_round_trip_and_older_codec_default() -> None:
    with_direction = dataclasses.replace(
        minimal_contract(), estimate_versions=(_estimate("DECREASE"),)
    )
    assert decode_input(encode_input(with_direction)) == with_direction
    # A pre-0.3.0 evidence file has no ``direction`` member: the dataclass default applies.
    mapping = input_mapping(encode_input(with_direction))
    versions = mapping["estimate_versions"]
    assert isinstance(versions, list) and isinstance(versions[0], dict)
    del versions[0]["direction"]
    rebuilt = bundle_from_mapping(mapping)
    assert rebuilt.estimate_versions[0].direction is None
    assert rebuilt.estimate_versions[0].parameters["cap"] == Decimal("5.50")


def test_decoder_refuses_unknown_members_and_formats() -> None:
    original = minimal_contract()
    mapping = input_mapping(encode_input(original))
    mapping["surprise"] = 1
    with pytest.raises(ValueError, match="unknown members"):
        bundle_from_mapping(mapping)
    parsed = json.loads(encode_input(original).decode())
    parsed["evidence_format"] = 99
    with pytest.raises(ValueError, match="unknown input evidence format"):
        input_mapping(json.dumps(parsed).encode())
    with pytest.raises(TypeError, match="float"):
        encode_input(dataclasses.replace(original, tenant_preset=1.5))  # type: ignore[arg-type]


def test_output_evidence_digest_is_the_cv26_hash() -> None:
    output = compute(_computable())
    evidence = encode_output(output)
    assert raw_digest(evidence) == output.sha256()
    # JSON-level mapping re-encodes to the same bytes, so views hash stably.
    assert sha256_hex(output_mapping(output)) == output.sha256()
    assert output_mapping(evidence) == output_mapping(output)


# --- input transforms (RCP-28a "Candidate input") -------------------------------------------------


def test_transform_chain_resolution() -> None:
    assert transform_chain("0.3.0", "0.3.0") == ()
    assert transform_chain("0.2.0", "0.3.0") == (("0.2.0", "0.3.0"),)
    assert transform_chain("0.1.0", "0.3.0") == (("0.1.0", "0.2.0"), ("0.2.0", "0.3.0"))
    with pytest.raises(TransformUnavailable):
        transform_chain("0.0.1", "0.3.0")
    with pytest.raises(TransformUnavailable):
        transform_chain("0.3.0", "0.2.0")  # no downgrade link is registered
    assert set(INPUT_TRANSFORMS) == {("0.1.0", "0.2.0"), ("0.2.0", "0.3.0")}


def test_candidate_input_stamps_the_candidate_and_keeps_the_source() -> None:
    source = dataclasses.replace(minimal_contract(), engine_version="0.2.0")
    mapping = input_mapping(encode_input(source))
    frozen = json.dumps(mapping, default=str, sort_keys=True)
    candidate, transform_id = candidate_input(mapping, ENGINE_VERSION)
    assert candidate.engine_version == ENGINE_VERSION
    assert transform_id == f"0.2.0->{ENGINE_VERSION}:0.2.0->0.3.0"
    assert json.dumps(mapping, default=str, sort_keys=True) == frozen  # source untouched
    assert candidate.sha256() != source.sha256()  # the stamp is hashed (CV-25)
    assert normalised_input_sha256(candidate) == normalised_input_sha256(source)
    same, identity = candidate_input(minimal_contract(), ENGINE_VERSION)
    assert identity == f"{ENGINE_VERSION}->{ENGINE_VERSION}:identity" and same == minimal_contract()
    with pytest.raises(TransformUnavailable):
        candidate_input(dataclasses.replace(source, engine_version="0.0.9"), ENGINE_VERSION)


# --- views ---------------------------------------------------------------------------------------


def test_cv25_view_mirrors_input_bundle_sha256() -> None:
    for bundle in (
        minimal_contract(),
        _two_book_bundle(),
        dataclasses.replace(minimal_contract(), estimate_versions=(_estimate(None),)),
    ):
        assert sha256_hex(cv25_view(bundle)) == bundle.sha256()


def test_attribution_comparison_labels() -> None:
    current = minimal_contract()
    no_previous = attribution_comparison(None, current)
    assert no_previous.equal is None and no_previous.transform_id is None
    equal = attribution_comparison(current, current)
    assert (
        equal.equal is True and equal.transform_id == f"{ENGINE_VERSION}->{ENGINE_VERSION}:identity"
    )
    older = dataclasses.replace(current, engine_version="0.2.0")
    aligned = attribution_comparison(older, current)
    assert aligned.equal is True  # only the stamp differed; the transform brings it across
    moved = dataclasses.replace(current, known_at=current.known_at + timedelta(days=1))
    assert attribution_comparison(moved, current).equal is False  # known_at is an engine-read input
    other_states = dataclasses.replace(current, entities=(entity(states={"FY2026-P01": "closed"}),))
    assert attribution_comparison(other_states, current).equal is False  # period state change
    unreachable = dataclasses.replace(current, engine_version="0.0.1")
    assert attribution_comparison(unreachable, current).equal is None  # no transform chain
    assert equal.as_json()["current_attribution_input_sha256"] == attribution_input_sha256(current)


def _stamp_only_variant(output: dict[str, object], version: str) -> dict[str, object]:
    variant = json.loads(json.dumps(output))
    variant["engine_version"] = version
    variant["input_sha256"] = "f" * 64
    for entry in variant["books"]:
        entry["trace"]["engine_version"] = version
    assert isinstance(variant, dict)
    return variant


def test_l1_equal_for_a_stamp_only_release_and_r_counts_3_and_n_plus_2() -> None:
    one_book = output_mapping(compute(_computable()))
    assert len(one_book["books"]) == 1
    variant = _stamp_only_variant(one_book, "9.9.9")
    assert sha256_hex(one_book) != sha256_hex(variant)  # L0 differs
    assert l1_sha256(one_book) == l1_sha256(variant)  # L1 equal
    diff = representation_diff(one_book, variant)
    assert diff.only_representation and diff.count("R") == 3
    assert diff.as_json() == {
        "M": 0,
        "P": 0,
        "T": 0,
        "R": 3,
        "changed_r_paths": list(diff.changed_r_paths),
    }
    assert set(diff.changed_r_paths) == {
        "engine_version",
        "input_sha256",
        "books[0].trace.engine_version",
    }
    # n + 2 with n = 2: the counting rule is JSON-level, so a second book entry is synthesised.
    two_books = json.loads(json.dumps(one_book))
    second = json.loads(json.dumps(one_book["books"][0]))
    second["book_code"] = "IFRS15"
    two_books["books"].append(second)
    diff2 = representation_diff(two_books, _stamp_only_variant(two_books, "9.9.9"))
    assert diff2.only_representation and diff2.count("R") == 4
    assert set(diff2.changed_r_paths) >= {
        "books[0].trace.engine_version",
        "books[1].trace.engine_version",
    }
    assert l1_view(one_book)["engine_version"] == "" and l1_view(one_book)["input_sha256"] == ""


def test_l2_classifies_money_posting_and_trace_changes() -> None:
    expected = output_mapping(compute(_computable()))
    actual = json.loads(json.dumps(expected))
    book_out = actual["books"][0]
    columns = book_out["contract_version"]["columns"]
    key = next(
        k
        for k, v in sorted(columns.items())
        if isinstance(v, str) and v.replace(".", "").replace("-", "").isdigit()
    )
    columns[key] = str(Decimal(columns[key]) + Decimal("0.01"))
    diff = representation_diff(expected, actual)
    assert diff.count("M") == 1 and not diff.only_representation and diff.count("R") == 0
    row = diff.rows[0]
    assert (
        row.category == "M"
        and row.before != row.after
        and row.path.startswith("books[0].contract_version.columns.")
    )
    # A formula id change is lineage (T), never M or R.
    actual_t = json.loads(json.dumps(expected))
    actual_t["books"][0]["trace"]["nodes"][0]["formula_id"] = "changed.v9"
    assert representation_diff(expected, actual_t).count("T") == 1
    # A posting intent change is P; a trace_nodes lineage key inside a monetary section is T.
    actual_p = json.loads(json.dumps(expected))
    intents = actual_p["books"][0]["posting_intents"]
    if intents:
        intents[0]["lines"][0]["amount_txn"] = intents[0]["lines"][0]["amount_txn"] + 1
        assert representation_diff(expected, actual_p).count("P") == 1
    actual_l = json.loads(json.dumps(expected))
    actual_l["books"][0]["contract_version"]["trace_nodes"]["__probe__"] = "node"
    assert representation_diff(expected, actual_l).count("T") == 1
    assert representation_diff(expected, expected).rows == ()
