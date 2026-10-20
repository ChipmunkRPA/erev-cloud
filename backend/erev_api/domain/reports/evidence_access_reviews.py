"""As-of access-review evidence for ACCESS packs, under the original source permission.

Returns source payloads for encrypted retention by the caller, never personal data in a
source-binding JSON column. A revocation request is distinct from confirmed revocation.
The audit slice establishes campaign transitions; it is not full-chain verification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import access_review_campaign, access_review_item, audit_event
from erev_api.domain.platform import file_access
from erev_api.domain.reports import evidence_access_roles
from erev_api.domain.reports.evidence_archive import MAX_PAYLOAD_BYTES, PackFile
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class ReviewEvidence:
    files: tuple[PackFile, ...]
    campaign_ids: tuple[UUID, ...]
    source_file_ids: tuple[UUID, ...]


def authorize(uow: UnitOfWork) -> None:
    evidence_access_roles.authorize(uow)
    if (
        "access.approve" not in uow.principal.permissions
        or uow.principal.permission_scopes.get("access.approve") != "*"
    ):
        raise Problem("forbidden", "Access-review evidence requires tenant-wide access.approve.")


def _invalid(detail: str) -> Problem:
    return Problem("validation-failed", f"Access-review evidence: {detail}")


def item_at(row: dict[str, Any], at: datetime) -> dict[str, Any]:
    """One-time decision followed by optional confirmed revocation; no later facts leak."""
    decided = row["decided_at"]
    revoked = row["revocation_completed_at"]
    if (
        row["decision"] not in {"PENDING", "CERTIFIED", "REVOKE_REQUESTED", "REVOKED"}
        or (decided is None) != (row["decision"] == "PENDING")
        or (decided is not None and (decided < row["created_at"] or row["reviewer_id"] is None))
        or (
            revoked is not None
            and (decided is None or revoked < decided or row["decision"] != "REVOKED")
        )
        or (row["decision"] == "REVOKED" and revoked is None)
    ):
        raise _invalid("an item has inconsistent decision timestamps.")
    decision = "PENDING" if decided is None or decided > at else row["decision"]
    if decision == "REVOKED" and revoked > at:
        decision = "REVOKE_REQUESTED"
    return {
        key: row[key]
        for key in (
            "id",
            "membership_id",
            "user_email_snapshot",
            "roles_snapshot",
            "last_login_at",
        )
    } | {
        "decision": decision,
        "reviewer_id": row["reviewer_id"] if decision != "PENDING" else None,
        "decided_at": decided if decision != "PENDING" else None,
        "comment": row["comment"] if decision != "PENDING" else None,
        "revocation_completed_at": revoked if decision == "REVOKED" else None,
    }


def _snapshot(uow: UnitOfWork, campaign: dict[str, Any], items: list[dict[str, Any]]) -> PackFile:
    identity = campaign["snapshot_file_id"]
    if identity is None or file_access.bound(uow.session, uow.ctx, identity) is None:
        raise Problem("not-found")
    metadata, stream = open_file(uow.session, identity, files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read(MAX_PAYLOAD_BYTES + 1)
    if (
        metadata["purpose"] != FilePurpose.REPORT_OUTPUT
        or metadata["media_type"] != "application/json"
        or len(content) > MAX_PAYLOAD_BYTES
        or len(content) != metadata["size_bytes"]
        or hashlib.sha256(content).hexdigest() != metadata["sha256"]
    ):
        raise _invalid("the original membership snapshot failed verification.")
    try:
        doc = json.loads(content)
        members = [UUID(item["membership_id"]) for item in doc["items"]]
        retained = {str(item["membership_id"]): item for item in items}
        fields = ("user_email_snapshot", "roles_snapshot")
        if (
            doc["campaign"]["id"] != str(campaign["id"])
            or datetime.fromisoformat(doc["campaign"]["started_at"]) != campaign["started_at"]
            or len(members) != len(set(members))
            or set(members) != {item["membership_id"] for item in items}
            or len(items) != len(members)
            or any(
                canonical_bytes({key: source[key] for key in fields})
                != canonical_bytes({key: retained[source["membership_id"]][key] for key in fields})
                or (
                    datetime.fromisoformat(source["last_login_at"])
                    if source["last_login_at"] is not None
                    else None
                )
                != retained[source["membership_id"]]["last_login_at"]
                for source in doc["items"]
            )
            or canonical_bytes(doc) != content
        ):
            raise ValueError("snapshot population")
    except (ValueError, TypeError, KeyError) as error:
        raise _invalid("the snapshot does not prove the complete campaign population.") from error
    return PackFile(f"access/reviews/{campaign['id']}/membership_snapshot.json", content)


def collect(uow: UnitOfWork, *, as_of: datetime) -> ReviewEvidence:
    authorize(uow)
    if as_of.tzinfo is None or as_of > uow.now:
        raise _invalid("the effective instant must be aware and no later than known-at.")
    tenant = uow.principal.tenant_id
    campaigns = [
        dict(row)
        for row in uow.session.execute(
            select(access_review_campaign)
            .where(
                access_review_campaign.c.tenant_id == tenant,
                access_review_campaign.c.created_at <= as_of,
            )
            .order_by(access_review_campaign.c.created_at, access_review_campaign.c.id)
        ).mappings()
    ]
    files: list[PackFile] = []
    sources: list[UUID] = []
    summaries = []
    for campaign in campaigns:
        identity = campaign["id"]
        events = [
            dict(row)
            for row in uow.session.execute(
                select(
                    audit_event.c.id,
                    audit_event.c.chain_seq,
                    audit_event.c.occurred_at,
                    audit_event.c.action,
                    audit_event.c.actor_id,
                    audit_event.c.before,
                    audit_event.c.after,
                )
                .where(
                    audit_event.c.tenant_id == tenant,
                    audit_event.c.object_type == "access_review_campaign",
                    audit_event.c.object_id == identity,
                    audit_event.c.outcome == "SUCCESS",
                    audit_event.c.occurred_at <= uow.now,
                )
                .order_by(audit_event.c.chain_seq)
            ).mappings()
        ]
        transitions = [
            event
            for event in events
            if isinstance(event["after"], dict) and "status" in event["after"]
        ]
        if not transitions or transitions[-1]["after"]["status"] != campaign["status"]:
            raise _invalid("the campaign's retained transition history is incomplete.")
        previous = None
        allowed = {
            "access_review_campaign.create": (None, "DRAFT"),
            "access_review_campaign.start": ("DRAFT", "IN_REVIEW"),
            "access_review_campaign.complete": ("IN_REVIEW", "COMPLETED"),
        }
        for event in transitions:
            before = event["before"].get("status") if isinstance(event["before"], dict) else None
            after = event["after"]["status"]
            pair = allowed.get(event["action"])
            valid = (
                (before, after) == pair
                if pair
                else (
                    event["action"] == "access_review_campaign.cancel"
                    and before in {"DRAFT", "IN_REVIEW"}
                    and after == "CANCELLED"
                )
            )
            if not valid or before != previous:
                raise _invalid("the campaign transition sequence has a gap or unsupported change.")
            previous = after
        selected = [event for event in transitions if event["occurred_at"] <= as_of]
        if not selected:
            raise _invalid("the campaign has no creation evidence at the selected instant.")
        status = selected[-1]["after"]["status"]
        started = campaign["started_at"] is not None and campaign["started_at"] <= as_of
        if status in {"IN_REVIEW", "COMPLETED"} and not started:
            raise _invalid("campaign status precedes its recorded start.")
        if status == "COMPLETED" and (
            campaign["completed_at"] is None or campaign["completed_at"] > as_of
        ):
            raise _invalid("campaign completion timestamp differs from its transition.")
        items = (
            [
                dict(row)
                for row in uow.session.execute(
                    select(access_review_item)
                    .where(
                        access_review_item.c.tenant_id == tenant,
                        access_review_item.c.access_review_campaign_id == identity,
                    )
                    .order_by(access_review_item.c.id)
                ).mappings()
            ]
            if started
            else []
        )
        if any(row["created_at"] > as_of for row in items):
            raise _invalid("campaign items do not share the captured start population.")
        if started:
            files.append(_snapshot(uow, campaign, items))
            sources.append(campaign["snapshot_file_id"])
        outputs = [item_at(row, as_of) for row in items]
        counts = {
            decision: sum(item["decision"] == decision for item in outputs)
            for decision in ("PENDING", "CERTIFIED", "REVOKE_REQUESTED", "REVOKED")
        }
        summary = {
            "id": identity,
            "name": campaign["name"],
            "status": status,
            "campaign_as_of": campaign["as_of"],
            "created_at": campaign["created_at"],
            "started_at": campaign["started_at"] if started else None,
            "completed_at": campaign["completed_at"] if status == "COMPLETED" else None,
            "reviewer_membership_ids": campaign["reviewer_membership_ids"],
            "snapshot_file_id": campaign["snapshot_file_id"] if started else None,
            "counts": counts,
        }
        summaries.append(summary)
        files.append(
            PackFile(
                f"access/reviews/{identity}/review.json",
                canonical_bytes(
                    {
                        "as_of": as_of,
                        "known_at": uow.now,
                        "campaign": summary,
                        "items": outputs,
                        "campaign_transitions": [
                            event for event in events if event["occurred_at"] <= as_of
                        ],
                        "audit_basis": (
                            "Campaign transition slice; not full audit-chain verification."
                        ),
                        "membership_basis": (
                            "Original membership snapshot captured at started_at, "
                            "not campaign_as_of."
                        ),
                    }
                ),
            )
        )
    files.append(
        PackFile(
            "access/reviews/index.json",
            canonical_bytes(
                {
                    "as_of": as_of,
                    "known_at": uow.now,
                    "campaign_count": len(campaigns),
                    "campaigns": summaries,
                }
            ),
        )
    )
    return ReviewEvidence(tuple(files), tuple(row["id"] for row in campaigns), tuple(sources))
