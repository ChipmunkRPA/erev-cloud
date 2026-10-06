"""The SSP records of a computation reproduce it when they are handed back (item PIN-READBACK-1,
supervisor ruling R-116 (d); 05 RCP-15; ENGINE_SPEC S05-R-03, S06-R-11; 04 T-CON-07
``pinned_refs.ssp_weights``, T-CON-11 ``ssp_book_version_id``).

The bundle builder hands the engine the SSP versions an earlier computation priced an obligation
from: the version of its own pricing and of its weight in each modification. These tests hold the
two halves together without a database. A computation is run, its records are taken as the
platform takes them — ``bundles.ssp_weight_members`` over the trace, ``ssp_book_version_key`` of
each obligation version — and handed back as the read-back rows of ``bundles._policies``; the
second computation must give the first one's figures and trace, key for key. The database half —
which computation is read, the activation gate, the combination, the override — is
``tests/domain/contracts/test_ssp_readback.py`` and ``test_modifications.py``.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import erev_engine
import pytest
from erev_api.domain.contracts import bundles
from erev_engine.bundle import InputBundle, OutputBundle, ResolvedPolicyInput
from erev_engine.trace import SourceRef
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

# (answer key, whether its computations weigh a modification from SSP entries)
KEYS = (
    ("mod/MOD-CHK-028-S6-EX5-CASEB", True),  # remaining units and units added to an obligation
    ("mod/MOD-CHK-043-S6-EX7", True),  # a series, two versions of the book
    ("mod/MOD-S6-COMBINED-MOD-OWN", True),  # a combined group
    ("mod/MOD-CHK-042-D18", True),  # POL-080 D18_DEFAULT
    ("mod/MOD-CHK-042-INCEPTION", True),  # POL-080 INCEPTION_ALL
    ("mr/MR-CHK-050-MODIFICATION", True),  # a material right beside the modification
    ("mod/MOD-S6-EX5-CASEA", False),  # a separate contract: nothing is weighed
    ("mod/MOD-CHK-027-S6-EX8", False),  # cumulative catch-up: no weight from an SSP entry
    ("alc/ALC-CHK-033-S4-EX34-CASEB", False),  # a bundle: the stage 03 reader
    ("alc/ALC-CHK-002-GT01-GT03", False),  # the parity preset: versions named by label
    ("ifrs/IFRS-S13-SWITCH-SHIPPING", False),  # two books
)


def _id(*parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, "/".join(str(part) for part in parts))


def _index(bundle: InputBundle, output: OutputBundle) -> bundles.BundleIndex:
    """Row ids for the natural keys ``ssp_weight_members`` maps (``bundles.index`` without a
    database)."""
    subjects = {item.subject_key for book in output.books for item in book.obligation_versions}
    return bundles.BundleIndex(
        group={},
        contracts={},
        obligations={subject: {"id": _id("obligation", subject)} for subject in subjects},
        entities={},
        periods={},
        products={},
        templates={},
        ssp_versions={v.version_key: _id("version", v.version_key) for v in bundle.ssp_versions},
        ssp_entries={},
        account_mapping_version_id=None,
        fx_versions={},
        events={
            (event.contract_key, event.stream_version): _id("event", event.event_key)
            for event in bundle.events
        },
    )


def _read_back(
    bundle: InputBundle, output: OutputBundle
) -> tuple[InputBundle, dict[str, dict[str, dict[str, str]]]]:
    """``bundle`` with the read-back rows of ``output`` in every book, and the weight records."""
    found = _index(bundle, output)
    weights = bundles.ssp_weight_members(bundle, found, output)
    event_keys = {
        str(found.events[(event.contract_key, event.stream_version)]): event.event_key
        for event in bundle.events
    }
    subjects = {str(row["id"]): subject for subject, row in found.obligations.items()}
    version_keys = {str(version_id): key for key, version_id in found.ssp_versions.items()}
    books = []
    for book, book_output in zip(bundle.books, output.books, strict=True):
        assert book.book_code == book_output.book_code
        values: dict[str, dict[str, str]] = {}
        for item in book_output.obligation_versions:
            own = item.columns.get("ssp_book_version_key")
            if own:
                values.setdefault(item.subject_key, {})[bundles.RECORDED_VERSION] = str(own)
        for event_id, by_obligation in weights.get(book.book_code, {}).items():
            member = f"{bundles.RECORDED_VERSION}@{event_keys[event_id]}"
            for obligation_id, version_id in by_obligation.items():
                values.setdefault(subjects[obligation_id], {})[member] = version_keys[version_id]
        rows = tuple(
            ResolvedPolicyInput(
                bundles.SSP_VERSION_BASIS,
                "OBLIGATION",
                subject,
                dict(sorted(value.items())),
                "O",
                bundles.RECORDED_SOURCE,
                "K",
            )
            for subject, value in sorted(values.items())
        )
        policies = tuple(
            sorted((*book.policies, *rows), key=lambda p: (p.code, p.scope, p.subject_key))
        )
        books.append(dataclasses.replace(book, policies=policies))
    return dataclasses.replace(bundle, books=tuple(books)), weights


def _figures(output: OutputBundle) -> tuple[Any, ...]:
    """Everything a computation states but the hash of its input: every book with its versions,
    schedules, posting intents and trace, and the diagnostics."""
    return output.books, output.diagnostics


@pytest.mark.parametrize(("key", "weighs"), KEYS, ids=[key for key, _ in KEYS])
def test_the_records_of_a_computation_reproduce_it_when_handed_back(key: str, weighs: bool) -> None:
    """For every bundle of every checkpoint of ``key``: the versions the computation priced from,
    handed back as read-back rows, give the same figures and the same trace — so reading the
    record back moves nothing that selection by date had computed. The second computation
    records the same weights again, and its product pin is the first one's: a read-back row is
    the obligation's and never a level-P value of its product."""
    weighed = 0
    for checkpoint in runners._build_checkpoint_bundles(load(ANSWER_KEY_ROOT / f"{key}.yaml")):
        for bundle in checkpoint.bundles:
            output = erev_engine.compute(bundle)
            handed, weights = _read_back(bundle, output)
            assert handed != bundle  # the rows are bundle input: the second run is a new bundle
            second = erev_engine.compute(handed)
            assert _figures(second) == _figures(output)
            assert _read_back(handed, second)[1] == weights
            assert bundles.product_pin_members(handed, second) == bundles.product_pin_members(
                bundle, output
            )
            weighed += sum(len(by_event) for by_event in weights.values())
    assert (weighed > 0) is weighs


def _node(measure: str, subject: str, *sources: SourceRef) -> SimpleNamespace:
    return SimpleNamespace(measure=measure, id=f"{measure}:{subject}:-", inputs=sources)


def _entry(key: str, member: str) -> SourceRef:
    return SourceRef("ssp_entry", key, {"member": member, "value": "1"})


def test_a_weight_is_recorded_only_where_one_version_priced_an_existing_obligation() -> None:
    """``ssp_weight_members`` over the nodes of one event: the remaining units and the added
    units of an existing obligation priced from one version are recorded under the ids of the
    event, the obligation and the version; an obligation the event adds (``added``), a correction
    (``corrected``, ``inception``), a weight without an entry and a weight priced from two
    versions have no record, and neither has a node of another measure."""
    event = SimpleNamespace(event_key="K-01/EV-000003", contract_key="K-01", stream_version=3)
    versions = [
        SimpleNamespace(version_key=f"SSP-US@v{no}", entries=[SimpleNamespace(entry_key=f"E{no}")])
        for no in (1, 2)
    ]
    bundle: Any = SimpleNamespace(ssp_versions=versions, events=[event])
    measure = "mod_weight@K-01/EV-000003"
    nodes = [
        _node(measure, "K-01/O1", _entry("E1", "remaining"), _entry("E1", "added:0")),
        _node(measure, "K-01/O2", _entry("E2", "added")),
        _node(measure, "K-01/O3", _entry("E1", "corrected"), _entry("E2", "inception")),
        _node(measure, "K-01/O4", _entry("-", "remaining")),
        _node(measure, "K-01/O5", _entry("E1", "remaining"), _entry("E2", "added:0")),
        _node(measure, "K-01/O6"),
        _node("mod_pool@K-01/EV-000003", "K-01/O1", _entry("E2", "remaining")),
        _node("mod_weight@K-01/EV-000009", "K-01/O1", _entry("E2", "remaining")),
    ]
    output: Any = SimpleNamespace(
        books=[
            SimpleNamespace(book_code="ASC606", trace=SimpleNamespace(nodes=nodes)),
            SimpleNamespace(book_code="LEGACY", trace=SimpleNamespace(nodes=[])),
        ]
    )
    found: Any = SimpleNamespace(
        events={("K-01", 3): _id("event")},
        obligations={f"K-01/O{no}": {"id": _id("obligation", no)} for no in range(1, 7)},
        ssp_versions={"SSP-US@v1": _id("v1"), "SSP-US@v2": _id("v2")},
    )

    assert bundles.ssp_weight_members(bundle, found, output) == {
        "ASC606": {str(_id("event")): {str(_id("obligation", 1)): str(_id("v1"))}}
    }


def test_mod_ssp_override_preview_1_an_approved_override_gains_its_version_key() -> None:
    """Item MOD-SSP-OVERRIDE-PREVIEW-1: in the engine-facing ``CONTRACT_AMENDED`` payload an
    ``ssp_basis`` override that names an approved version by id carries its key as well
    (ENGINE_SPEC S06-R-11); a classification default, an override naming a version that is not
    approved and every other member stay as stored, and a payload without an override is handed
    on as the same object."""
    approved, unknown = str(_id("approved")), str(_id("unknown"))
    keys = {approved: "US-LIST@v1"}
    override = {"ssp_book_version_id": approved, "is_override": True, "justification": "Agreed."}
    default = {"ssp_book_version_id": approved, "is_override": False, "justification": None}
    unapproved = {"ssp_book_version_id": unknown, "is_override": True, "justification": "Agreed."}
    payload = {
        "modification_id": "M-1",
        "lines": [{"obligation_key": "O2"}],
        "ssp_basis": {"O1": default, "O2": override, "O3": unapproved},
    }

    handed = bundles._ssp_pin_key("CONTRACT_AMENDED", payload, keys)

    assert handed == {
        **payload,
        "ssp_basis": {
            "O1": default,
            "O2": {**override, "ssp_version_key": "US-LIST@v1"},
            "O3": unapproved,
        },
    }
    assert payload["ssp_basis"]["O2"] == override  # the stored payload is not changed
    plain = {"modification_id": "M-2", "ssp_basis": {"O1": default}}
    assert bundles._ssp_pin_key("CONTRACT_AMENDED", plain, keys) is plain
    assert bundles._ssp_pin_key("CONTRACT_BOOKED", payload, keys) is payload


def test_the_record_starts_at_the_first_activation_of_a_contract() -> None:
    """``_activation_gates``: per contract the stream version of its first ``CONTRACT_ACTIVATED``
    — behind it a computation is no longer provisional (ENGINE_SPEC S02-R-02) — and no gate for
    a contract still DRAFT."""
    first, second, draft = _id("first"), _id("second"), _id("draft")
    stored = [
        {"contract_id": first, "event_type": "CONTRACT_BOOKED", "stream_version": 1},
        {"contract_id": first, "event_type": "CONTRACT_ACTIVATED", "stream_version": 2},
        {"contract_id": second, "event_type": "CONTRACT_BOOKED", "stream_version": 1},
        {"contract_id": second, "event_type": "COLLECTIBILITY_ASSESSED", "stream_version": 2},
        {"contract_id": second, "event_type": "CONTRACT_ACTIVATED", "stream_version": 5},
        {"contract_id": second, "event_type": "CONTRACT_ACTIVATED", "stream_version": 3},
        {"contract_id": draft, "event_type": "CONTRACT_BOOKED", "stream_version": 1},
    ]

    assert bundles._activation_gates(stored) == {first: 2, second: 3}
