"""Retained disclosure inputs: reassemble chapters without reading current child files/policies."""

from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.reports import disclosure_assembly, disclosure_plan, disclosure_results
from erev_api.domain.reports.builders import RETAINED, SourceBinding
from erev_api.domain.reports.disclosure_plan import ChildSource
from erev_api.domain.reports.outputs import RunStamp, manifest
from erev_api.problems import Problem


def scope(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(run["tenant_id"]),
        "entity_ids": [str(identity) for identity in run["entity_ids"]],
        "book": run["book_code"],
        "known_at": run["known_at"].isoformat(),
        "parameters": dict(run["parameters"]),
    }


def capture(
    run: Mapping[str, Any], pack: disclosure_assembly.Pack, stamps: Mapping[UUID, RunStamp]
) -> dict[str, Any]:
    children = []
    for child in pack.children:
        stamp = stamps[child.source.run_id]
        saved_stamp = {field.name: getattr(stamp, field.name) for field in fields(stamp)}
        saved_stamp.update(
            run_at=stamp.run_at.isoformat(),
            entity_codes=list(stamp.entity_codes),
            parameters=dict(stamp.parameters),
        )
        children.append(
            {
                "key": child.source.key,
                "run_id": str(child.source.run_id),
                "job_id": None if child.source.job_id is None else str(child.source.job_id),
                "sections": list(child.source.sections),
                "basis": child.source.basis,
                "parameters_sha256": child.source.parameters_sha256,
                "output_sha256": child.output_sha256,
                "stamp": saved_stamp,
                "dataset": manifest.dataset_document(
                    manifest.report_reference(
                        stamp.report_code, stamp.report_name, stamp.report_version
                    ),
                    child.run["parameters"],
                    child.data,
                ),
            }
        )
    return {
        "version": 2,
        **scope(run),
        "children": children,
        "policies": dict(pack.policy_facts),
        "policy_sha256": pack.policy_sha256,
    }


def rebuild(
    run: Mapping[str, Any],
) -> tuple[disclosure_assembly.Pack, dict[UUID, RunStamp], dict[str, Any]]:
    """Verify retained identities and typed datasets, then rerun section/election assembly."""
    try:
        if (
            run["report_code"] != "disclosure_pack"
            or run["report_version"] != 1
            or run["period_lock_id"] is not None
        ):
            raise ValueError("report identity")
        binding = SourceBinding.from_stored(run["source_binding"])
        if (
            binding is None
            or binding.strategy != RETAINED
            or binding.report_version != 1
            or binding.cutoff != run["known_at"]
            or binding.open
        ):
            raise ValueError("binding")
        facts = dict(binding.evidence["disclosure_inputs"])
        if (
            facts["version"] != 2
            or sha256_hex(facts) != binding.evidence["disclosure_inputs_sha256"]
            or any(facts[key] != value for key, value in scope(run).items())
            or sha256_hex(facts["policies"]) != facts["policy_sha256"]
        ):
            raise ValueError("scope or digest")
        children = []
        stamps = {}
        for item in facts["children"]:
            document = item["dataset"]
            report = document["report"]
            code = report["code"]
            source = ChildSource(
                item["key"],
                tuple(item["sections"]),
                item["basis"],
                UUID(item["run_id"]),
                UUID(item["job_id"]),
                item["parameters_sha256"],
            )
            if (
                source.key != f"{code}:{source.basis}"
                or source.sections != disclosure_plan.SECTIONS[code]
                or source.basis not in {"PERIOD", "QUARTER_TO_DATE"}
                or report["version"] != 1
            ):
                raise ValueError("child identity")
            raw_stamp = item["stamp"]
            stamp = RunStamp(
                **{
                    **raw_stamp,
                    "entity_codes": tuple(raw_stamp["entity_codes"]),
                    "run_at": datetime.fromisoformat(raw_stamp["run_at"]),
                }
            )
            if stamp.run_at.tzinfo is None or (
                stamp.report_code != code
                or stamp.report_version != report["version"]
                or stamp.report_name != report["name"]
                or stamp.parameters != document["parameters"]
                or stamp.output_sha256 != item["output_sha256"]
                or stamp.book != facts["book"]
                or stamp.entity_codes != (facts["policies"]["entity_code"],)
            ):
                raise ValueError("child stamp")
            row = {
                "tenant_id": run["tenant_id"],
                "entity_ids": run["entity_ids"],
                "book_code": run["book_code"],
                "known_at": run["known_at"],
                "report_code": code,
                "report_version": report["version"],
                "parameters": document["parameters"],
                "output_sha256": item["output_sha256"],
                "row_count": document["row_count"],
                "control_totals": document["control_totals"],
                "tie_out_results": document["tie_out_results"],
                "report_run_no": stamp.report_run_no,
            }
            data = disclosure_results.decode(canonical_bytes(document), row, source)
            children.append(
                disclosure_results.CompletedChild(source, data, row, item["output_sha256"])
            )
            stamps[source.run_id] = stamp
        ids = [child.source.run_id for child in children]
        if len(stamps) != len(children):
            raise ValueError("duplicate child")
        if run.get("child_report_run_ids") and list(run["child_report_run_ids"]) != ids:
            raise ValueError("attached child identity")
        pack = disclosure_assembly.assemble(
            {**run, "child_report_run_ids": ids},
            disclosure_results.Collected((), tuple(children)),
            facts["policies"],
        )
        if capture(run, pack, stamps) != facts:
            raise ValueError("unsupported retained fields")
        return pack, stamps, facts
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise Problem("validation-failed", "The retained disclosure inputs are invalid.") from error
