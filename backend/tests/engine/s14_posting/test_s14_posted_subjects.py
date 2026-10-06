"""S14-INV-02 per subject family over the ledger read-back rule, and the regrouping rule of a
group-level subject (item ENG-COST-READBACK-1; supervisor rulings R-11 as amended on 2026-10-02
and R-44 (b); ENGINE_SPEC_B S14-R-04 rev 1.165; 04 T-SL-04 ``subject_key`` rev 1.282; 05 RCP-05
rev 1.202).

The ledger stores the subject key the engine posts under and the read-back returns it, so the
``posted`` amounts of a bundle name the role keys the engine emitted. For one answer key per
subject family the last checkpoint is computed with its three close passes, everything posted is
sealed under those subjects, and the computation and the passes run again: no intent.

Under the read-back as it was (decision L3-1-Q-32: every line without an obligation answered
``<contract>@<entity>``; it stands now for a line without a stored key alone) the same
recompute reversed and re-posted the refund-liability
components, the cost assets, the loss units and the FX remeasurements, and it raised for the two
terminated contracts with a capitalised commission below — the reason variants of S14-R-27 no
longer summed to a role key that had lost its subject.

The database half is ``tests/domain/contracts/test_posted_subjects.py``. The contract-level loss
unit posts only in the ``CLOSE_RELEASE`` pass (JET-12 is time-driven); its database witness is
``tests/domain/close/test_close_run_steps.py::test_a_second_release_of_a_loss_unit_posts_nothing``.

Regrouping (S14-R-04). A group-level subject begins with the combination group —
``<group>@<entity>`` of FX remeasurement, ``<group>@<entity>/<kind>/<source>`` of a
refund-liability component. When a contract changes group, what it posted stays stored under the
former group's key. ONE rule covers every such subject: the stored amount answers the same subject
under the current group, so a combination posts only differences. The two-member case of FX
remeasurement is ``test_s14_fx_rate_references.py``; the components are witnessed here.
"""

from __future__ import annotations

import dataclasses
import decimal

import erev_engine
import pytest
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.money import DECIMAL_CONTEXT
from erev_engine.stages.s14_posting.assign import regrouped_subject_key
from support import intent_totals
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

# (answer key, the posted (entry kind, subject key) pairs that show its family)
FAMILIES = (
    # a contract-level loss unit: the contract key itself
    ("loss/LOSS-GE-03-LOSS-CONTRACT-PROVISION", (("LOSS_PROVISION", "GE-03"),)),
    ("loss/LOSS-S7-LOSS-OWN", (("LOSS_PROVISION", "C-LOSS"),)),
    # a cost asset <contract>/<event> with two reason variants, and a refund-liability component
    (
        "mod/MOD-CHK-112",
        (
            ("CONTRACT_COST_CAPITALIZATION", "C-TERM/EV-000005"),
            ("CONTRACT_COST_AMORTIZATION", "C-TERM/EV-000005"),
            ("REFUND_LIABILITY", "CG-C-TERM@US01/TERMINATION/C-TERM/EV-000007"),
        ),
    ),
    ("mod/MOD-FS-09-CANCELLATION-REFUND-COMMISSION", ()),
    # <group>@<entity> of FX remeasurement and the component <group>@<entity>/<kind>/<source>
    (
        "fx/FX-CHK-084-A-REFUND-LIABILITY-REMEASURED",
        (
            ("FX_REMEASUREMENT", "CG-C-FX-084-A@US01"),
            ("REFUND_LIABILITY", "CG-C-FX-084-A@US01/RETURN/C-FX-084-A/L1-GADGET"),
            ("REVENUE_RECOGNITION", "C-FX-084-A/L1-GADGET"),
        ),
    ),
    ("fx/FX-CHK-081-CONTRACT-ASSET-REMEASURED-TO-CLOSING-RATE", ()),
)


def _run(bundle: InputBundle) -> list[OutputBundle]:
    """The command computation and the three close passes over what it posts (RCP-08)."""
    first = erev_engine.compute(bundle)
    done: list[OutputBundle] = []
    with decimal.localcontext(DECIMAL_CONTEXT):
        for name in runners.CLOSE_PASSES:
            done.append(intent_totals.close_pass(bundle, [first, *done], name))
    return [first, *done]


@pytest.mark.parametrize(("key", "expected"), FAMILIES, ids=[key for key, _ in FAMILIES])
def test_s14_inv_02_a_recompute_over_the_stored_subjects_posts_nothing(
    key: str, expected: tuple[tuple[str, str], ...]
) -> None:
    """The last checkpoint of ``key``: what the computation and its passes post, read back under
    the subjects the engine posted it under, leaves the next computation and its passes nothing to
    post, for every book and bundle of the checkpoint."""
    loaded = load(ANSWER_KEY_ROOT / f"{key}.yaml")
    checkpoint = runners._build_checkpoint_bundles(loaded)[-1]
    subjects: set[tuple[str, str]] = set()
    for bundle in checkpoint.bundles:
        outputs = _run(bundle)
        stored = intent_totals.posted(*outputs, sealed=bundle.posted)
        assert stored, key
        subjects.update((item.entry_kind, item.subject_key) for item in stored)
        again = _run(dataclasses.replace(bundle, posted=stored))
        assert [
            (intent.entry_kind, intent.subject_key)
            for output in again
            for book in output.books
            for intent in book.posting_intents
        ] == []
    assert set(expected) <= subjects


# (answer key, the group-level (entry kind, subject key) pairs it stores under its own group)
GROUP_LEVEL = (
    (
        "fx/FX-CHK-084-A-REFUND-LIABILITY-REMEASURED",
        (
            ("FX_REMEASUREMENT", "CG-C-FX-084-A@US01"),
            ("REFUND_LIABILITY", "CG-C-FX-084-A@US01/RETURN/C-FX-084-A/L1-GADGET"),
        ),
    ),
    ("mod/MOD-CHK-112", (("REFUND_LIABILITY", "CG-C-TERM@US01/TERMINATION/C-TERM/EV-000007"),)),
)
CURRENT_GROUP = "CG-COMBINED"


@pytest.mark.parametrize(("key", "stored_under"), GROUP_LEVEL, ids=[key for key, _ in GROUP_LEVEL])
def test_s14_r_04_regrouping_a_group_level_subject_answers_the_current_group(
    key: str, stored_under: tuple[tuple[str, str], ...]
) -> None:
    """The regrouping rule of S14-R-04 for every group-level subject (rulings R-11, R-44 (b)). The
    last checkpoint of ``key`` is computed with its close passes and sealed: the remeasurement and
    the refund-liability components are stored under the key of the contract's own group. The
    contract then belongs to another combination group — ``CG-COMBINED``; nothing else changes —
    and is computed again with its passes over those amounts. An amount stored under
    ``<former group>@<entity>…`` answers the same subject under the current group, so nothing
    posts. The stored keys alone would reverse every such amount under the former group's key and
    post it again under the current group's (net nil per role and period)."""
    loaded = load(ANSWER_KEY_ROOT / f"{key}.yaml")
    checkpoint = runners._build_checkpoint_bundles(loaded)[-1]
    seen: set[tuple[str, str]] = set()
    for bundle in checkpoint.bundles:
        stored = intent_totals.posted(*_run(bundle), sealed=bundle.posted)
        seen.update((item.entry_kind, item.subject_key) for item in stored)
        moved = dataclasses.replace(
            bundle,
            posted=stored,
            group=dataclasses.replace(bundle.group, group_key=CURRENT_GROUP),
        )
        assert [
            (intent.entry_kind, intent.subject_key)
            for output in _run(moved)
            for book in output.books
            for intent in book.posting_intents
        ] == []
    assert set(stored_under) <= seen


@pytest.mark.parametrize(
    ("stored", "answered"),
    [
        # group-level subjects of a former group: the FX remeasurement subject and the components
        ("CG-K1@US01", "CG-COMBINED@US01"),
        ("CG-K1@US01/RETURN/K-1/POB-01", "CG-COMBINED@US01/RETURN/K-1/POB-01"),
        ("CG-K1@US01/TERMINATION/K-1/EV-000007", "CG-COMBINED@US01/TERMINATION/K-1/EV-000007"),
        (
            "CG-K1@US01/VARIABLE_CONSIDERATION/K-1/REBATE-01",
            "CG-COMBINED@US01/VARIABLE_CONSIDERATION/K-1/REBATE-01",
        ),
        # the current group's own subjects
        ("CG-COMBINED@US01", "CG-COMBINED@US01"),
        ("CG-COMBINED@US01/RETURN/K-1/POB-01", "CG-COMBINED@US01/RETURN/K-1/POB-01"),
        # subjects of a member contract are not group-level: <contract>@<entity>, an obligation,
        # a cost asset, a contract-level loss unit, a termination key
        ("K-1@US01", "K-1@US01"),
        ("K-1/POB-01", "K-1/POB-01"),
        ("K-1/EV-000005", "K-1/EV-000005"),
        ("K-1", "K-1"),
        ("K-1#TERMINATION@EV-000007", "K-1#TERMINATION@EV-000007"),
    ],
)
def test_s14_r_04_regrouped_subject_key_vectors(stored: str, answered: str) -> None:
    """``regrouped_subject_key``: only the leading group of a group-level subject is replaced;
    every other component, and every subject of a member contract, is kept."""
    assert regrouped_subject_key(stored, "CG-COMBINED", frozenset({"K-1", "K-2"})) == answered


def test_s14_r_04_regrouped_subject_key_encodes_the_current_group() -> None:
    """The current group's code is CV-21 encoded as the engine writes it in a subject key."""
    assert regrouped_subject_key("CG-K1@US01", "CG/A@B", frozenset()) == "CG%2FA%40B@US01"


def test_s14_r_04_a_stored_key_named_like_a_member_contract_is_read_as_that_contract() -> None:
    """The assumption of the regrouping rule, pinned (S14-R-04 rev 1.165; supervisor ruling on the
    lane's collision point): combination group codes and contract external ids are disjoint, which
    the platform enforces (item CTR-EXTID-RESERVED-1). The engine refuses nothing: a stored
    ``<x>@…`` whose ``x`` is the external id of a member contract is that contract's subject and
    keeps its key — also when a former group carried the same code, for its FX subject and for a
    component alike — while the same key answers the current group once ``x`` is no member."""
    members = frozenset({"CG-K1", "K-2"})  # a member contract whose external id is a group code
    for stored in ("CG-K1@US01", "CG-K1@US01/RETURN/K-2/POB-01"):
        assert regrouped_subject_key(stored, "CG-COMBINED", members) == stored
        moved = regrouped_subject_key(stored, "CG-COMBINED", frozenset({"K-2"}))
        assert moved == stored.replace("CG-K1@", "CG-COMBINED@", 1)
