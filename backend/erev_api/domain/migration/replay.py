"""Legacy template replay into a sandbox, the pure part (BUILD_SPEC LMG-4; D-31 mode (b);
ENGINE_SPEC §7.4 S07-R-12; 05 SBX-02, SBX-10; dev-guide §9.6 DG-PAR-04; legacy 07 §3; SCREENS_B
§10.3 "Plan"; PRD J-21.1; BUILD_SPEC GPB-3).

The replay plan is an ordered list of legacy template files, each with its template code, its
E-24 mode (modification files) and its effective date (progress and modification files).
``infer_template`` chooses template and mode from the file name as legacy 07 §3 chooses the
handler ("retrospective" → retrospective modification, "POB specific VC" → ``pob_price_change``,
"prospective" (also legacy's "propsective") → prospective; SKU SSP; Contract Setup; Progress
Tracking or delivery → progress).

The required plan length is derived from the reference database the migration was created with
(F-LMG record §4): one ``legacy_sku_ssp`` file when ``SKU_SSP`` holds rows, plus one file per
distinct ``Contract_Live`` version token (``Processing Time Log``) in order. The shipped step-04
database requires 4 files, the after-step-14 database 14. The reconciliation runs after the last
planned batch, so the checkpoint is the plan itself: LMG-4's 13-file plan against WLD-F-16
answers "Add 14 files in order.", and GPB-3 replays a 4-file plan against WLD-F-15 through the
same route. ``validate_plan`` carries the three SCREENS_B copies. Committing the batches (IPL-01
to IPL-12, no per-batch approval, BR-MIG-03), the sandbox (F-SNP) and promotion (SBX-10) belong
to the database slice.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final
from uuid import UUID

from erev_api.domain.migration.legacy_db import LegacyProfile, LegacyRow
from erev_api.problems import ProblemError

__all__ = [
    "COPY_COUNT",
    "COPY_DATE",
    "COPY_MODE",
    "DATED_TEMPLATES",
    "MODES",
    "TEMPLATE_CONTRACT_MODIFICATION",
    "TEMPLATE_CONTRACT_SETUP",
    "TEMPLATE_PROGRESS_TRACKING",
    "TEMPLATE_SKU_SSP",
    "TEMPLATES",
    "PlanItem",
    "PlanSlot",
    "ReplayBatch",
    "ReplayCheckpoint",
    "ReplayPlanShape",
    "ReplaySandboxRequest",
    "UploadParameters",
    "batches",
    "checkpoint",
    "infer_template",
    "plan_params",
    "replay_plan",
    "required_files",
    "sandbox_display_name",
    "slot_mismatches",
    "upload_parameters",
    "validate_plan",
]

# 04 T-IMP-01 LEGACY_V1 template codes (revision 0044 seeds; support.golden_streams.HANDLERS).
TEMPLATE_SKU_SSP: Final = "legacy_sku_ssp"
TEMPLATE_CONTRACT_SETUP: Final = "legacy_contract_setup"
TEMPLATE_PROGRESS_TRACKING: Final = "legacy_progress_tracking"
TEMPLATE_CONTRACT_MODIFICATION: Final = "legacy_contract_modification"
TEMPLATES: Final = (
    TEMPLATE_SKU_SSP,
    TEMPLATE_CONTRACT_SETUP,
    TEMPLATE_PROGRESS_TRACKING,
    TEMPLATE_CONTRACT_MODIFICATION,
)
MODES: Final = ("prospective", "retrospective", "pob_price_change")  # E-24
DATED_TEMPLATES: Final = frozenset({TEMPLATE_PROGRESS_TRACKING, TEMPLATE_CONTRACT_MODIFICATION})
COPY_COUNT: Final = "Add {n} files in order."
COPY_MODE: Final = "Choose a mode for {name}."
COPY_DATE: Final = "Enter the effective date for {name}."
_RULE: Final = "LMG-4"
_SANDBOX_SUFFIX: Final = " replay (Sandbox)"  # PRD J-21.2; SCREENS_B §10.3


@dataclass(frozen=True, slots=True)
class PlanItem:
    """One replay plan row (API-R-48 ``/import`` ``plan[]``: file, template, mode, date)."""

    file_name: str
    template_code: str
    mode: str | None = None
    effective_date: date | None = None
    file_id: UUID | None = None


def infer_template(file_name: str) -> tuple[str, str | None]:
    """Template code and E-24 mode from a legacy template file name (legacy 07 §3 handler
    selection); ``ValueError`` for a name no legacy template matches.
    """
    name = file_name.lower()
    if "sku ssp" in name or "ssp template" in name:
        return TEMPLATE_SKU_SSP, None
    if "contract setup" in name:
        return TEMPLATE_CONTRACT_SETUP, None
    if "progress tracking" in name or "delivery" in name:
        return TEMPLATE_PROGRESS_TRACKING, None
    if "modification" in name or "mod " in name:
        if "retrospective" in name and "pob specific vc" not in name:
            return TEMPLATE_CONTRACT_MODIFICATION, "retrospective"
        if "pob specific vc" in name:
            return TEMPLATE_CONTRACT_MODIFICATION, "pob_price_change"
        if "prospective" in name or "propsective" in name:
            return TEMPLATE_CONTRACT_MODIFICATION, "prospective"
        return TEMPLATE_CONTRACT_MODIFICATION, None
    raise ValueError(f"{file_name!r} matches no legacy template")


def required_files(profile: LegacyProfile) -> int:
    """The plan length the reference database requires: one SSP file when ``SKU_SSP`` holds rows,
    plus one file per distinct ``Contract_Live`` version token (F-LMG record §4).
    """
    return (1 if profile.sku_ssp_rows > 0 else 0) + len(profile.version_tokens)


def validate_plan(plan: Sequence[PlanItem], *, required: int) -> list[ProblemError]:
    """422 ``validation-failed`` errors of a replay plan (SCREENS_B §10.3 plan states): the plan
    length must equal ``required``; a modification file needs a mode; a progress or modification
    file needs an effective date; the template code must be a legacy v1 code; an SSP file, when
    present, comes first.
    """
    errors: list[ProblemError] = []
    if len(plan) != required:
        errors.append(
            ProblemError(field="plan", rule_id=_RULE, message=COPY_COUNT.format(n=required))
        )
    for index, item in enumerate(plan):
        prefix = f"plan[{index}]"
        if item.template_code not in TEMPLATES:
            errors.append(
                ProblemError(
                    field=f"{prefix}.template_code",
                    rule_id=_RULE,
                    message=f"Choose a legacy template for {item.file_name}.",
                )
            )
            continue
        if item.template_code == TEMPLATE_CONTRACT_MODIFICATION:
            if item.mode not in MODES:
                errors.append(
                    ProblemError(
                        field=f"{prefix}.mode",
                        rule_id=_RULE,
                        message=COPY_MODE.format(name=item.file_name),
                    )
                )
        elif item.mode is not None:
            errors.append(
                ProblemError(
                    field=f"{prefix}.mode",
                    rule_id=_RULE,
                    message=f"{item.file_name} takes no mode.",
                )
            )
        if item.template_code in DATED_TEMPLATES and item.effective_date is None:
            errors.append(
                ProblemError(
                    field=f"{prefix}.effective_date",
                    rule_id=_RULE,
                    message=COPY_DATE.format(name=item.file_name),
                )
            )
        if item.template_code == TEMPLATE_SKU_SSP and index != 0:
            errors.append(
                ProblemError(
                    field=f"{prefix}.template_code",
                    rule_id=_RULE,
                    message=f"Move {item.file_name} to the first position.",
                )
            )
    return errors


@dataclass(frozen=True, slots=True)
class ReplayBatch:
    """One import batch of the replay, in order (T-MIG-01 ``import_upload_ids`` position)."""

    order: int  # 1-based
    file_name: str
    template_code: str
    mode: str | None
    date_input: date | None  # the upload parameter of dated templates (DG-PAR-04)
    file_id: UUID | None


def batches(plan: Sequence[PlanItem]) -> tuple[ReplayBatch, ...]:
    """The ordered batch descriptors of a valid plan."""
    return tuple(
        ReplayBatch(
            order=index + 1,
            file_name=item.file_name,
            template_code=item.template_code,
            mode=item.mode,
            date_input=item.effective_date,
            file_id=item.file_id,
        )
        for index, item in enumerate(plan)
    )


def plan_params(profile: LegacyProfile) -> dict[str, str | int]:
    """The derivation inputs of the required plan length (ruling Q-1, D-98 candidate 42): the
    reference database digest, its distinct version-token count and its ``SKU_SSP`` row count,
    with the derived length, so a trace re-evaluates the plan from recorded inputs."""
    return {
        "source_sha256": profile.source_sha256,
        "version_count": len(profile.version_tokens),
        "sku_ssp_rows": profile.sku_ssp_rows,
        "required_files": required_files(profile),
    }


@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    """Where the reconciliation observes: after the last planned batch, against the reference
    database whose profile fixed the plan length (F-LMG record §4); ``params`` are the derivation
    inputs (``plan_params``).
    """

    required_files: int
    reference_versions: tuple[str, ...]
    latest_current_period: date | None
    has_sku_ssp: bool
    params: Mapping[str, str | int] = field(default_factory=dict)

    @property
    def reconcile_after(self) -> int:
        return self.required_files


def checkpoint(profile: LegacyProfile) -> ReplayCheckpoint:
    return ReplayCheckpoint(
        required_files=required_files(profile),
        reference_versions=profile.version_tokens,
        latest_current_period=profile.latest_current_period,
        has_sku_ssp=profile.sku_ssp_rows > 0,
        params=plan_params(profile),
    )


@dataclass(frozen=True, slots=True)
class UploadParameters:
    """The v1 import upload parameters of one planned batch, in the vocabulary of the golden
    handlers (legacy 07 §3; DG-PAR-04): the legacy template code, the E-24 mode of a modification
    file (else None), the ``date_input`` of a dated file (else None) and the file's SHA-256. This
    is what the reader (T1) passes to the import for each plan position."""

    template_code: str
    mode: str | None
    date_input: date | None
    file_sha256: str

    def as_json(self) -> dict[str, str | None]:
        return {
            "template_code": self.template_code,
            "mode": self.mode,
            "date_input": None if self.date_input is None else self.date_input.isoformat(),
            "file_sha256": self.file_sha256,
        }


def upload_parameters(batch: ReplayBatch, *, file_sha256: str) -> UploadParameters:
    """The upload parameters of ``batch``; ``file_sha256`` is the 64-hex digest of the file
    (``ValueError`` otherwise)."""
    digest = file_sha256.lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("file_sha256 must be a 64-character hex SHA-256 digest")
    return UploadParameters(
        template_code=batch.template_code,
        mode=batch.mode,
        date_input=batch.date_input,
        file_sha256=digest,
    )


def sandbox_display_name(tenant_display_name: str) -> str:
    """The replay sandbox name "<tenant display name> replay (Sandbox)" (PRD J-21.2)."""
    return f"{tenant_display_name}{_SANDBOX_SUFFIX}"


# --- the plan shape derived from the reference database (F-LMG record §4; ruling Q-1) -----------

_PREVIOUS_PERIOD: Final = "Previous Period"  # 04 LM-CL-32: NULL on a first version (a setup upload)


@dataclass(frozen=True, slots=True)
class PlanSlot:
    """One position of the plan the reference database requires: the SSP file first when
    ``SKU_SSP`` holds rows, then one slot per ``Contract_Live`` version token in ``Processing Time
    Log`` order. A slot whose rows all carry a NULL ``Previous Period`` is a setup upload (no
    effective date in the plan); every other slot is a dated upload whose ``effective_date`` is the
    version's ``Current Period``. The template of a dated slot is not derivable from
    ``Contract_Live`` (a progress upload and a modification write the same columns), so the plan
    item's template comes from the file name (``infer_template``) and the slot only fixes the
    count, the order and the date."""

    order: int  # 1-based
    version_token: str | None  # None for the SSP slot
    template_code: str | None  # TEMPLATE_SKU_SSP, TEMPLATE_CONTRACT_SETUP, or None (dated upload)
    effective_date: date | None
    is_setup: bool


@dataclass(frozen=True, slots=True)
class ReplayPlanShape:
    """What ``replay_plan`` derives from the reference database; ``params`` are the derivation
    inputs (``plan_params``; ruling Q-1)."""

    required_files: int
    slots: tuple[PlanSlot, ...]
    params: Mapping[str, str | int] = field(default_factory=dict)


def replay_plan(profile: LegacyProfile, rows: Iterable[LegacyRow]) -> ReplayPlanShape:
    """The plan shape the reference database requires (F-LMG record §4; ruling Q-1): the shipped
    step-04 database gives 4 slots (SSP; setup 2023-01-01; setup 2023-02-01; dated 2023-01-31),
    the after-step-14 output 14. ``rows`` are every ``Contract_Live`` row of the reference."""
    by_token: dict[str, list[LegacyRow]] = {}
    for row in rows:
        by_token.setdefault(row.processing_time_log, []).append(row)
    slots: list[PlanSlot] = []
    if profile.sku_ssp_rows > 0:
        slots.append(PlanSlot(1, None, TEMPLATE_SKU_SSP, None, False))
    for token in sorted(by_token):
        version = by_token[token]
        setup = all(row.values.get(_PREVIOUS_PERIOD) in (None, "") for row in version)
        periods = {row.current_period for row in version if row.current_period is not None}
        effective = next(iter(periods)) if len(periods) == 1 else None
        slots.append(
            PlanSlot(
                len(slots) + 1,
                token,
                TEMPLATE_CONTRACT_SETUP if setup else None,
                None if setup else effective,
                setup,
            )
        )
    return ReplayPlanShape(len(slots), tuple(slots), plan_params(profile))


def slot_mismatches(plan: Sequence[PlanItem], shape: ReplayPlanShape) -> list[ProblemError]:
    """The plan against the reference shape beyond ``validate_plan``: the SSP slot must hold the
    SSP file, a setup slot a setup file, and a dated slot a dated file whose ``effective_date`` is
    the version's ``Current Period`` (recorded engineering check, not a SCREENS_B copy)."""
    errors: list[ProblemError] = []
    if len(plan) != shape.required_files:
        return [
            ProblemError(
                field="plan", rule_id=_RULE, message=COPY_COUNT.format(n=shape.required_files)
            )
        ]
    for item, slot in zip(plan, shape.slots, strict=True):
        prefix = f"plan[{slot.order - 1}]"
        if slot.template_code is not None and item.template_code != slot.template_code:
            errors.append(
                ProblemError(
                    field=f"{prefix}.template_code",
                    rule_id=_RULE,
                    message=(
                        f"Position {slot.order} of the reference is a {slot.template_code} upload."
                    ),
                )
            )
        elif slot.template_code is None and item.template_code not in DATED_TEMPLATES:
            errors.append(
                ProblemError(
                    field=f"{prefix}.template_code",
                    rule_id=_RULE,
                    message=f"Position {slot.order} of the reference is a dated upload.",
                )
            )
        elif slot.effective_date is not None and item.effective_date != slot.effective_date:
            errors.append(
                ProblemError(
                    field=f"{prefix}.effective_date",
                    rule_id=_RULE,
                    message=(
                        f"Position {slot.order} of the reference is dated "
                        f"{slot.effective_date.isoformat()}."
                    ),
                )
            )
    return errors


@dataclass(frozen=True, slots=True)
class ReplaySandboxRequest:
    """What LMG-4 asks F-SNP for: an EMPTY sandbox of kind ``sandbox`` for the production tenant,
    named ``sandbox_display_name(<tenant display name>)``, never converted (DB-05, SBX-10).

    Implementer (cited, not copied): ``domain.platform.snapshot_dataset.empty_sandbox_plan``
    taking the caller's permission, with ``EMPTY_SANDBOX_PURPOSE == "EMPTY"`` — lane F-SNP,
    commit 6a6206b on ``sprint/l23-fsnp`` (steps authorise / provision / seed / audit; no dataset,
    no ``tenant_snapshot`` row). The caller passes ``migration.run`` as the permission.
    """

    source_tenant_id: UUID
    display_name: str
    permission: str = "migration.run"
