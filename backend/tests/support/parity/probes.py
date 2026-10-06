"""Legacy probe runner (docs/dev-guide.md §9.6 DG-PAR-06, DG-PAR-10, DG-PAR-11 and the table
"Probe import-status mapping"; docs/legacy/DEVIATIONS.md §7.3; BUILD_SPEC GPA-6).

``run`` replays one probe in its own fresh tenant under the preset (DG-PAR-06): the DG-PAR-04 world
of ``scenario.build`` with the probe's own tenant code, then each item of ``probe.json``
``sequence`` in order. Reset items are skipped. A button label maps to the handler that the golden
``step.json`` files pair with it, and the handler to its template and mode (DG-PAR-04). The file
comes from ``fixtures/legacy_probes/`` or ``fixtures/legacy_uat/`` by basename, and ``date_input``
is the upload parameter ``effective_date``. Before each item the clock advances one hour and both
personas sign in again. An upload that validates is diffed, submitted, approved by ak-approver and
committed (DG-PAR-10: probes never reject an approval). Each item keeps a :class:`ProbeUpload`: the
E-40 status (null when no ``import_upload`` row exists), the refusal problem, the SHA-256 of the
uploaded bytes, the findings read through API-R-43 and API-R-44, and the ASC606 obligation version
counts before and after the item.

``compare`` checks the expected object of ``deviations.json``:

- ``import_status``, ``error_code`` and ``detail`` through :func:`classify` (DG-PAR-10), and the
  asserted members of ``import_status_basis`` (``e40_import_status``; ``problem`` members ``slug``,
  ``status`` and ``errors[].rule_id``);
- ``findings`` as an ordered list (DG-PAR-11, :func:`finding_mismatches`);
- ``versions_before`` and ``versions_after`` around the last sequence item;
- ``watched_latest`` from the latest ASC606 obligation version through the 04 §17 LM-CL rows, at
  DG-PAR-05 precision for the measures of DG-OQ-05 and as stored for the posted amounts
  (``billed_cum``, ``pre_standard_revenue_*``; the L5-1-Q-34 reading of ``values``);
- a journal expectation ``je_gross_<label>`` or ``je_delta_<label>`` against report
  ``legacy_je_summary`` in the gross or adjustment view over the window of ``probe.json``
  ``reports[<key>]``, field by field as ``values.journal_mismatches`` compares kind
  ``journal_entry_totals`` (GPB-1).
  While that report has no builder (RPT-13), each such key is a mismatch naming ``BUILD_SPEC RPS``
  (B3-BS2-04; XR-12);
- an upload object ``<ordinal>_<label>_upload`` (rev 1.1, P4 ``first_2_28_upload``): the members
  above for the ``<ordinal>`` upload of the file uploaded more than once whose name holds the label
  with ``_`` read as ``.``; and a suffixed count ``versions_before_<ordinal>`` or
  ``versions_after_<ordinal>`` around that upload of the probe's one repeated file.

Values are compared under DG-PAR-07: amounts within 1/10000, journal amounts to the cent, codes,
counts and texts equal. ``detail`` follows D-87b (L7-1-Q-1): the stored message names the expected
key's contract, obligation and product as whole tokens and "requested <n>" and "remaining <m>". The
provenance keys of DG-PAR-06 are not asserted. Any other key fails the case (DG-PAR-09).

After each committed upload the probe world posts the close run's JET-06 reclass through
``support.parity.netting`` (L7-1-Q-6), as the scenario does after each golden step.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction
from functools import cache
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    calc_trace,
    contract,
    contract_version,
    import_upload,
    obligation_version,
)
from erev_api.domain.imports.queries import FINDING_SEVERITY
from erev_api.domain.reports.framework import BUILDERS
from erev_api.enums import BookCode
from erev_api.explain import store
from erev_api.problems import TYPE_BASE
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from support.factories import (
    IMPORT_ID_HEADER,
    IMPORTS_PATH,
    LEGACY_UAT,
    create_import,
    run_import_job,
    upload_import_source,
)
from support.golden_streams import GOLDEN_ROOT, HANDLERS
from support.legacy_replay import job_of, shown, submit
from support.parity import compare as parity_compare
from support.parity import netting, scenario, values
from support.parity.compare import Mismatch
from support.parity.integrity import GoldenCase
from support.reference import approve, get

__all__ = [
    "COMMITTED",
    "COMMITTED_WITH_FINDINGS",
    "JOURNAL_NOT_BUILT",
    "JOURNAL_REPORT",
    "KIND",
    "REJECTED",
    "WATCHED_COLUMNS",
    "Classification",
    "ProbeFinding",
    "ProbeItem",
    "ProbeObservation",
    "ProbeUpload",
    "button_handlers",
    "check",
    "classify",
    "compare",
    "detail_equal",
    "finding_mismatches",
    "journal_built",
    "journal_mode",
    "journal_window",
    "named_upload",
    "normalised_key",
    "order_findings",
    "probe_items",
    "probe_reports",
    "repeated_uploads",
    "run",
    "tenant_code",
]

KIND: Final = "legacy_probe"
COMMITTED: Final = "COMMITTED"
COMMITTED_WITH_FINDINGS: Final = "COMMITTED_WITH_FINDINGS"
REJECTED: Final = "REJECTED"
PROBES_ROOT: Final = GOLDEN_ROOT / "probes"
LEGACY_PROBES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "legacy_probes"
RESET_HANDLER: Final = "db_reset"
DUPLICATE_SLUG: Final = "duplicate-import"  # 05 IPL-01; 04 ux_import_upload__duplicate
EXCEPTIONS_PATH: Final = "/api/v1/exceptions"
PAGE_LIMIT: Final = 500
JOURNAL_REPORT: Final = "legacy_je_summary"
JOURNAL_NOT_BUILT: Final = "legacy_je_summary not built (BUILD_SPEC RPS)"
JOURNAL_PREFIXES: Final = ("je_gross_", "je_delta_")
# DG-PAR-06: provenance keys, never asserted.
PROVENANCE_KEYS: Final = frozenset({"error_code_source", "legacy_oracle"})
PROVENANCE_PREFIX: Final = "legacy_replica_"
IDENTITY_KEYS: Final = frozenset({"contract", "pob"})
# 04 §17 LM-CL rows of the legacy columns the probes watch -> obligation_version column.
WATCHED_COLUMNS: Final[Mapping[str, str]] = {
    "Current Period": "effective_date",  # LM-CL-13
    "Current Remaining Qty": "remaining_quantity",  # LM-CL-48
    "Current Remaining Allocation": "remaining_allocation",  # LM-CL-50
    "Current Pre-ASC606 Revenue (Net Design Only)": "pre_standard_revenue_amount",  # LM-CL-56
    "Current Delivery - Cumulative": "delivered_quantity_cum",  # LM-CL-60
    "Current Rev Rec - Cumulative": "revenue_cum",  # LM-CL-61
    "Current Pre-ASC606 Revenue (Net Design Only) - Cumulative": "pre_standard_revenue_cum",  # 62
    "Current Billing - Cumulative": "billed_cum",  # LM-CL-63
}
# DG-OQ-05: the posted money measures whose exact value is a trace node (DG-PAR-05).
TRACED_MEASURES: Final = frozenset(
    {
        "revenue_cum",
        "remaining_allocation",
        "position_obligation",
        "catch_up_amount",
        "catch_up_cum",
        "netting_reclass_amount",
        "remaining_billing",
    }
)
_ROWS: Final = re.compile(r"\bRows ((?:[0-9]+, )+[0-9]+)\.")  # findings.every_row (OQ-D11)
JOURNAL_NO_WINDOW: Final = "probe.json reports names no window for this key (DG-PAR-06)"
NO_REPEATED_UPLOAD: Final = "no repeated upload of that file in the sequence (DG-PAR-06 rev 1.1)"
# Members of one upload (DG-PAR-06, DG-PAR-10, DG-PAR-11); top-level members read the last upload.
UPLOAD_MEMBERS: Final = frozenset(
    {
        "import_status",
        "error_code",
        "detail",
        "import_status_basis",
        "findings",
        "sha256",
        "versions_before",
        "versions_after",
    }
)
_ORDINALS: Final[Mapping[str, int]] = {"first": 0, "second": 1, "third": 2, "fourth": 3}
_ORDINAL: Final = "first|second|third|fourth"
_UPLOAD_OBJECT: Final = re.compile(rf"^(?P<ordinal>{_ORDINAL})_(?P<label>.+)_upload$")
_SUFFIXED_COUNT: Final = re.compile(
    rf"^(?P<count>versions_before|versions_after)_(?P<ordinal>{_ORDINAL})$"
)
_MONTH_LABEL: Final = re.compile(r"^(?P<year>[0-9]{4})_(?P<month>[0-9]{2})$")
# D-87b: the legacy prose of a probe detail and its aggregated key.
_LEGACY_DETAIL: Final = re.compile(
    r"^(?P<key>.+): delivery (?P<requested>[0-9.]+) exceeds remaining quantity "
    r"(?P<remaining>[0-9.]+)$"
)
_LEGACY_KEY: Final = re.compile(r"^(?P<contract>.+?) (?P<pob>POB #[0-9]+) (?P<product>.+)$")


# --- observations -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProbeFinding:
    """One 04 §15.4 finding of an upload: a row finding, or a file-stage finding without a row."""

    code: str
    severity: str  # finding severity (E-43 inverse): ERROR, WARNING, INFO
    message: str
    sheet_name: str | None = None
    row_number: int | None = None  # Excel row number, header row = 1
    business_key: str | None = None

    @property
    def file_stage(self) -> bool:
        return self.row_number is None

    @property
    def worksheet_rows(self) -> tuple[int, ...]:
        """Every contributing Excel row, ascending: the rows the message names, else its row."""
        named = _ROWS.search(self.message)
        if named is not None:
            return tuple(sorted({int(number) for number in named.group(1).split(", ")}))
        return () if self.row_number is None else (self.row_number,)

    @property
    def pob(self) -> str | None:
        return None if self.business_key is None else normalised_key(self.business_key)


@dataclass(frozen=True, slots=True)
class ProbeUpload:
    """One replayed sequence item (module docstring)."""

    file_name: str
    sha256: str
    e40_status: str | None  # null when no import_upload row exists
    findings: tuple[ProbeFinding, ...] = ()
    problem: Mapping[str, Any] | None = None  # the problem body of a refused upload
    versions_before: int = 0
    versions_after: int = 0


@dataclass(frozen=True, slots=True)
class ProbeObservation:
    """The uploads of a probe in sequence order, the watched legacy columns by (contract, POB) and
    the ``legacy_je_summary`` view of each expected journal key."""

    uploads: tuple[ProbeUpload, ...]
    watched: Mapping[tuple[str, str], Mapping[str, Fraction | str | None]]
    journals: Mapping[str, values.JournalView] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Classification:
    """The DG-PAR-10 row an upload matches; ``import_status`` is null when no row matches, and
    ``condition`` then says what was observed."""

    import_status: str | None
    error_code: str | None = None
    detail: str | None = None
    condition: str | None = None


def normalised_key(business_key: str) -> str:
    """DG-PAR-11 ``pob``: each ``" / "`` separator replaced by one space."""
    return business_key.replace(" / ", " ")


def order_findings(findings: Sequence[ProbeFinding]) -> tuple[ProbeFinding, ...]:
    """DG-PAR-11 order: file-stage findings first, then row findings by sheet, Excel row and
    code."""
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                0 if item.file_stage else 1,
                item.sheet_name or "",
                item.row_number or 0,
                item.code,
            ),
        )
    )


def problem_slug(problem: Mapping[str, Any]) -> str:
    return str(problem.get("type") or "").removeprefix(TYPE_BASE)


def classify(upload: ProbeUpload) -> Classification:
    """The table "Probe import-status mapping" (DG-PAR-10)."""
    if upload.problem is not None:
        slug = problem_slug(upload.problem)
        errors = upload.problem.get("errors") or []
        first: Mapping[str, Any] = errors[0] if errors and isinstance(errors[0], Mapping) else {}
        if upload.e40_status is None and slug == DUPLICATE_SLUG and upload.problem["status"] == 409:
            return Classification(REJECTED, first.get("rule_id"), first.get("message"))
        return Classification(
            None,
            condition=f"upload answered {upload.problem.get('status')} {slug} with E-40 "
            f"{upload.e40_status}",
        )
    ordered = order_findings(upload.findings)
    severities = {item.severity for item in ordered}
    if upload.e40_status == "COMMITTED":
        if not ordered:
            return Classification(COMMITTED)
        if "WARNING" in severities and "ERROR" not in severities:
            return Classification(COMMITTED_WITH_FINDINGS)
    elif upload.e40_status == "INVALID":
        error = next((item for item in ordered if item.severity == "ERROR"), None)
        if error is not None:
            return Classification(REJECTED, error.code, error.message)
    return Classification(
        None,
        condition=f"no DG-PAR-10 row matches E-40 {upload.e40_status} with finding severities "
        f"{sorted(severities)}",
    )


# --- comparison ---------------------------------------------------------------------------------


def journal_built() -> bool:
    """Whether report ``legacy_je_summary`` has a builder (RPT-13; BUILD_SPEC RPS-5)."""
    return JOURNAL_REPORT in BUILDERS


def _mismatch(field: str, expected: Any, actual: Any) -> Mismatch:
    return Mismatch(field=field, expected=expected, actual=actual, legacy=None)


def _strings(value: Any) -> tuple[str, ...] | None:
    """A string, or a list of strings, as a tuple; anything else is None."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return None


def finding_mismatches(
    expected: Sequence[Mapping[str, Any]], actual: Sequence[ProbeFinding], field: str = "findings"
) -> list[Mismatch]:
    """DG-PAR-11: the ordered list over ``code``, ``severity``, ``worksheet_row``,
    ``worksheet_rows`` and ``pob``; each other string member must appear verbatim in the message.
    An empty expected list requires zero findings."""
    ordered = order_findings(actual)
    found: list[Mismatch] = []
    if len(expected) != len(ordered):
        found.append(
            _mismatch(
                f"{field}.count",
                len(expected),
                [f"{item.code} {item.severity} row {item.row_number}" for item in ordered],
            )
        )
    for index, (want, got) in enumerate(zip(expected, ordered, strict=False)):
        prefix = f"{field}[{index}]"
        observed: Mapping[str, Any] = {
            "code": got.code,
            "severity": got.severity,
            "worksheet_row": got.row_number,
            "worksheet_rows": list(got.worksheet_rows),
            "pob": got.pob,
        }
        for key, value in want.items():
            if key in observed:
                if not parity_compare.exact_equal(observed[key], value):
                    found.append(_mismatch(f"{prefix}.{key}", value, observed[key]))
                continue
            strings = _strings(value)
            if strings is None:
                found.append(_mismatch(f"{prefix}.{key}", value, "no DG-PAR-11 rule for this key"))
            elif any(text not in got.message for text in strings):
                found.append(_mismatch(f"{prefix}.{key}", value, got.message))
    return found


def _basis_mismatches(
    basis: Mapping[str, Any], upload: ProbeUpload | None, *, prefix: str = ""
) -> list[Mismatch]:
    """The asserted members of ``import_status_basis`` (DG-PAR-10)."""
    field_name = f"{prefix}import_status_basis"
    found: list[Mismatch] = []
    if "e40_import_status" in basis:
        actual = None if upload is None else upload.e40_status
        if actual != basis["e40_import_status"]:
            found.append(
                _mismatch(f"{field_name}.e40_import_status", basis["e40_import_status"], actual)
            )
    want = basis.get("problem")
    if isinstance(want, Mapping):
        got = None if upload is None else upload.problem
        if got is None:
            found.append(_mismatch(f"{field_name}.problem", want, None))
            return found
        if "slug" in want and problem_slug(got) != want["slug"]:
            found.append(_mismatch(f"{field_name}.problem.slug", want["slug"], problem_slug(got)))
        if "status" in want and got.get("status") != want["status"]:
            found.append(
                _mismatch(f"{field_name}.problem.status", want["status"], got.get("status"))
            )
        if "errors" in want:
            wanted = [item.get("rule_id") for item in want["errors"]]
            actual_ids = [item.get("rule_id") for item in got.get("errors") or []]
            if wanted != actual_ids:
                found.append(_mismatch(f"{field_name}.problem.errors", wanted, actual_ids))
    return found


def _watched_mismatches(
    expected: Sequence[Mapping[str, Any]],
    observed: Mapping[tuple[str, str], Mapping[str, Fraction | str | None]],
) -> list[Mismatch]:
    found: list[Mismatch] = []
    for index, item in enumerate(expected):
        got = observed.get((str(item["contract"]), str(item["pob"])), {})
        for name, value in item.items():
            if name in IDENTITY_KEYS:
                continue
            field = f"watched_latest[{index}].{name}"
            column = WATCHED_COLUMNS.get(name)
            if column is None:
                found.append(_mismatch(field, value, "no LM-CL reader for this legacy column"))
                continue
            actual = got.get(name)
            if column == "effective_date":
                equal = parity_compare.exact_equal(actual, value)
            else:
                equal = not isinstance(actual, str) and parity_compare.unit_equal(actual, value)
            if not equal:
                found.append(_mismatch(field, value, actual))
    return found


def journal_mode(key: str) -> str:
    """The ``legacy_je_summary`` mode of a journal key: ``je_gross_*`` gross, ``je_delta_*``
    adjustment."""
    return "GROSS" if key.startswith("je_gross_") else "DELTA"


def _month_window(year: int, month: int) -> list[str] | None:
    """``[YYYY-MM-01, YYYY-MM-<last day>]`` of a calendar month; None outside months 1 to 12."""
    if not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, 1).isoformat(), date(year, month, last).isoformat()]


def journal_window(reports: Mapping[str, Any], key: str) -> tuple[str, str] | None:
    """``probe.json`` ``reports[key].window`` (DG-PAR-06).

    [J] L7-1-Q-7 (D-88, DG-PAR-06 as amended): P1 names its report ``je_gross`` while its expected
    key is ``je_gross_2023_01``. A key ``je_<gross|delta>_<YYYY>_<MM>`` without its own report takes
    ``reports['je_<gross|delta>'].window``, but only when that window equals ``[YYYY-MM-01, the last
    day of that month]``; in any other case there is no window and the key fails with
    ``JOURNAL_NO_WINDOW``.
    """
    found = reports.get(key)
    if not isinstance(found, Mapping):
        prefix = next((item for item in JOURNAL_PREFIXES if key.startswith(item)), None)
        label = None if prefix is None else _MONTH_LABEL.match(key.removeprefix(prefix))
        view = None if prefix is None else reports.get(prefix.rstrip("_"))
        view_window = view.get("window") if isinstance(view, Mapping) else None
        if (
            label is None
            or not isinstance(view_window, list)
            or view_window != _month_window(int(label["year"]), int(label["month"]))
        ):
            return None
        found = view
    window = found.get("window")
    if isinstance(window, list) and len(window) == 2:
        return str(window[0]), str(window[1])
    return None


def _journal_mismatches(
    key: str, value: Any, observation: ProbeObservation, built: bool
) -> list[Mismatch]:
    """A journal expectation against its ``legacy_je_summary`` view (DG-PAR-06; GPB-1)."""
    if not built:
        return [_mismatch(key, "legacy_je_summary totals", JOURNAL_NOT_BUILT)]
    view = observation.journals.get(key)
    if view is None:
        return [_mismatch(key, "legacy_je_summary totals", JOURNAL_NO_WINDOW)]
    if not isinstance(value, Mapping):
        return [_mismatch(key, value, "not a journal view")]
    return values.journal_mismatches(value, view, prefix=key)


def _whole_token(token: str, text: str) -> bool:
    """``token`` in ``text``, not inside a longer word or number (``POB #1`` is not ``POB #10``)."""
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w|\.[0-9])", text) is not None


def detail_equal(expected: object, actual: str | None) -> bool:
    """D-87b (L7-1-Q-1), for ``legacy_probe`` only: the expected detail ``<contract> <pob>
    <product>: delivery <n> exceeds remaining quantity <m>`` passes when the stored message names
    the contract, obligation and product as whole tokens and "requested <n>" and "remaining <m>".
    Any other expected shape fails; an expected null requires a null actual."""
    if expected is None or actual is None:
        return expected is None and actual is None
    parsed = _LEGACY_DETAIL.match(str(expected))
    key = None if parsed is None else _LEGACY_KEY.match(parsed["key"])
    if parsed is None or key is None:
        return False
    tokens = (
        key["contract"],
        key["pob"],
        key["product"],
        f"requested {parsed['requested']}",
        f"remaining {parsed['remaining']}",
    )
    return all(_whole_token(token, actual) for token in tokens)


def repeated_uploads(uploads: Sequence[ProbeUpload]) -> tuple[tuple[ProbeUpload, ...], ...]:
    """The uploads of each file uploaded more than once, files in first-upload order (DG-PAR-06
    rev 1.1)."""
    by_file: dict[str, list[ProbeUpload]] = {}
    for upload in uploads:
        by_file.setdefault(upload.file_name, []).append(upload)
    return tuple(tuple(items) for items in by_file.values() if len(items) > 1)


def named_upload(
    observation: ProbeObservation, ordinal: str, label: str | None
) -> ProbeUpload | None:
    """The upload an object or a count suffix names: the ``ordinal`` upload of the repeated file
    whose name holds ``label`` with ``_`` read as ``.`` (``2_28`` → ``2.28``), or with no label of
    the probe's one repeated file; None when that file is not exactly one."""
    groups = repeated_uploads(observation.uploads)
    if label is not None:
        wanted = label.replace("_", ".")
        groups = tuple(group for group in groups if wanted in group[0].file_name)
    index = _ORDINALS[ordinal]
    if len(groups) != 1 or index >= len(groups[0]):
        return None
    return groups[0][index]


def _upload_mismatches(
    expected: Mapping[str, Any], upload: ProbeUpload | None, *, prefix: str = ""
) -> list[Mismatch]:
    """The members of one upload (DG-PAR-06, DG-PAR-10, DG-PAR-11; D-87b for ``detail``)."""
    classified = (
        Classification(None, condition="the probe uploaded nothing")
        if upload is None
        else classify(upload)
    )
    found: list[Mismatch] = []
    for key, value in expected.items():
        if key in PROVENANCE_KEYS or key.startswith(PROVENANCE_PREFIX):
            continue
        name = f"{prefix}{key}"
        match key:
            case "import_status":
                if classified.import_status != value:
                    actual = classified.import_status or classified.condition
                    found.append(_mismatch(name, value, actual))
            case "error_code":
                if not parity_compare.exact_equal(classified.error_code, value):
                    found.append(_mismatch(name, value, classified.error_code))
            case "detail":
                if not detail_equal(value, classified.detail):
                    found.append(_mismatch(name, value, classified.detail))
            case "import_status_basis":
                found.extend(_basis_mismatches(value, upload, prefix=prefix))
            case "findings":
                observed = () if upload is None else upload.findings
                found.extend(finding_mismatches(value, observed, name))
            case "sha256":
                digest = None if upload is None else upload.sha256
                if not parity_compare.exact_equal(digest, value):
                    found.append(_mismatch(name, value, digest))
            case "versions_before" | "versions_after":
                count = None if upload is None else getattr(upload, key)
                if not parity_compare.exact_equal(count, value):
                    found.append(_mismatch(name, value, count))
            case _:
                found.append(_mismatch(name, value, "no DG-PAR-06 rule for this upload member"))
    return found


def compare(
    expected: Mapping[str, Any],
    observation: ProbeObservation,
    *,
    report_built: bool | None = None,
) -> list[Mismatch]:
    """Every expected member against the observation (module docstring)."""
    built = journal_built() if report_built is None else report_built
    last = observation.uploads[-1] if observation.uploads else None
    own = {key: value for key, value in expected.items() if key in UPLOAD_MEMBERS}
    found = _upload_mismatches(own, last)
    for key, value in expected.items():
        if key in own or key in PROVENANCE_KEYS or key.startswith(PROVENANCE_PREFIX):
            continue
        upload_object = _UPLOAD_OBJECT.match(key)
        suffixed = _SUFFIXED_COUNT.match(key)
        if key == "watched_latest":
            found.extend(_watched_mismatches(value, observation.watched))
        elif key.startswith(JOURNAL_PREFIXES):
            found.extend(_journal_mismatches(key, value, observation, built))
        elif upload_object is not None:
            upload = named_upload(observation, upload_object["ordinal"], upload_object["label"])
            if upload is None or not isinstance(value, Mapping):
                found.append(_mismatch(key, value, NO_REPEATED_UPLOAD))
            else:
                found.extend(_upload_mismatches(value, upload, prefix=f"{key}."))
        elif suffixed is not None:
            upload = named_upload(observation, suffixed["ordinal"], None)
            count = None if upload is None else getattr(upload, suffixed["count"])
            if not parity_compare.exact_equal(count, value):
                found.append(_mismatch(key, value, NO_REPEATED_UPLOAD if upload is None else count))
        else:
            found.append(_mismatch(key, value, "no DG-PAR-06 rule for this key"))
    return found


# --- replay -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProbeItem:
    """One upload of ``probe.json`` ``sequence``."""

    index: int
    button_label: str
    template_code: str
    mode: str | None
    date_input: date | None
    path: Path

    @property
    def parameters(self) -> dict[str, Any] | None:
        found: dict[str, Any] = {}
        if self.date_input is not None:
            found["effective_date"] = self.date_input.isoformat()
        if self.mode is not None:
            found["mode"] = self.mode
        return found or None


@cache
def button_handlers() -> Mapping[str, str]:
    """Button label -> step handler, as the golden ``step.json`` files pair them (DG-PAR-04)."""
    found: dict[str, str] = {}
    for path in sorted(GOLDEN_ROOT.glob("*/step.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        label, handler = spec.get("button_label"), spec.get("handler")
        if not isinstance(label, str) or not isinstance(handler, str):
            continue
        if found.setdefault(label, handler) != handler:
            raise ValueError(f"button label {label!r} names two handlers")
    return found


def _fixture(name: str) -> Path:
    """The fixture of a probe file by basename: ``legacy_probes/``, else ``legacy_uat/``."""
    candidates = [LEGACY_PROBES / name] if (LEGACY_PROBES / name).is_file() else []
    candidates += [
        directory / name
        for directory in sorted(LEGACY_UAT.iterdir())
        if directory.is_dir() and (directory / name).is_file()
    ]
    digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in candidates}
    if not candidates or len(digests) != 1:
        raise FileNotFoundError(f"probe file {name!r}: {len(candidates)} fixtures, not one")
    return candidates[0]


def _probe_document(test_id: str) -> Mapping[str, Any]:
    loaded = json.loads(
        (PROBES_ROOT / test_id.removeprefix("probe-") / "probe.json").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, Mapping):
        raise ValueError(f"{test_id}: probe.json holds no object")
    return loaded


def probe_reports(test_id: str) -> Mapping[str, Any]:
    """``probe.json`` ``reports``: the legacy journal reports and their windows."""
    reports = _probe_document(test_id).get("reports")
    return reports if isinstance(reports, Mapping) else {}


def probe_items(test_id: str) -> tuple[ProbeItem, ...]:
    """The uploads of a probe's ``sequence``, reset items skipped (DG-PAR-06)."""
    probe = _probe_document(test_id)
    handlers = button_handlers()
    found: list[ProbeItem] = []
    for item in probe["sequence"]:
        label = str(item["button_label"])
        handler = handlers.get(label)
        if handler is None:
            raise ValueError(f"{test_id}: no golden step pairs button label {label!r}")
        if handler == RESET_HANDLER:
            continue
        template_code, mode = HANDLERS[handler]
        raw_date = item.get("date_input")
        found.append(
            ProbeItem(
                index=int(item["i"]),
                button_label=label,
                template_code=template_code,
                mode=mode,
                date_input=None if raw_date is None else date.fromisoformat(str(raw_date)),
                path=_fixture(str(item["file"])),
            )
        )
    return tuple(found)


def tenant_code(test_id: str) -> str:
    """The probe's own tenant: ``legacy-probe-p3`` for ``probe-P3-over-delivery-validation``."""
    return f"legacy-probe-{test_id.removeprefix('probe-').split('-', 1)[0].lower()}"


def _context(world: scenario.ParityScenario) -> DbContext:
    return DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")


def _count(world: scenario.ParityScenario, statement: Any) -> int:
    with tenant_session(_context(world), read_only=True) as session:
        return int(session.execute(statement).scalar_one())


def _versions(world: scenario.ParityScenario) -> int:
    """DG-PAR-06: the ``obligation_version`` rows in book ASC606."""
    return _count(
        world,
        select(func.count())
        .select_from(obligation_version)
        .where(obligation_version.c.book_code == BookCode.ASC606.value),
    )


def _pages(
    world: scenario.ParityScenario, path: str, params: Mapping[str, Any] | None = None
) -> Iterator[Mapping[str, Any]]:
    cursor: str | None = None
    while True:
        query: dict[str, Any] = {**(params or {}), "limit": PAGE_LIMIT}
        if cursor is not None:
            query["cursor"] = cursor
        response = get(world.app, path, world.world.maya, query)
        assert response.status_code == 200, response.text
        body = response.json()
        yield from body["items"]
        cursor = body.get("next_cursor")
        if not cursor:
            return


def _findings(world: scenario.ParityScenario, import_id: str) -> tuple[ProbeFinding, ...]:
    """The upload's catalogue findings: row messages (API-R-43 rows) and file-stage items
    (API-R-44 ``import_upload_id``, no row)."""
    found: list[ProbeFinding] = []
    for row in _pages(world, f"{IMPORTS_PATH}/{import_id}/rows"):
        for message in row["messages"]:
            found.append(
                ProbeFinding(
                    code=str(message["rule_id"]),
                    severity=str(message["severity"]),
                    message=str(message["message"]),
                    sheet_name=str(row["sheet_name"]),
                    row_number=int(row["row_number"]),
                    business_key=row["business_key"],
                )
            )
    for item in _pages(world, EXCEPTIONS_PATH, {"import_upload_id": import_id}):
        if item["import_row_id"] is None:
            found.append(
                ProbeFinding(
                    code=str(item["code"]),
                    severity=FINDING_SEVERITY[str(item["severity"])],
                    message=str(item["message"]),
                    business_key=item["business_key"],
                )
            )
    return order_findings(found)


def _replay(world: scenario.ParityScenario, item: ProbeItem) -> ProbeUpload:
    """One sequence item through the legacy v1 import pipeline (module docstring)."""
    legacy = world.advance()
    imports = legacy.imports
    content = item.path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    before = _versions(world)
    uploads_before = _count(world, select(func.count()).select_from(import_upload))
    file_id = upload_import_source(imports, item.path.name, content)
    created = create_import(imports, file_id, item.template_code, item.parameters)
    if created.status_code != 202:
        rows = _count(world, select(func.count()).select_from(import_upload))
        return ProbeUpload(
            file_name=item.path.name,
            sha256=digest,
            e40_status=None if rows == uploads_before else "UNKNOWN",
            problem=dict(created.json()),
            versions_before=before,
            versions_after=_versions(world),
        )
    import_id = str(created.headers[IMPORT_ID_HEADER])
    run_import_job(imports, UUID(str(created.json()["id"])))
    if shown(imports, import_id)["status"] == "VALIDATED":
        run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_DIFF"))
        if shown(imports, import_id)["status"] == "DIFF_READY":
            submitted = submit(imports, import_id)
            assert submitted.status_code == 200, submitted.text
            decided = approve(
                legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya
            )
            assert decided.status_code == 200, decided.text
            run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
            if shown(imports, import_id)["status"] == "COMMITTED":
                # The close run's JET-06 step, which the rc platform does not post (L7-1-Q-6).
                netting.post_netting_reclass(legacy.place(), scenario.OPEN_KEYS_SET)
    return ProbeUpload(
        file_name=item.path.name,
        sha256=digest,
        e40_status=str(shown(imports, import_id)["status"]),
        findings=_findings(world, import_id),
        versions_before=before,
        versions_after=_versions(world),
    )


def _latest(
    session: Session, contract_name: str, pob: str
) -> tuple[Mapping[str, Any], values.NodeLookup]:
    """The latest ASC606 obligation version of ``contract_name``, ``pob``: its row in the highest
    ``version_no`` of the contract's group, with the lookup of its calc_trace nodes."""
    found = (
        session.execute(
            select(contract.c.id, contract.c.combination_group_id).where(
                contract.c.external_id == contract_name
            )
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise values.ValueSourceError(f"{contract_name} does not exist")
    version = (
        session.execute(
            select(contract_version.c.id, contract_version.c.calc_trace_id)
            .where(
                contract_version.c.combination_group_id == found["combination_group_id"],
                contract_version.c.book_code == BookCode.ASC606.value,
            )
            .order_by(contract_version.c.version_no.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if version is None:
        raise values.ValueSourceError(f"no ASC606 version of {contract_name}")
    row = (
        session.execute(
            select(obligation_version).where(
                obligation_version.c.contract_version_id == version["id"],
                obligation_version.c.contract_id == found["id"],
                obligation_version.c.obligation_key == pob,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise values.ValueSourceError(f"the latest version of {contract_name} holds no {pob}")
    trace_row = (
        session.execute(select(calc_trace).where(calc_trace.c.id == version["calc_trace_id"]))
        .mappings()
        .one()
    )
    nodes = {node.id: node for node in store.trace_from_row(trace_row).nodes}
    return dict(row), nodes.get


def _watched(
    world: scenario.ParityScenario, items: Any
) -> dict[tuple[str, str], dict[str, Fraction | str | None]]:
    """The watched legacy columns of each expected ``watched_latest`` item that has a reader."""
    found: dict[tuple[str, str], dict[str, Fraction | str | None]] = {}
    if not isinstance(items, list):
        return found
    with tenant_session(_context(world), read_only=True) as session:
        for item in items:
            key = (str(item["contract"]), str(item["pob"]))
            row, nodes = _latest(session, *key)
            read: dict[str, Fraction | str | None] = {}
            for name in item:
                column = WATCHED_COLUMNS.get(name)
                if column is None:
                    continue
                if column == "effective_date":
                    stored = row[column]
                    read[name] = None if stored is None else stored.isoformat()
                elif column in TRACED_MEASURES or values.column_kind(column) == "exact":
                    read[name] = values.exact(row, column, nodes)
                else:
                    stored = row[column]
                    read[name] = None if stored is None else Fraction(Decimal(str(stored)))
            found[key] = read
    return found


def run(case: GoldenCase, settings: Settings, keyring: KeyRing) -> ProbeObservation:
    """Replay the probe of ``case`` in its own fresh tenant (module docstring)."""
    items = probe_items(case.id)
    world = scenario.build(settings, keyring, tenant_code=tenant_code(case.id))
    uploads = tuple(_replay(world, item) for item in items)
    reports = probe_reports(case.id)
    journals: dict[str, values.JournalView] = {}
    for key in case.expected:
        window = journal_window(reports, key) if key.startswith(JOURNAL_PREFIXES) else None
        if window is not None:
            journals[key] = values.run_journal(world.world, window, journal_mode(key))
    return ProbeObservation(
        uploads=uploads,
        watched=_watched(world, case.expected.get("watched_latest")),
        journals=journals,
    )


def check(case: GoldenCase, settings: Settings, keyring: KeyRing) -> list[Mismatch]:
    """DG-PAR-06 for one ``legacy_probe`` case: replay, then compare."""
    return compare(case.expected, run(case, settings, keyring))
