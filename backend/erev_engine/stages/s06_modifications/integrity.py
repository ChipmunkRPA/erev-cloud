"""Stage 06 modification integrity validator and refusal (B3-BS2-05; REQ-MOD-019, REQ-MOD-021).

``validate_modification`` is the pure function that the CTR modification command and the DIN
legacy modification template call before a modification commits. It returns 04 table 15.4-A codes
(S06-R-07; DEVIATIONS §5 #6, #20, #21, #27, #28, #30), each ``ERROR`` at stage 6:

- ``IMPORT_NO_DATA_ROWS``: a template modification (``template_mode`` set) without lines (TC-20,
  TC-RM-09). A native modification may carry no lines, for example a price change on satisfied
  performance through ``price_change_amount`` (S06-R-09).
- ``CONTRACT_NOT_FOUND``: the modification names a contract absent from the group (TC-11,
  TC-RM-14). The cross-file rules on obligations are then not evaluated.
- ``MOD_SIGN_MISMATCH``: a line whose quantity and consideration are both non-zero with opposite
  signs (TC-17; legacy 03 §3.1 "sign mismatch rejected").
- ``MOD_DUPLICATE_KEY``: a second line for the same obligation key and product (the SKU) (TC-12,
  TC-RM-10).
- ``POB_NOT_FOUND``: a line other than ``ADD`` naming an obligation absent from the contract.
- ``MOD_ATTRIBUTE_CONFLICT`` (ENB-6; DEV-035): a line on an existing obligation whose
  stratification, selling entity or account members differ from the stored obligation.
  ``ssp_version_label`` is exempt, because it prices the increment (POL-080 parity), and an ``ADD``
  line brings the attributes of a new obligation. Attribute changes are their own
  ``LINE_ATTRIBUTES_CHANGED`` events. Nothing is applied: the stored attributes stay.

``refuse`` is the refusal in ``apply`` (ENB-13). CV-44 leaves the type, cross-row and file codes
to the import pipeline, and the engine re-checks only what the whole stream can break: the
cross-file codes of ``REFUSED_CODES`` and a modification key applied twice (``MOD_DUPLICATE_KEY``).
Such an event never passed the import, so the engine raises
``EngineError("ENGINE_INVARIANT_VIOLATED")`` with ``detail["rule"] == "S06-R-07"`` and
``detail["code"]`` (CV-45). ``MOD_SIGN_MISMATCH``, duplicate lines and ``IMPORT_NO_DATA_ROWS`` are
not refused, so a template's own findings (for example ``VC_QUANTITY_NOT_ALLOWED``) still return
with the state (CV-15). Exported from the package ``__init__``. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    obligation_subject_key,
    payload_text,
)
from erev_engine.stages.s06_modifications.classify import ADD, ModificationView
from erev_engine.stages.state import AllocatedState, BookContext, EventView, Finding

__all__ = [
    "ATTRIBUTE_CONFLICT",
    "CONTRACT_NOT_FOUND",
    "DUPLICATE_KEY",
    "NO_DATA_ROWS",
    "POB_NOT_FOUND",
    "REFUSED_CODES",
    "SIGN_MISMATCH",
    "refuse",
    "validate_modification",
]

ATTRIBUTE_CONFLICT: Final = "MOD_ATTRIBUTE_CONFLICT"
CONTRACT_NOT_FOUND: Final = "CONTRACT_NOT_FOUND"
DUPLICATE_KEY: Final = "MOD_DUPLICATE_KEY"
NO_DATA_ROWS: Final = "IMPORT_NO_DATA_ROWS"
POB_NOT_FOUND: Final = "POB_NOT_FOUND"
SIGN_MISMATCH: Final = "MOD_SIGN_MISMATCH"
# The cross-file codes ``apply`` refuses (S06-R-07; CV-44, CV-45). ``MOD_ATTRIBUTE_CONFLICT`` is
# not refused: the handler never applies attribute members (REQ-MOD-021).
REFUSED_CODES: Final = frozenset({CONTRACT_NOT_FOUND, POB_NOT_FOUND})
# Boundary events that apply the T-CON-06 object named by ``modification_id`` with its lines.
_APPLYING: Final = frozenset({"CONTRACT_AMENDED", "CONTRACT_TERMINATED"})
_STAGE: Final = 6
_RULE: Final = "S06-R-07"
_SEPARATOR: Final = "|"


def validate_modification(
    ctx: BookContext, st: AllocatedState, modification: ModificationView
) -> tuple[Finding, ...]:
    """The 04 table 15.4-A findings of one modification before it commits, in CV-43 order.

    Every finding is ``ERROR`` at stage 6 with detail ``modification_key`` and ``rule``
    (S06-R-07). Line findings name the line index and the obligation's subject key; the header
    findings (``IMPORT_NO_DATA_ROWS``, ``CONTRACT_NOT_FOUND``) name the contract. No policy is
    read, so both presets give the same findings. ``ctx`` is the book context of the caller.
    """
    del ctx  # no rule reads a policy: the codes are the same under every preset
    mod = modification
    event_key = None if mod.event is None else mod.event.event_key
    contract = contract_subject_key(mod.contract_key)
    findings: list[Finding] = []

    def found(code: str, subject_key: str, **detail: str) -> None:
        members = {"modification_key": mod.modification_key, "rule": _RULE, **detail}
        findings.append(Finding(code, "ERROR", subject_key, members, _STAGE, event_key))

    if mod.template_mode is not None and not mod.lines:
        found(NO_DATA_ROWS, contract, template_mode=mod.template_mode)
    member = any(view.header.external_id == mod.contract_key for view in st.contracts)
    if not member:
        found(CONTRACT_NOT_FOUND, contract, contract_key=mod.contract_key)
    stored = {ob.obligation_key: ob for ob in st.obligations if ob.contract_key == mod.contract_key}
    first_lines: dict[tuple[str, str], int] = {}
    for index, line in enumerate(mod.lines):
        subject = obligation_subject_key(mod.contract_key, line.obligation_key)
        quantity, consideration = line.quantity_delta, line.consideration_delta
        if quantity != 0 and consideration != 0 and (quantity > 0) != (consideration > 0):
            found(
                SIGN_MISMATCH,
                subject,
                consideration_delta=format_exact(consideration),
                line_index=str(index),
                obligation_key=line.obligation_key,
                quantity_delta=format_exact(quantity),
            )
        product = line.product_code or ""
        first = first_lines.setdefault((line.obligation_key, product), index)
        if first != index:
            found(
                DUPLICATE_KEY,
                subject,
                first_line_index=str(first),
                line_index=str(index),
                obligation_key=line.obligation_key,
                product_code=product,
            )
        if not member or line.action == ADD:
            continue
        ob = stored.get(line.obligation_key)
        if ob is None:
            found(POB_NOT_FOUND, subject, line_index=str(index), obligation_key=line.obligation_key)
            continue
        members: list[str] = []
        stratification = line.members.get("stratification")
        if stratification is not None and stratification != ob.stratification:
            members.append("stratification")
        entity = line.members.get("selling_entity_code")
        if entity is not None and entity != ob.performing_entity:
            members.append("selling_entity_code")
        accounts = line.members.get("account_codes")
        if isinstance(accounts, Mapping):
            for role, code in sorted(accounts.items()):
                if ob.account_overrides.get(str(role)) != code:
                    members.append(f"account_codes.{role}")
        if members:
            found(
                ATTRIBUTE_CONFLICT,
                ob.subject_key,
                line_index=str(index),
                members=_SEPARATOR.join(members),
                obligation_key=ob.obligation_key,
            )
    return tuple(sorted(findings, key=Finding.sort_key))


def refuse(ctx: BookContext, st: AllocatedState, ev: EventView) -> None:
    """S06-R-07 at the boundary: raise for an event the import must have refused (CV-44, CV-45).

    Every stage 06 event names a member contract (``CONTRACT_NOT_FOUND``). A ``CONTRACT_AMENDED``
    or ``CONTRACT_TERMINATED`` must not carry a modification that an earlier such event of the
    stream applied, or that an obligation of the contract already records (``MOD_DUPLICATE_KEY``),
    and its T-CON-06 object must raise no code of ``REFUSED_CODES`` (``POB_NOT_FOUND``). The error
    detail holds
    ``rule`` S06-R-07, ``code``, ``event_key`` and the finding's detail. A payload without
    ``modification_id``, or naming a modification absent from the bundle, is left to the handler,
    which raises ``ValueError`` (CV-45).
    """
    header = next(
        (view.header for view in st.contracts if view.header.external_id == ev.contract_key), None
    )
    if header is None:
        raise _refusal(ev, CONTRACT_NOT_FOUND, contract_key=ev.contract_key)
    if ev.event_type not in _APPLYING:
        return
    key = payload_text(ev.payload, "modification_id")
    modification = next(
        (item for item in header.modifications if item.modification_key == key), None
    )
    if key is None or modification is None:
        return
    if _applied(st, ev, key):
        raise _refusal(ev, DUPLICATE_KEY, modification_key=key)
    view = ModificationView.of(ev.contract_key, modification, event=ev)
    for finding in validate_modification(ctx, st, view):
        if finding.code in REFUSED_CODES:
            raise _refusal(ev, finding.code, **finding.detail)


def _applied(st: AllocatedState, ev: EventView, key: str) -> bool:
    """True when ``key`` was applied before ``ev``: by an earlier event or on an obligation."""
    earlier = any(
        item.contract_key == ev.contract_key
        and item.event_type in _APPLYING
        and item.order_key < ev.order_key
        and payload_text(item.payload, "modification_id") == key
        for item in st.events
    )
    return earlier or any(
        ob.contract_key == ev.contract_key and ob.last_modification_key == key
        for ob in st.obligations
    )


def _refusal(ev: EventView, code: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        "the modification fails its integrity rules",
        subject_key=ev.contract_key,
        detail={**detail, "code": code, "event_key": ev.event_key, "rule": _RULE},
    )
