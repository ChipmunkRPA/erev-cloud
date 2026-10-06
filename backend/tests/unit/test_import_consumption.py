"""The legacy import books a plan against the APPROVED basis of its key (DG-KRN-APR-05 rev 1.51;
D-98 candidate 119; Codex production-20260921-0342 R1): the composition the IMPORT_COMMIT job
consumed under the locks carries each key's approved head or approved absence, and ``_book`` admits
a plan only against it — never by adopting whatever draft is visible at that moment."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine, subjects
from erev_api.db import locking
from erev_api.domain.imports import commit, csv_v2, diff, legacy_v1
from erev_api.domain.imports.legacy_v1 import contract_setup

REQUEST = UUID(int=9)
IMPORT = UUID(int=20)


def _consumed(bases: dict[str, int | None]) -> engine.ConsumedBasis:
    return engine.ConsumedBasis(
        approval_request_id=REQUEST,
        subject_type=engine.ApprovalSubjectType.IMPORT_COMMIT,
        subject_id=IMPORT,
        keys=frozenset(bases),
        bases=bases,
        session=SimpleNamespace(),
    )


def _draft(head: int) -> dict[str, Any]:
    return {"id": UUID(int=1), "head_stream_version": head, "status": "DRAFT"}


def test_approved_absence_refuses_a_contract_that_appeared_in_between() -> None:
    """Codex 0342 R1's witness: key B approved absent; after the initial check an external
    transaction created and committed a compatible DRAFT B; the later plan must not adopt it."""
    with pytest.raises(engine.StaleBasis):
        contract_setup._admit_booking(_consumed({"B": None}), "B", _draft(1))


def test_approved_absence_admits_a_still_absent_key() -> None:
    contract_setup._admit_booking(_consumed({"B": None}), "B", None)


def test_approved_head_must_still_be_the_head_of_the_draft() -> None:
    consumed = _consumed({"A": 3})
    contract_setup._admit_booking(consumed, "A", _draft(3))  # the approved head: admitted
    with pytest.raises(engine.StaleBasis):
        contract_setup._admit_booking(consumed, "A", _draft(4))  # moved after the approval
    with pytest.raises(engine.StaleBasis):
        contract_setup._admit_booking(consumed, "A", None)  # the approved draft is gone


def test_a_key_without_a_basis_entry_is_refused_not_treated_as_absent() -> None:
    """A missing basis entry is distinct from an approved None: the approval did not cover the
    key, so the plan is refused rather than treated as an approved absence."""
    with pytest.raises(engine.StaleBasis):
        contract_setup._admit_booking(_consumed({"A": 3}), "B", None)


def test_the_dry_run_has_no_composition_and_enforces_nothing() -> None:
    contract_setup._admit_booking(None, "B", _draft(1))
    contract_setup._admit_booking(None, "A", None)


# --- the consumption's lock set (integrated batch #5 return, main 020e5fd3) -----------------------

CONTRACT_1, CONTRACT_2 = UUID(int=31), UUID(int=32)
COMMITTING_ROW: dict[str, Any] = {
    "id": IMPORT,
    "status": "COMMITTING",
    "template_code": "legacy_progress_tracking",
    "approval_request_id": REQUEST,
    "is_quarantine_mode": False,
    "diff_file_id": UUID(int=40),
    "file_object_id": UUID(int=41),
    "created_by": UUID(int=11),
}


class _Stop(Exception):
    pass


class _Session:
    """Answers the two reads of the commit up to the consumption step: the lock of the upload's
    source file row — a source that was not shredded (supervisor ruling R-98 (1)) — and the ids
    of the contracts named by external id. ``order`` records which lock came when."""

    def __init__(self, order: list[str]) -> None:
        self.asked: list[list[str]] = []
        self.order = order

    def scalars(self, statement: Any) -> list[UUID]:
        keys = list(statement.whereclause.right.value)
        self.asked.append(keys)
        ids = {"Contract 1": CONTRACT_1, "Contract 2": CONTRACT_2}
        return [ids[key] for key in keys if key in ids]

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        table = statement.get_final_froms()[0].name
        if table != "file_object" or "FOR UPDATE" not in str(statement):
            raise AssertionError(f"unexpected statement: {statement}")
        self.order.append("source file row")
        source = SimpleNamespace(original_filename="progress.xlsx", shredded_at=None)
        return SimpleNamespace(one=lambda: source)


def test_the_lock_set_is_every_contract_the_approved_basis_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch #5 on main 020e5fd3 returned the legacy case ``test_named_contracts_stay_locked_from_
    the_consumption_to_the_commit``: a progress commit held NO contract lock, because the lock set
    came from ``import_contract_keys`` alone — empty for a template whose target_object is not
    ``contract`` (``legacy_progress_tracking`` → ``contract_event``) — although the approved basis
    (``diff.stored_bases``) pinned the heads of Contracts 1 and 2. The rows locked before the basis
    is consumed are every contract the basis names, in ascending id order, and the template's keys
    still travel as ``keys``. Fail-first: on the returned source the lock step received ``[]``.

    Supervisor ruling R-98 (1) added one read to this path (STALE TEST WORLD: the upload row of
    this world named no source file and its session answered no other statement): the commit
    locks the upload's source file row first — dev-guide DG-KRN-DB-08 rev 1.130: the upload row,
    the file row, then the group and contract rows — which the last assertion holds."""
    order: list[str] = []
    session = _Session(order)
    locked: list[list[UUID]] = []
    consumed: list[dict[str, Any]] = []
    monkeypatch.setattr(commit, "_locked", lambda session, import_id: dict(COMMITTING_ROW))
    monkeypatch.setattr(diff, "emitter_of", lambda code: None)
    monkeypatch.setattr(diff, "import_rows", lambda session, import_id: [])
    monkeypatch.setattr(subjects, "import_contract_keys", lambda session, import_id: [])
    monkeypatch.setattr(
        diff, "stored_bases", lambda uow, row: [("Contract 2", 5), ("Contract 1", 3)]
    )

    def lock(session: Any, ids: Any) -> None:
        order.append("group and contract rows")
        locked.append(list(ids))

    monkeypatch.setattr(locking, "lock_groups_then_contracts", lock)

    def consume(uow: Any, request_id: UUID, **kwargs: Any) -> None:
        consumed.append({"request_id": request_id, **kwargs})
        raise _Stop  # the consumption itself is the engine's (test_activation_lock_order)

    monkeypatch.setattr(commit, "consume_fresh_basis", consume)
    uow = SimpleNamespace(session=session)
    with pytest.raises(_Stop):
        commit.commit_upload(uow, IMPORT)  # type: ignore[arg-type]
    assert session.asked == [["Contract 1", "Contract 2"]]  # the basis's contracts, sorted
    assert locked == [[CONTRACT_1, CONTRACT_2]]  # locked BEFORE the consumption
    assert consumed == [
        {
            "request_id": REQUEST,
            "subject_type": engine.ApprovalSubjectType.IMPORT_COMMIT,
            "subject_id": IMPORT,
            "keys": [],  # the template's keys — none for a progress template — still travel
            "bases": {"Contract 2": 5, "Contract 1": 3},
        }
    ]
    assert order == ["source file row", "group and contract rows"]


# --- the approval content names the basis's contracts (P5-SUBJ-1; 04 §16.10) ---------------------


class _KeysSession:
    """Answers `import_contract_keys`' three reads for one upload: the upload's template code, the
    template's target object / family, and the VALID / WARNING rows — their NORMALIZED data (the
    authoritative contract field) or, for the previous seam, the display `business_key` it read,
    rebuilt from the same rows (so the fail-first red is the truncation itself)."""

    def __init__(
        self, *, code: str, target_object: str, family: str, rows: list[dict[str, Any]]
    ) -> None:
        self.code, self.target_object, self.family, self.rows = code, target_object, family, rows

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        table = statement.get_final_froms()[0].name
        if table == "import_upload":
            return SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(template_code=self.code, template_version=1)
            )
        if table == "import_template":
            return SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    target_object=self.target_object, family=self.family
                )
            )
        raise AssertionError(f"unexpected statement on {table}")

    def scalars(self, statement: Any) -> list[Any]:
        assert statement.get_final_froms()[0].name == "import_row"
        selected = {c.name for c in statement.selected_columns}
        if selected == {"business_key"}:  # the previous seam: the DISPLAY key (T-IMP-03 join)
            return [" / ".join(str(value) for value in row.values()) for row in self.rows]
        assert selected == {"normalized"}, selected  # the authoritative data
        return list(self.rows)


def _legacy(*names: str) -> list[dict[str, Any]]:
    return [
        {"Contract Unique Name": name, "POB Unique ID": f"POB #{i}", "SKU Name": "SKU-A"}
        for i, name in enumerate(names, start=1)
    ]


@pytest.mark.parametrize(
    ("code", "target_object", "family", "rows", "expected"),
    [
        (
            "legacy_contract_setup",
            "contract",
            "LEGACY_V1",
            _legacy("Contract 2", "Contract 1"),
            ["Contract 1", "Contract 2"],
        ),
        (
            "legacy_progress_tracking",
            "contract_event",
            "LEGACY_V1",
            _legacy("Contract 2", "Contract 1", "Contract 2"),
            ["Contract 1", "Contract 2"],
        ),
        (
            "legacy_contract_modification",
            "modification",
            "LEGACY_V1",
            _legacy("Contract 1"),
            ["Contract 1"],
        ),
        (
            # D-98 candidate 135 amendment 1 (Codex 1521 §1): " / " inside the identifier — the
            # display business_key reads "ACME / West / POB #1 / SKU-A"; the key is the contract.
            "legacy_progress_tracking",
            "contract_event",
            "LEGACY_V1",
            _legacy("ACME / West", "ACME / West", "ACME"),
            ["ACME", "ACME / West"],
        ),
        (
            "cost_events",
            "contract_event",
            "CSV_V2",
            [{"contract": "SF-ORD-2"}, {"contract": "SF-ORD-1"}, {"contract": "SF-ORD-2"}],
            ["SF-ORD-1", "SF-ORD-2"],
        ),
        (
            "cost_events",
            "contract_event",
            "CSV_V2",
            [{"contract": "X / Y"}, {"contract": "X"}],
            ["X", "X / Y"],
        ),
        # prospective: the seeded CSV v2 `modifications` template has no emitter yet, so it names
        # nothing until one is registered (its key_column will be the contract).
        ("modifications", "modification", "CSV_V2", [{"contract": "SF-ORD-9"}], []),
        ("estimates", "estimate_version", "CSV_V2", [{"contract": "SF-ORD-1"}], []),
        ("legacy_sku_ssp", "ssp_book_version", "LEGACY_V1", [{"SKU Name": "SKU-A"}], []),
    ],
    ids=[
        "legacy-setup",
        "legacy-progress",
        "legacy-modification",
        "legacy-progress-slash-in-name",
        "csv-contract-event",
        "csv-contract-event-slash-in-name",
        "csv-modifications-prospective",
        "csv-estimates-excluded",
        "legacy-sku-ssp-none",
    ],
)
def test_contract_keys_name_the_contracts_of_every_contract_keyed_template(
    code: str, target_object: str, family: str, rows: list[dict[str, Any]], expected: list[str]
) -> None:
    """P5-SUBJ-1 (04 §16.10 rev 1.65; D-98 candidate 135 + amendment 1) — a COMPOSITION-SHAPE
    witness on a stand-in session (source-derived; the persisted-row witnesses are the DB cases):
    `import_contract_keys` names the contracts of a contract template AND of the contract-event /
    modification templates of both families, read from each row's NORMALIZED contract field (the
    legacy `Contract Unique Name`; a CSV v2 emitter's registered `key_column`) — exact text, so an
    identifier containing " / " survives — sorted, deduplicated; `estimates`, the non-contract
    templates and a CSV v2 template without an emitter name none. The columns come from the
    registry the domain templates fill when they load (`register_import_contract_column`; the
    kernel imports no domain module, DG-ARC-01) — the two packages are imported above for that.
    Fail-first on db77bd3f's seam: the LEGACY slash case returned the truncated prefix
    (`ACME`); the CSV slash case was never truncated (a single-column key) and passed; the other
    red was the prospective CSV `modifications` expectation (Codex 1653 §3)."""
    assert "legacy_progress_tracking" in legacy_v1.TEMPLATES and "cost_events" in csv_v2.TEMPLATES
    session = _KeysSession(code=code, target_object=target_object, family=family, rows=rows)
    assert subjects.import_contract_keys(session, IMPORT) == expected  # type: ignore[arg-type]


def test_the_contract_columns_are_registered_by_the_domain_templates() -> None:
    """DG-ARC-01: the kernel consults a registry the domain fills — legacy setup / progress /
    modification register `Contract Unique Name`; CSV v2 contract-keyed emitters register their
    `key_column`; `estimates` and the non-contract templates register nothing."""
    assert subjects.import_contract_column("legacy_progress_tracking") == "Contract Unique Name"
    assert subjects.import_contract_column("legacy_contract_modification") == "Contract Unique Name"
    assert subjects.import_contract_column("legacy_contract_setup") == "Contract Unique Name"
    assert subjects.import_contract_column("contracts") == "external_id"
    assert subjects.import_contract_column("cost_events") == "contract"
    assert subjects.import_contract_column("invoices") == "contract"
    assert subjects.import_contract_column("pre_standard_revenue") == "contract"
    assert subjects.import_contract_column("estimates") is None
    assert subjects.import_contract_column("legacy_sku_ssp") is None
    assert subjects.import_contract_column("modifications") is None  # no CSV v2 emitter yet


def test_a_progress_import_approval_pins_its_contracts_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A composition-shape witness (stand-in session; source-derived): `import_commit_content.
    contracts` carries `[external_id, head]` for a progress import's contracts and the canonical
    hash moves when one head moves — the STALE_SUBJECT trigger for progress / modification
    approvals (the commit's `_check_bases` stays). Green before and after the seam change; the
    persisted-row witnesses are the DB cases (NOT RUN on l12)."""
    from erev_engine.canonical import sha256_hex

    heads = {"Contract 1": 3, "Contract 2": 5}

    class _ContentSession:
        def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            table = statement.get_final_froms()[0].name
            if table == "import_upload":
                row = SimpleNamespace(
                    file_sha256="f" * 64,
                    template_code="legacy_progress_tracking",
                    template_version=1,
                    parameters={"effective_date": "2023-01-31"},
                    diff_file_id=None,
                )
                return SimpleNamespace(one_or_none=lambda: row)
            if table == "contract":
                return [(key, head) for key, head in heads.items()]
            raise AssertionError(f"unexpected statement on {table}")

    monkeypatch.setattr(
        subjects, "import_contract_keys", lambda session, subject_id: ["Contract 1", "Contract 2"]
    )
    content = subjects.import_commit_content(_ContentSession(), IMPORT)  # type: ignore[arg-type]
    assert content["contracts"] == [["Contract 1", 3], ["Contract 2", 5]]
    reviewed = sha256_hex(content)
    heads["Contract 1"] = 4  # an event appended to Contract 1 after the review
    moved = subjects.import_commit_content(_ContentSession(), IMPORT)  # type: ignore[arg-type]
    assert moved["contracts"] == [["Contract 1", 4], ["Contract 2", 5]]
    assert sha256_hex(moved) != reviewed
