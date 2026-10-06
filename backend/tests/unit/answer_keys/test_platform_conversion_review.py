"""Codex conversion review of 7fc7af7 (PRODUCTION-F-RPS-CONVERSION-REVIEW-7fc7af7.md): rules CONV-1
to CONV-4 of record §16 with Codex's exact inputs (lane F-RPS + ENG-E1). No database.

- CONV-1: enum-typed handler parameters receive enum instances (BookCode, RegistryScope, the
  optional policy book); ``bind_check`` verifies the native types, so binding alone cannot pass.
- CONV-2: EX42 seq 7 ``ESTIMATE_CHANGED`` takes the estimate lifecycle route, never
  ``record_events`` (record §18 FOLL-2 made that route executable: submit → decide → compute)
  until that command exists; ``record_events`` never carries it (API-R-30). Since 04 §16.14
  rev 1.241 the version, its CONSTRAINT record and its evidence come before the submission
  (``test_platform_estimate_statements``).
- CONV-3: the DLT ``LEGACY_PARITY`` preset is preserved as a lifecycle step; a DEFAULT world has
  none; an unsupported preset refuses explicitly.
- CONV-4: ``unit_price`` "25" and the admitted object {amount: "25", currency: USD} both convert to
  the DecimalStr "25"; a mismatched currency refuses.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from erev_api.enums import BookCode, RegistryScope
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, H, load_platform_key, plan
from support.answer_keys.platform_runner import (
    EXECUTED,
    DbPlatform,
    NotProvisioned,
    run_platform,
)
from support.answer_keys.request_models import (
    PRESET_HANDLER,
    MockResolver,
    adapt,
    bind_check,
    booking_request,
)
from support.answer_keys.workspace_adapter import (
    Call,
    RecordingInvoker,
    WorkspaceAdapter,
    booking_body,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _calls(loaded: LoadedKey) -> list:  # noqa: ANN202
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        loaded, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock-fixture"
    )
    for step in plan(loaded).steps:
        if step.phase in ("CHECKPOINT", "RUNNER") or step.gap is not None:
            continue
        try:
            adapter.run(step)
        except NotProvisioned:
            continue
    return invoker.calls


def test_conv_1_entity_book_and_policy_scope_are_enum_instances() -> None:
    """Every put_entity_book call carries a BookCode; every create_policy call a RegistryScope
    (and a BookCode for a BOOK scope); EX42's ENTITY US01 policy takes the ENTITY scope."""
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        resolver = MockResolver(key_id)
        for call in _calls(loaded):
            if call.handler == H["entity_book"]:
                for kwargs in adapt(call, loaded.key, resolver):
                    assert isinstance(kwargs["code"], BookCode), (key_id, kwargs["code"])
            if call.handler == H["policy"]:
                for kwargs in adapt(call, loaded.key, resolver):
                    assert isinstance(kwargs["scope"], RegistryScope), (key_id, kwargs["scope"])
                    if kwargs["scope"] is RegistryScope.BOOK:
                        assert isinstance(kwargs["book_code"], BookCode)
                    if kwargs["scope"] is RegistryScope.ENTITY:
                        assert kwargs["entity_code"] is not None
    ex42 = load_platform_key(EX42)
    entity_policy = [
        kwargs
        for call in _calls(ex42)
        if call.handler == H["policy"]
        for kwargs in adapt(call, ex42.key, MockResolver(EX42))
        if kwargs["scope"] is RegistryScope.ENTITY
    ]
    assert entity_policy and entity_policy[0]["entity_code"] == "US01"


def test_conv_1_bind_check_refuses_a_string_where_an_enum_is_required() -> None:
    loaded = load_platform_key(POS_012)
    resolver = MockResolver(POS_012)
    call = next(c for c in _calls(loaded) if c.handler == H["entity_book"])
    (kwargs,) = adapt(call, loaded.key, resolver)
    bind_check(call, [kwargs])  # enum instance: binds and type-checks
    with pytest.raises(TypeError, match="BookCode"):
        bind_check(call, [{**kwargs, "code": "ASC606"}])


def test_conv_2_estimate_change_takes_the_lifecycle_route_never_record_events() -> None:
    """CONV-2 kept: ESTIMATE_CHANGED is never appended through record_events (API-R-30). FOLL-2
    (record §18) made the route executable: at seq 7 the preparer submits the DRAFT version, the
    approver's decision appends the event (known_at is that commit), then the group computes."""
    ex42 = load_platform_key(EX42)
    seven = [s for s in plan(ex42).steps if s.seq == 7 and s.phase == "TIMELINE"]
    assert [s.handler for s in seven] == [H["estimate_submit"], H["decide"], H["compute"]]
    assert "API-R-30" in seven[0].detail.get("route", "")
    assert seven[1].detail["emits"] == "ESTIMATE_CHANGED" and seven[1].captures_known_at
    assert not seven[0].captures_known_at
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(
        ex42, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock-fixture"
    )
    result = run_platform(ex42, DbPlatform(ex42, adapter))
    executed = [item for item in result.executed if item.step.seq == 7]
    # 04 §16.14 rev 1.241 (PRD ERR-93, ERR-94): seven steps of the runner's come before the
    # route's three — the version created when it is due, its CONSTRAINT record prepared,
    # sent and reviewed, the record named on the version, its evidence uploaded and attached.
    assert [item.status for item in executed] == [EXECUTED] * 10
    assert [item.step.handler for item in executed][-3:] == [s.handler for s in seven]
    assert 7 in result.known_at
    assert not any(c.handler == H["record_events"] and c.step.seq == 7 for c in invoker.calls)
    # booking 1, the runner's Step 1 assessment of the one enabled book 2 (DG-AK-41 layer 4), the
    # approved activation 3, the approved estimate 4
    assert adapter.stream["C-EX42-C"] == 4
    with pytest.raises(NotProvisioned, match="CONV-2"):  # the direct append still refuses
        record = next(  # a key event's own append, not the runner's assessment before activation
            c
            for c in invoker.calls
            if c.handler == H["record_events"] and c.step.phase == "TIMELINE"
        )
        adapt(
            Call(
                H["record_events"],
                record.actor,
                {**record.kwargs, "contract": "C-EX42-C"},
                next(s for s in seven if s.handler == H["estimate_submit"]),
            ),
            ex42.key,
            MockResolver(EX42),
        )


def test_conv_3_legacy_parity_preset_is_preserved_and_default_has_none() -> None:
    dlt = load_platform_key(DLT)
    pos = load_platform_key(POS_012)
    dlt_presets = [s for s in plan(dlt).steps if s.handler == PRESET_HANDLER]
    assert dlt_presets and dlt_presets[0].phase == "WORLD"
    assert not [s for s in plan(pos).steps if s.handler == PRESET_HANDLER]
    calls = [c for c in _calls(dlt) if c.handler == PRESET_HANDLER]
    assert calls
    for call in calls:
        (kwargs,) = adapt(call, dlt.key, MockResolver(DLT))
        assert isinstance(kwargs["scope"], RegistryScope)
        bind_check(call, [kwargs])
    assert len(_calls(dlt)) > len(_calls(pos)) - 20  # sanity: the preset adds steps to DLT
    from support.answer_keys.platform_plan import preset_steps

    with pytest.raises(ValueError, match="preset"):
        preset_steps("OTHER", effective_from="2026-01-01T05:00:00Z")
    assert preset_steps("DEFAULT", effective_from="2026-01-01T05:00:00Z") == []


def test_conv_4_both_money_encodings_of_unit_price_normalise(tmp_path: Path) -> None:
    ex42 = load_platform_key(EX42)
    contract = next(c for c in ex42.key.contracts if any(line.unit_price for line in c.lines))
    resolver = MockResolver(EX42)
    original = booking_request(contract, ex42.key.world, resolver)
    assert next(line.unit_price for line in original.lines if line.unit_price) == "25"
    source = yaml.safe_load((ANSWER_KEY_ROOT / "disc" / f"{EX42}.yaml").read_text())
    for entry in source["contracts"]:
        for line in entry["lines"]:
            if line.get("unit_price") == "25":
                line["unit_price"] = {"amount": "25", "currency": "USD"}
    target = tmp_path / "disc" / f"{EX42}.yaml"
    target.parent.mkdir()
    target.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    admitted = load(target)
    same = next(c for c in admitted.key.contracts if c.external_id == contract.external_id)
    converted = booking_request(same, admitted.key.world, resolver)
    assert next(line.unit_price for line in converted.lines if line.unit_price) == "25"
    assert booking_body(same)["lines"][0].get("unit_price") == "25"
    for entry in source["contracts"]:
        for line in entry["lines"]:
            if isinstance(line.get("unit_price"), dict):
                line["unit_price"]["currency"] = "EUR"
    target.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    mismatched = load(target)
    wrong = next(c for c in mismatched.key.contracts if c.external_id == contract.external_id)
    with pytest.raises(ValueError, match="currency"):
        booking_request(wrong, mismatched.key.world, resolver)
