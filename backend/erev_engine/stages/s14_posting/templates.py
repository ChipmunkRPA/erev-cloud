"""Stage 14 template parts and counter-entry roles (ENGINE_SPEC_B §14.2.1; BUILD_SPEC END-4).

Private to stage 14 (DG-ENG-07); the package exports the constants. ``JET_PARTS`` is Table 14-A: one
entry per template part of POLICIES §2.3 (JET rules R1 to R9; JET-01 to JET-17), with its 04 E-29
entry kind, its debit and credit roles in the direction of a positive target (a negative economic
effect swaps the sides, R4 and POLICIES §0.9), its owner entity and subject, the part whose target
carries it when it has no target of its own (S14-R-02, S14-R-03), and its triggers: the 04 E-03
literals and E-31 close-run passes of table 2.3-B (R9). ``TRIGGER_FAMILIES`` inverts the triggers
to the table 2.3-B rows.

``COUNTER_ROLES`` fixes the counter-entry roles whose other side belongs to another subledger
(05 §3.6.1; POLICIES table 0.8-A; D-14a). The parts read those sides from it, so a later amendment
changes one table. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.enums import AccountRole, ContractEventType

__all__ = [
    "ADJUSTMENT_ENTITY",
    "ASSET_ENTITY",
    "BY_SUBJECT",
    "CLEARING_PURPOSES",
    "CLOSE_RUN_PASSES",
    "CONTRACTING",
    "COUNTER_ROLES",
    "CREDIT",
    "DEBIT",
    "ENTRY_KINDS",
    "INTERCOMPANY_ROLES",
    "JET_02_TRIGGERS",
    "JET_PARTS",
    "NOT_A_CONTRACT_EVENT",
    "ONE",
    "PERFORMING",
    "RESERVED_ROLES",
    "SPLIT",
    "TEMPLATE_REASONS",
    "TRIGGER_FAMILIES",
    "JetPart",
    "Role",
    "Side",
]

DEBIT: Final = "DEBIT"
CREDIT: Final = "CREDIT"
ONE: Final = "ONE"  # a single role
SPLIT: Final = "SPLIT"  # several roles share the amount (agent, tax, reclass roles; S14-R-01)
BY_SUBJECT: Final = "BY_SUBJECT"  # one role, chosen by the subject (asset kind, balance role)
_SELECTIONS: Final = frozenset({ONE, SPLIT, BY_SUBJECT})

CONTRACTING: Final = "CONTRACTING"
PERFORMING: Final = "PERFORMING"
ASSET_ENTITY: Final = "ASSET_ENTITY"
ADJUSTMENT_ENTITY: Final = "ADJUSTMENT_ENTITY"
_OWNERS: Final = frozenset({CONTRACTING, PERFORMING, ASSET_ENTITY, ADJUSTMENT_ENTITY})

OBLIGATION: Final = "OBLIGATION"
CONTRACT_ENTITY: Final = "CONTRACT_ENTITY"  # <contract>@<entity>
GROUP_ENTITY: Final = "GROUP_ENTITY"  # <group>@<entity>
COST_ASSET: Final = "COST_ASSET"
LOSS_UNIT: Final = "LOSS_UNIT"
OBLIGATION_OR_CONTRACT: Final = "OBLIGATION_OR_CONTRACT"
_SUBJECTS: Final = frozenset(
    {OBLIGATION, CONTRACT_ENTITY, GROUP_ENTITY, COST_ASSET, LOSS_UNIT, OBLIGATION_OR_CONTRACT}
)

# 04 E-31 posting kinds that name the close-run passes (05 RCP-08).
CLOSE_RUN_PASSES: Final = ("CLOSE_RELEASE", "FX_REMEASUREMENT", "NETTING_RECLASS")
# Table 2.3-B JET-01b: the 606-10-25-7 evaluation on every event appended while NOT_A_CONTRACT.
NOT_A_CONTRACT_EVENT: Final = "NOT_A_CONTRACT_EVENT"
# Table 2.3-B JET-02 triggers, reused by JET-11, JET-13, JET-14 and JET-17.
JET_02_TRIGGERS: Final = (
    "DELIVERY_RECORDED",
    "PROGRESS_RECORDED",
    "MILESTONE_ACHIEVED",
    "COST_INCURRED",
    "USAGE_REPORTED",
    "ESTIMATE_CHANGED",
    "CLOSE_RELEASE",
)
# 04 E-29 subledger_entry_kind (rev 1.2).
ENTRY_KINDS: Final = frozenset(
    {
        "REVENUE_RECOGNITION",
        "BILLING",
        "CREDIT_MEMO",
        "NETTING_RECLASS",
        "NETTING_RECLASS_REVERSAL",
        "REFUND_LIABILITY",
        "RETURN_ASSET",
        "DEPOSIT",
        "CONSIDERATION_PAYABLE",
        "CONTRACT_COST_CAPITALIZATION",
        "CONTRACT_COST_AMORTIZATION",
        "CONTRACT_COST_IMPAIRMENT",
        "LOSS_PROVISION",
        "WARRANTY_ACCRUAL",
        "FINANCING_INTEREST",
        "FX_REMEASUREMENT",
        "FX_ROUNDING",
        "INTERCOMPANY",
        "PRE_STANDARD_REVENUE",
        "NONCASH_CONSIDERATION",
        "SALES_TAX",
        "MANUAL_ADJUSTMENT",
        "REVERSAL",
        "RECEIVABLE_CONTRA",
    }
)
# 04 E-109 clearing_purpose (D-14a).
CLEARING_PURPOSES: Final = frozenset(
    {"BILLING", "UNAPPLIED_CASH", "AP_SUPPLIER", "INVENTORY", "EQUITY", "INVESTMENTS"}
)
RESERVED_ROLES: Final = frozenset({"RETAINED_EARNINGS", "FINANCING_OBLIGATION"})  # D-14a
INTERCOMPANY_ROLES: Final = frozenset({"INTERCOMPANY_DUE_TO", "INTERCOMPANY_DUE_FROM"})
_TRIGGERS: Final = frozenset(
    {*(literal.value for literal in ContractEventType), *CLOSE_RUN_PASSES, NOT_A_CONTRACT_EVENT}
)


@dataclass(frozen=True, slots=True)
class Role:
    """An account role with its clearing purpose, present exactly on ``BILLING_CLEARING`` (R8)."""

    account_role: str  # E-01
    clearing_purpose: str | None = None  # E-109

    def __post_init__(self) -> None:
        AccountRole(self.account_role)
        if self.account_role in RESERVED_ROLES:
            raise ValueError(f"{self.account_role} is reserved and never emitted (D-14a)")
        if (self.account_role == "BILLING_CLEARING") != (self.clearing_purpose is not None):
            raise ValueError("clearing_purpose is present exactly on BILLING_CLEARING (R8; E-109)")
        if self.clearing_purpose is not None and self.clearing_purpose not in CLEARING_PURPOSES:
            raise ValueError(f"unknown clearing purpose {self.clearing_purpose!r} (E-109)")

    @property
    def label(self) -> str:
        """``<role>`` or ``BILLING_CLEARING:<purpose>`` (the override key of T-REF-15)."""
        if self.clearing_purpose is None:
            return self.account_role
        return f"{self.account_role}:{self.clearing_purpose}"


@dataclass(frozen=True, slots=True)
class Side:
    """The roles of one side of a template part and how the side's amount reaches them."""

    roles: tuple[Role, ...]
    selection: str  # ONE | SPLIT | BY_SUBJECT

    def __post_init__(self) -> None:
        if self.selection not in _SELECTIONS:
            raise ValueError(f"unknown side selection {self.selection!r}")
        if (self.selection == ONE) != (len(self.roles) == 1) or not self.roles:
            raise ValueError("a ONE side has one role; SPLIT and BY_SUBJECT sides have several")
        if len({role.label for role in self.roles}) != len(self.roles):
            raise ValueError("a side names each role once")

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(role.label for role in self.roles)


@dataclass(frozen=True, slots=True)
class JetPart:
    """One template part of Table 14-A (POLICIES §2.3)."""

    part: str  # JET_PARTS key, for example "JET-02 principal"
    template: str  # POLICIES §2.3 template id, for example "JET-04b" or "JET-09a′"
    family: str  # table 2.3-B row, for example "JET-04"
    entry_kind: str | None  # E-29; None when the part posts no lines of its own
    debit: Side | None  # roles debited by a positive target (R4)
    credit: Side | None
    owner: str | None  # CONTRACTING | PERFORMING | ASSET_ENTITY | ADJUSTMENT_ENTITY
    subject: str | None  # OBLIGATION, CONTRACT_ENTITY, GROUP_ENTITY, COST_ASSET, LOSS_UNIT
    triggers: tuple[str, ...]  # E-03 literals, E-31 passes, NOT_A_CONTRACT_EVENT (table 2.3-B)
    through: str | None = None  # the part whose target carries this template (S14-R-02, S14-R-03)
    book: str | None = None  # "LEGACY" for JET-15 (R5, R6)
    counterparty: str | None = None  # the entity tagged on intercompany roles (R3)
    # The reason_code the part's lines carry (S11-R-12, S11-R-13; S14-R-27): None for every
    # part but JET-09e (TERMINATION_ACCELERATION) and JET-09f (CLAWBACK).
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.entry_kind is not None and self.entry_kind not in ENTRY_KINDS:
            raise ValueError(f"{self.part}: unknown entry kind {self.entry_kind!r} (E-29)")
        if (self.debit is None) != (self.credit is None):
            raise ValueError(f"{self.part}: a part has both sides or none")
        if self.debit is not None and self.entry_kind is None:
            raise ValueError(f"{self.part}: a part with roles has an entry kind")
        if self.owner is not None and self.owner not in _OWNERS:
            raise ValueError(f"{self.part}: unknown owner {self.owner!r}")
        if self.subject is not None and self.subject not in _SUBJECTS:
            raise ValueError(f"{self.part}: unknown subject {self.subject!r}")
        unknown = sorted(set(self.triggers) - _TRIGGERS)
        if not self.triggers or unknown:
            raise ValueError(f"{self.part}: unknown or missing triggers {unknown}")
        roles = {
            role.account_role for side in (self.debit, self.credit) if side for role in side.roles
        }
        if (self.counterparty is not None) != bool(roles & INTERCOMPANY_ROLES):
            raise ValueError(f"{self.part}: a counterparty is tagged exactly on intercompany roles")

    @property
    def has_amounts(self) -> bool:
        """Whether the part produces amounts: its own lines, or a share of another part's target."""
        return self.entry_kind is not None or self.through is not None


def _one(role: str) -> Side:
    return Side((Role(role),), ONE)


def _counter(part: str, side: str) -> Side:
    return Side((COUNTER_ROLES[(part, side)],), ONE)


def _split(*roles: Role) -> Side:
    return Side(tuple(roles), SPLIT)


def _by_subject(*roles: str) -> Side:
    return Side(tuple(Role(role) for role in roles), BY_SUBJECT)


_CL: Final = "CONTRACT_LIABILITY"
_ASSETS: Final = ("COST_TO_OBTAIN_ASSET", "COST_TO_FULFILL_ASSET")
_UNAPPLIED_CASH: Final = Role("BILLING_CLEARING", "UNAPPLIED_CASH")
_COST_CLEARING: Final = Role("CONTRACT_COST_CLEARING")

COUNTER_ROLES: Final[Mapping[tuple[str, str], Role]] = MappingProxyType(
    {
        ("JET-01b receipt", DEBIT): _UNAPPLIED_CASH,
        ("JET-01b refund", CREDIT): _UNAPPLIED_CASH,
        ("JET-02 agent", CREDIT): Role("BILLING_CLEARING", "AP_SUPPLIER"),
        ("JET-07c", CREDIT): Role("COST_OF_REVENUE"),
        ("JET-07d", DEBIT): Role("BILLING_CLEARING", "INVENTORY"),
        ("JET-09a", CREDIT): _COST_CLEARING,
        ("JET-09a′", CREDIT): _COST_CLEARING,
        ("JET-09f", DEBIT): _COST_CLEARING,
        ("JET-14 share-based", CREDIT): Role("BILLING_CLEARING", "EQUITY"),
        ("JET-16 claim release", CREDIT): Role("COST_OF_REVENUE"),
        ("JET-17 receipt", DEBIT): Role("BILLING_CLEARING", "INVESTMENTS"),
    }
)

_AMENDMENT: Final = ("CONTRACT_AMENDED", "CONTRACT_TERMINATED")
_PARTS: Final = (
    JetPart("JET-01", "JET-01", "JET-01", None, None, None, None, None, ("CONTRACT_ACTIVATED",)),
    JetPart(
        "JET-01b receipt",
        "JET-01b",
        "JET-01b",
        "DEPOSIT",
        _counter("JET-01b receipt", DEBIT),
        _one("DEPOSIT_LIABILITY"),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("PAYMENT_RECEIVED", "BILLING_RECORDED"),
    ),
    JetPart(
        "JET-01b criteria met",
        "JET-01b",
        "JET-01b",
        "DEPOSIT",
        _one("DEPOSIT_LIABILITY"),
        _one(_CL),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("CONTRACT_CRITERIA_MET",),
    ),
    JetPart(
        "JET-01b 25-7 revenue",
        "JET-01b",
        "JET-01b",
        "REVENUE_RECOGNITION",
        _one("DEPOSIT_LIABILITY"),
        _one("REVENUE"),
        CONTRACTING,
        OBLIGATION,
        (NOT_A_CONTRACT_EVENT, "CLOSE_RELEASE"),
    ),
    JetPart(
        "JET-01b refund",
        "JET-01b",
        "JET-01b",
        "DEPOSIT",
        _one("DEPOSIT_LIABILITY"),
        _counter("JET-01b refund", CREDIT),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("CONTRACT_TERMINATED",),
    ),
    JetPart(
        "JET-02 principal",
        "JET-02",
        "JET-02",
        "REVENUE_RECOGNITION",
        _one(_CL),
        _one("REVENUE"),
        CONTRACTING,
        OBLIGATION,
        JET_02_TRIGGERS,
    ),
    JetPart(
        "JET-02 agent",
        "JET-02",
        "JET-02",
        "REVENUE_RECOGNITION",
        _one(_CL),
        _split(Role("REVENUE"), COUNTER_ROLES[("JET-02 agent", CREDIT)]),
        CONTRACTING,
        OBLIGATION,
        JET_02_TRIGGERS,
    ),
    JetPart(
        "JET-03 invoice",
        "JET-03",
        "JET-03",
        "BILLING",
        _one("ACCOUNTS_RECEIVABLE"),
        _split(Role(_CL), Role("SALES_TAX_PAYABLE")),
        CONTRACTING,
        OBLIGATION,
        ("BILLING_RECORDED",),
    ),
    JetPart(
        "JET-03 credit memo",
        "JET-03",
        "JET-03",
        "CREDIT_MEMO",
        _split(Role(_CL), Role("SALES_TAX_PAYABLE")),
        _one("ACCOUNTS_RECEIVABLE"),
        CONTRACTING,
        OBLIGATION,
        ("CREDIT_MEMO_RECORDED",),
    ),
    JetPart(
        "JET-04a",
        "JET-04a",
        "JET-04",
        "REVENUE_RECOGNITION",
        _one(_CL),
        _one("REVENUE"),
        CONTRACTING,
        OBLIGATION,
        ("ESTIMATE_CHANGED", "USAGE_REPORTED", "CLOSE_RELEASE"),
        through="JET-02 principal",
    ),
    JetPart(
        "JET-04b",
        "JET-04b",
        "JET-04",
        "REFUND_LIABILITY",
        _one(_CL),
        _one("REFUND_LIABILITY"),
        CONTRACTING,
        OBLIGATION_OR_CONTRACT,
        ("ESTIMATE_CHANGED", "USAGE_REPORTED", "BILLING_RECORDED", "CREDIT_MEMO_RECORDED")
        + ("CLOSE_RELEASE",),
    ),
    JetPart(
        "JET-04c",
        "JET-04c",
        "JET-04",
        "RECEIVABLE_CONTRA",
        _one(_CL),
        _one("RECEIVABLE_CONTRA"),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("ESTIMATE_CHANGED", "BILLING_RECORDED", "CREDIT_MEMO_RECORDED"),
    ),
    JetPart(
        "JET-05a",
        "JET-05a",
        "JET-05",
        "REVENUE_RECOGNITION",
        _one(_CL),
        _one("REVENUE"),
        CONTRACTING,
        OBLIGATION,
        _AMENDMENT,
        through="JET-02 principal",
    ),
    JetPart(
        "JET-05b",
        "JET-05b",
        "JET-05",
        "REVENUE_RECOGNITION",
        _one("REVENUE"),
        _one(_CL),
        CONTRACTING,
        OBLIGATION,
        _AMENDMENT,
        through="JET-02 principal",
    ),
    JetPart(
        "JET-05c",
        "JET-05c",
        "JET-05",
        "REFUND_LIABILITY",
        _one("REVENUE"),
        _one("REFUND_LIABILITY"),
        CONTRACTING,
        OBLIGATION,
        _AMENDMENT,
    ),
    JetPart(
        "JET-06 reclass",
        "JET-06",
        "JET-06",
        "NETTING_RECLASS",
        _split(Role("UNBILLED_RECEIVABLE"), Role("CONTRACT_ASSET")),
        _one(_CL),
        CONTRACTING,
        OBLIGATION,
        ("NETTING_RECLASS",),
    ),
    JetPart(
        "JET-06 reversal",
        "JET-06",
        "JET-06",
        "NETTING_RECLASS_REVERSAL",
        _one(_CL),
        _split(Role("UNBILLED_RECEIVABLE"), Role("CONTRACT_ASSET")),
        CONTRACTING,
        OBLIGATION,
        ("NETTING_RECLASS",),
    ),
    JetPart(
        "JET-07a",
        "JET-07a",
        "JET-07",
        None,
        None,
        None,
        CONTRACTING,
        OBLIGATION,
        ("DELIVERY_RECORDED",),
        through="JET-02 principal",
    ),
    JetPart(
        "JET-07b",
        "JET-07b",
        "JET-07",
        None,
        None,
        None,
        CONTRACTING,
        OBLIGATION,
        ("DELIVERY_RECORDED", "RETURN_RECORDED"),
        through="JET-04b",
    ),
    JetPart(
        "JET-07c",
        "JET-07c",
        "JET-07",
        "RETURN_ASSET",
        _one("RETURN_ASSET"),
        _counter("JET-07c", CREDIT),
        CONTRACTING,
        OBLIGATION,
        ("DELIVERY_RECORDED", "ESTIMATE_CHANGED", "RETURN_RECORDED", "CLOSE_RELEASE"),
    ),
    JetPart(
        "JET-07d",
        "JET-07d",
        "JET-07",
        "RETURN_ASSET",
        _counter("JET-07d", DEBIT),
        _one("RETURN_ASSET"),
        CONTRACTING,
        OBLIGATION,
        ("RETURN_RECORDED",),
    ),
    JetPart(
        "JET-08 exercise",
        "JET-08",
        "JET-08",
        None,
        None,
        None,
        None,
        None,
        ("MATERIAL_RIGHT_EXERCISED",),
    ),
    JetPart(
        "JET-08 expiry",
        "JET-08",
        "JET-08",
        "REVENUE_RECOGNITION",
        _one(_CL),
        _one("REVENUE"),
        CONTRACTING,
        OBLIGATION,
        ("MATERIAL_RIGHT_EXPIRED",),
        through="JET-02 principal",
    ),
    JetPart(
        "JET-09a",
        "JET-09a",
        "JET-09",
        "CONTRACT_COST_CAPITALIZATION",
        _one("COST_TO_OBTAIN_ASSET"),
        _counter("JET-09a", CREDIT),
        ASSET_ENTITY,
        COST_ASSET,
        ("COST_INCURRED",),
    ),
    JetPart(
        "JET-09a′",
        "JET-09a′",
        "JET-09",
        "CONTRACT_COST_CAPITALIZATION",
        _one("COST_TO_FULFILL_ASSET"),
        _counter("JET-09a′", CREDIT),
        ASSET_ENTITY,
        COST_ASSET,
        ("COST_INCURRED",),
    ),
    JetPart(
        "JET-09b",
        "JET-09b",
        "JET-09",
        "CONTRACT_COST_AMORTIZATION",
        _one("CONTRACT_COST_AMORTIZATION"),
        _by_subject(*_ASSETS),
        ASSET_ENTITY,
        COST_ASSET,
        ("CLOSE_RELEASE",),
    ),
    JetPart(
        "JET-09c",
        "JET-09c",
        "JET-09",
        "CONTRACT_COST_IMPAIRMENT",
        _one("CONTRACT_COST_IMPAIRMENT"),
        _by_subject(*_ASSETS),
        ASSET_ENTITY,
        COST_ASSET,
        ("CLOSE_RELEASE",),
    ),
    JetPart(
        "JET-09d",
        "JET-09d",
        "JET-09",
        "CONTRACT_COST_IMPAIRMENT",
        _by_subject(*_ASSETS),
        _one("CONTRACT_COST_IMPAIRMENT"),
        ASSET_ENTITY,
        COST_ASSET,
        ("CLOSE_RELEASE",),
    ),
    JetPart(
        "JET-09e",
        "JET-09e",
        "JET-09",
        "CONTRACT_COST_AMORTIZATION",
        _one("CONTRACT_COST_AMORTIZATION"),
        _by_subject(*_ASSETS),
        ASSET_ENTITY,
        COST_ASSET,
        ("CONTRACT_TERMINATED",),
        reason_code="TERMINATION_ACCELERATION",
    ),
    JetPart(
        "JET-09f",
        "JET-09f",
        "JET-09",
        "CONTRACT_COST_CAPITALIZATION",
        _counter("JET-09f", DEBIT),
        _by_subject(*_ASSETS),
        ASSET_ENTITY,
        COST_ASSET,
        ("COST_INCURRED",),
        reason_code="CLAWBACK",
    ),
    JetPart(
        "JET-10a",
        "JET-10a",
        "JET-10",
        "FX_REMEASUREMENT",
        _one(_CL),
        _one("FX_GAIN_LOSS"),
        CONTRACTING,
        GROUP_ENTITY,
        ("FX_REMEASUREMENT", "BILLING_RECORDED", "PAYMENT_RECEIVED"),
    ),
    JetPart(
        "JET-10a′",
        "JET-10a′",
        "JET-10",
        "FX_REMEASUREMENT",
        _one("ACCOUNTS_RECEIVABLE"),
        _one("FX_GAIN_LOSS"),
        CONTRACTING,
        GROUP_ENTITY,
        ("FX_REMEASUREMENT",),
    ),
    JetPart(
        "JET-10b",
        "JET-10b",
        "JET-10",
        "FX_REMEASUREMENT",
        _one("FX_GAIN_LOSS"),
        _one(_CL),
        CONTRACTING,
        GROUP_ENTITY,
        ("FX_REMEASUREMENT",),
    ),
    JetPart(
        "JET-10c",
        "JET-10c",
        "JET-10",
        "FX_REMEASUREMENT",
        _one("FX_GAIN_LOSS"),
        _one(_CL),
        CONTRACTING,
        GROUP_ENTITY,
        ("CREDIT_MEMO_RECORDED",),
    ),
    JetPart(
        "JET-10d",
        "JET-10d",
        "JET-10",
        "FX_REMEASUREMENT",
        _one("FX_GAIN_LOSS"),
        _by_subject("REFUND_LIABILITY", "DEPOSIT_LIABILITY", "CONSIDERATION_PAYABLE"),
        CONTRACTING,
        GROUP_ENTITY,
        ("FX_REMEASUREMENT", "CLOSE_RELEASE", "CREDIT_MEMO_RECORDED", "RETURN_RECORDED")
        + ("CONTRACT_CRITERIA_MET", "CONTRACT_TERMINATED", NOT_A_CONTRACT_EVENT),
    ),
    JetPart(
        "JET-11a",
        "JET-11a",
        "JET-11",
        "FINANCING_INTEREST",
        _one(_CL),
        _one("INTEREST_INCOME"),
        CONTRACTING,
        CONTRACT_ENTITY,
        JET_02_TRIGGERS,
    ),
    JetPart(
        "JET-11b",
        "JET-11b",
        "JET-11",
        "FINANCING_INTEREST",
        _one("INTEREST_EXPENSE"),
        _one(_CL),
        CONTRACTING,
        CONTRACT_ENTITY,
        JET_02_TRIGGERS,
    ),
    JetPart(
        "JET-12",
        "JET-12",
        "JET-12",
        "LOSS_PROVISION",
        _one("LOSS_EXPENSE"),
        _one("LOSS_PROVISION"),
        CONTRACTING,
        LOSS_UNIT,
        ("ESTIMATE_CHANGED", "COST_INCURRED", "CLOSE_RELEASE"),
    ),
    JetPart(
        "JET-13 contracting",
        "JET-13",
        "JET-13",
        "INTERCOMPANY",
        _one(_CL),
        _one("INTERCOMPANY_DUE_TO"),
        CONTRACTING,
        OBLIGATION,
        JET_02_TRIGGERS,
        counterparty=PERFORMING,
    ),
    JetPart(
        "JET-13 performing",
        "JET-13",
        "JET-13",
        "INTERCOMPANY",
        _one("INTERCOMPANY_DUE_FROM"),
        _one("REVENUE"),
        PERFORMING,
        OBLIGATION,
        JET_02_TRIGGERS,
        counterparty=CONTRACTING,
    ),
    JetPart(
        "JET-14 promised",
        "JET-14",
        "JET-14",
        "CONSIDERATION_PAYABLE",
        _one("CUSTOMER_INCENTIVE_ASSET"),
        _one("CONSIDERATION_PAYABLE"),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("CONTRACT_ACTIVATED", "CONTRACT_AMENDED"),
    ),
    JetPart(
        "JET-14 after revenue",
        "JET-14",
        "JET-14",
        "CONSIDERATION_PAYABLE",
        _one("REVENUE"),
        _one("CONSIDERATION_PAYABLE"),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("CONTRACT_ACTIVATED", "CONTRACT_AMENDED"),
    ),
    JetPart(
        "JET-14 release",
        "JET-14",
        "JET-14",
        "CONSIDERATION_PAYABLE",
        _one("REVENUE"),
        _one("CUSTOMER_INCENTIVE_ASSET"),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("BILLING_RECORDED", *JET_02_TRIGGERS),
    ),
    JetPart(
        "JET-14 share-based",
        "JET-14",
        "JET-14",
        "CONSIDERATION_PAYABLE",
        _one("REVENUE"),
        _counter("JET-14 share-based", CREDIT),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("ESTIMATE_CHANGED",),
    ),
    JetPart(
        "JET-15",
        "JET-15",
        "JET-15",
        "PRE_STANDARD_REVENUE",
        # D-89 L7-6-Q-8: LEGACY reverses the pre-standard revenue the ERP booked (S13-R-08).
        _one("PRE_STANDARD_REVENUE"),
        _one(_CL),
        CONTRACTING,
        OBLIGATION,
        ("PRE_STANDARD_REVENUE_RECORDED",),
        book="LEGACY",
    ),
    JetPart(
        "JET-16 accrual",
        "JET-16",
        "JET-16",
        "WARRANTY_ACCRUAL",
        _one("WARRANTY_EXPENSE"),
        _one("WARRANTY_PROVISION"),
        PERFORMING,
        OBLIGATION,
        ("DELIVERY_RECORDED",),
    ),
    JetPart(
        "JET-16 claim release",
        "JET-16",
        "JET-16",
        "WARRANTY_ACCRUAL",
        _one("WARRANTY_PROVISION"),
        _counter("JET-16 claim release", CREDIT),
        PERFORMING,
        OBLIGATION,
        ("COST_INCURRED",),
    ),
    JetPart(
        "JET-17 unconditional",
        "JET-17",
        "JET-17",
        "NONCASH_CONSIDERATION",
        _one("NONCASH_CONSIDERATION_ASSET"),
        _one(_CL),
        CONTRACTING,
        CONTRACT_ENTITY,
        JET_02_TRIGGERS,
    ),
    JetPart(
        "JET-17 receipt",
        "JET-17",
        "JET-17",
        "NONCASH_CONSIDERATION",
        _counter("JET-17 receipt", DEBIT),
        _one("NONCASH_CONSIDERATION_ASSET"),
        CONTRACTING,
        CONTRACT_ENTITY,
        ("PAYMENT_RECEIVED",),
    ),
)


def _index(parts: Iterable[JetPart]) -> Mapping[str, JetPart]:
    index: dict[str, JetPart] = {}
    for part in parts:
        if part.part in index:
            raise ValueError(f"template part {part.part} is defined twice")
        index[part.part] = part
    for part in index.values():
        if part.through is not None and part.through not in index:
            raise ValueError(f"{part.part} posts through the unknown part {part.through}")
    return MappingProxyType(index)


JET_PARTS: Final[Mapping[str, JetPart]] = _index(_PARTS)
# The reason codes Table 14-A parts stamp on their lines (S14-R-27): the reason variants of a
# role key; every other posted reason (LATE_EVENT, VOID, a manual adjustment's) is unattributable.
TEMPLATE_REASONS: Final[frozenset[str]] = frozenset(
    part.reason_code for part in JET_PARTS.values() if part.reason_code is not None
)


def _families(parts: Mapping[str, JetPart]) -> Mapping[str, tuple[str, ...]]:
    found: dict[str, set[str]] = {}
    for part in parts.values():
        for trigger in part.triggers:
            found.setdefault(trigger, set()).add(part.family)
    return MappingProxyType({trigger: tuple(sorted(found[trigger])) for trigger in sorted(found)})


# Table 2.3-B inverted: trigger -> the template rows it drives (R9).
TRIGGER_FAMILIES: Final[Mapping[str, tuple[str, ...]]] = _families(JET_PARTS)
