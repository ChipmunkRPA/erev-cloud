"""The recorder and the approval RPT-16 and RPT-17 show for a contract event (supervisor ruling
R-63 (c); SCREENS_B §5.6.3 RPT-16, RPT-17; PRD J-04.5): an event written by ``SYSTEM`` for an
import names its upload's uploader and the upload's approval request; every other event keeps
its own fields. CPU: ``event_provenance.resolved`` over flat records (DG-TST-18)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_api.domain.reports import catalogue
from erev_api.domain.reports.builders import event_provenance
from erev_api.domain.reports.builders.event_provenance import (
    APPROVAL,
    RECORDER,
    RECORDER_KIND,
    UPLOAD,
    Upload,
)
from erev_api.enums import PrincipalKind

MAYA = UUID("0a1b2c3d-0000-4000-8000-000000000001")
CLIENT = UUID("0a1b2c3d-0000-4000-8000-000000000002")
UPLOAD_ID = UUID("0a1b2c3d-0000-4000-8000-0000000000a1")
OTHER_UPLOAD = UUID("0a1b2c3d-0000-4000-8000-0000000000a2")
UPLOADS = {UPLOAD_ID: Upload(MAYA, "USER", "APR-000007")}


def event(
    kind: Any = "SYSTEM",
    *,
    recorder: UUID | None = None,
    upload: UUID | None = UPLOAD_ID,
    approval: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {RECORDER: recorder, RECORDER_KIND: kind, UPLOAD: upload, APPROVAL: approval, **extra}


def test_an_event_written_by_system_for_an_import_names_its_upload() -> None:
    (shown,) = event_provenance.resolved([event(stream_version=6)], UPLOADS)
    assert shown == {
        RECORDER: MAYA,  # the uploader
        RECORDER_KIND: "USER",
        UPLOAD: UPLOAD_ID,
        APPROVAL: "APR-000007",  # the upload's IMPORT_COMMIT request
        "stream_version": 6,  # every other member is carried unchanged
    }


def test_the_principal_kind_is_read_as_the_enum_or_its_value() -> None:
    record = event(PrincipalKind.SYSTEM)
    assert event_provenance.written_for_import(record)
    (shown,) = event_provenance.resolved([record], UPLOADS)
    assert (shown[RECORDER], shown[RECORDER_KIND], shown[APPROVAL]) == (MAYA, "USER", "APR-000007")


def test_an_event_with_no_upload_keeps_its_own_fields() -> None:
    own = event("USER", recorder=MAYA, upload=None, approval="APR-000003")
    system = event("SYSTEM", upload=None)  # a system event of another kind (a job, a migration)
    assert event_provenance.resolved([own, system], UPLOADS) == [own, system]
    assert not event_provenance.written_for_import(own)
    assert not event_provenance.written_for_import(system)


def test_an_event_a_person_or_a_client_recorded_keeps_its_own_fields() -> None:
    # an upload id on an event a principal other than SYSTEM appended changes nothing
    person = event("USER", recorder=MAYA, approval="APR-000003")
    client = event("API_CLIENT", recorder=CLIENT)
    assert event_provenance.resolved([person, client], UPLOADS) == [person, client]


def test_an_upload_without_a_request_leaves_the_event_its_own_approval() -> None:
    uploads = {UPLOAD_ID: Upload(MAYA, "USER", None)}
    (shown,) = event_provenance.resolved([event(approval="APR-000011")], uploads)
    assert (shown[RECORDER], shown[RECORDER_KIND]) == (MAYA, "USER")
    assert shown[APPROVAL] == "APR-000011"
    (bare,) = event_provenance.resolved([event()], uploads)
    assert bare[APPROVAL] is None


def test_an_upload_that_was_not_read_changes_nothing() -> None:
    record = event(upload=OTHER_UPLOAD)
    assert event_provenance.resolved([record], UPLOADS) == [record]


def test_a_record_without_an_event_is_carried_unchanged() -> None:
    # RPT-16 holds a cumulative line's record beside its event set: every event member is None
    line = {RECORDER: None, RECORDER_KIND: None, UPLOAD: None, APPROVAL: None, "line_id": 1}
    assert event_provenance.resolved([line], UPLOADS) == [line]


def test_resolved_keeps_the_order_and_leaves_its_input_unchanged() -> None:
    records = [event(), event("USER", recorder=MAYA, upload=None), event()]
    before = [dict(record) for record in records]
    shown = event_provenance.resolved(records, UPLOADS)
    assert records == before
    assert [record[RECORDER_KIND] for record in shown] == ["USER", "USER", "USER"]
    assert [record[APPROVAL] for record in shown] == ["APR-000007", None, "APR-000007"]


def test_both_register_definitions_name_the_upload_among_their_sources() -> None:
    """R-63 (c): ``import_upload`` joins the IPE sources of RPT-16 and RPT-17, with the join an
    imported event is resolved through and the join of its approval."""
    for code in ("out_of_period_register", "late_entry_report"):
        logic = catalogue.DEFINITIONS_BY_CODE[code].ipe_logic
        assert "import_upload" in logic["source_tables"], code
        joins = " | ".join(logic["joins"])
        assert "contract_event.import_upload_id = import_upload.id" in joins, code
        assert "import_upload.approval_request_id = approval_request.id" in joins, code
        assert "contract_event.approval_request_id = approval_request.id" in joins, code
