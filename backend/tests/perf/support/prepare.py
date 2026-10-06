"""The unmeasured preparation of the sandbox (dev-guide DG-PERF-02 (1)): the month-24 events of the
manifest appended through the API as ``perf-accountant`` (event.record; ≤ 500 per append, the
head's ETag as ``If-Match``) — a request that holds a manual event waits as an event submission
and is approved by ``perf-reviewer`` (event.approve; BUILD_SPEC CTR-6) — and the platform registry
version ``platform.job_concurrency = 8`` authored by ``perf-accountant`` (config.author) and
published for the sandbox with ``perf-reviewer``'s approval (05 PERF-20). NOT RUN in the lane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from erev_api.domain.demo import volume

from perf.support.client import PerfClient

MONTH_24: Final = 24
MAX_EVENTS: Final = 500
CONCURRENCY_KEY: Final = "platform.job_concurrency"
CONCURRENCY: Final = 8


@dataclass(frozen=True, slots=True)
class Prepared:
    events_appended: int
    events_deferred: int
    contracts_touched: int
    policy_id: str | None


def contract_id_by_external_id(client: PerfClient, external_id: str) -> str | None:
    page = client.get("/contracts", {"q": external_id, "limit": 5})
    for item in page.get("items", []):
        if item.get("external_id") == external_id:
            return str(item["id"])
    return None


def approve_request(reviewer: PerfClient, request_id: str) -> None:
    """``POST /approvals/{id}/approve`` as the reviewer, with the subject hash — and the impact
    preview hash when the request has a preview — that the request shows (REQ-PLT-014,
    REQ-PLT-015)."""
    shown: Mapping[str, Any] = reviewer.get(f"/approvals/{request_id}")
    body: dict[str, Any] = {
        "subject_content_sha256": shown["subject"]["content_sha256"],
        "comment": "perf harness",
    }
    preview = shown.get("impact_preview")
    if preview is not None:
        body["impact_preview_sha256"] = preview["sha256"]
    reviewer.post(f"/approvals/{request_id}/approve", body)


def append_month_24(
    client: PerfClient, reviewer: PerfClient, manifest: volume.VolumeManifest
) -> Prepared:
    """Append every month-24 event of the manifest to the sandbox contracts. A request of the
    accountant that holds a manual event — a delivery, a return, a milestone, a cost or, since
    04 rev 1.238, a usage report — appends nothing (BUILD_SPEC CTR-6; 04 §16.3 "Manual
    events"): it waits as an event submission, with
    the entity's evidence document of the month where the product asks for one, until
    ``reviewer`` (``event.approve``) approves it, which appends and computes it. Its events are
    counted as appended after that approval."""
    from erev_api.domain.contracts.events import MANUAL_TYPES
    from erev_api.schemas.events import EventAppendItemIn

    manual = {member.value for member in MANUAL_TYPES}
    grouped: dict[int, list[volume.VolumeEvent]] = {}
    for event in manifest.events_for_month(MONTH_24):
        grouped.setdefault(event.contract_seq, []).append(event)
    by_seq = {c.seq: c for c in manifest.contracts}
    documents: dict[str, str] = {}

    def evidence_of(entity_code: str) -> str:
        """The entity's evidence document of month 24, uploaded by the accountant at its first
        use (``volume.evidence_document``, as the seed stores it for months 1 to 23)."""
        if entity_code not in documents:
            stored: Mapping[str, Any] = client.upload(
                "/files",
                fields={"purpose": "ATTACHMENT"},
                filename=volume.evidence_filename(entity_code, MONTH_24),
                content=volume.evidence_document(
                    (by_seq[seq].external_id, event)
                    for seq in sorted(grouped)
                    if by_seq[seq].entity_code == entity_code
                    for event in grouped[seq]
                    if event.event_type in manual
                ),
                media_type=volume.EVIDENCE_MEDIA_TYPE,
            )
            documents[entity_code] = str(stored["id"])
        return documents[entity_code]

    appended = deferred = touched = 0
    for seq in sorted(grouped):
        spec = by_seq[seq]
        contract_id = contract_id_by_external_id(client, spec.external_id)
        if contract_id is None:
            raise RuntimeError(f"{spec.external_id} is not in the sandbox")
        items: list[dict[str, Any]] = []
        for event in grouped[seq]:
            body = volume.payload(event, spec)
            if body is None:
                deferred += 1
                continue
            item: dict[str, Any] = {
                "event_type": event.event_type,
                "effective_date": event.effective_date.isoformat(),
                "payload": body,
            }
            if event.obligation_key:
                item["obligation_key"] = event.obligation_key
            items.append(item)
        for start in range(0, len(items), MAX_EVENTS):
            batch = items[start : start + MAX_EVENTS]
            needs = volume.needs_evidence(EventAppendItemIn.model_validate(item) for item in batch)
            head = client.get_response(f"/contracts/{contract_id}")
            etag = head.headers.get("etag")
            answer = client.post(
                f"/contracts/{contract_id}/events",
                {
                    "events": batch,
                    "comment": f"perf month {MONTH_24}",
                    "evidence_file_ids": [evidence_of(spec.entity_code)] if needs else [],
                },
                if_match=etag,
                idempotency_key=manifest.idempotency_key(grouped[seq][start].seq),
            )
            # 201 with a submission: nothing is appended until the reviewer approves the request
            request_id = answer.get("approval_request_id") if isinstance(answer, Mapping) else None
            if request_id is not None:
                approve_request(reviewer, str(request_id))
            appended += len(batch)
        touched += 1
    return Prepared(appended, deferred, touched, None)


def publish_concurrency(
    accountant: PerfClient, reviewer: PerfClient, *, effective_from: str
) -> str:
    """``platform.job_concurrency = 8`` as a TENANT-scoped PLATFORM registry version: create and
    submit as the accountant (config.author), approve as the reviewer (config.approve), publish as
    the accountant (05 PERF-20; API-R-25 policies)."""
    created: Mapping[str, Any] = accountant.post(
        "/policies",
        {
            "category": "PLATFORM",
            "scope": "TENANT",
            "values": {CONCURRENCY_KEY: CONCURRENCY},
            "effective_from": effective_from,
        },
    )
    policy_id = str(created["id"])
    accountant.post(f"/policies/{policy_id}/submit", {"comment": "perf harness"})
    pending = reviewer.get(
        "/approvals",
        {"status": "PENDING", "subject_type": "REGISTRY_VERSION", "subject_id": policy_id},
    )
    for item in pending.get("items", []):
        reviewer.post(
            f"/approvals/{item['id']}/approve",
            {
                "subject_content_sha256": item["subject_content_sha256"],
                "impact_preview_sha256": item.get("impact_preview_sha256"),
                "comment": "perf harness",
            },
        )
    accountant.post(f"/policies/{policy_id}/publish", {"comment": "perf harness"})
    return policy_id
