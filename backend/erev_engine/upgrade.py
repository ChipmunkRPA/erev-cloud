"""Engine release orchestration helpers: evidence codec, input transforms, comparison views.

05 RCP-28a and D-96 (1)-(4). Orchestration only: no stage imports this module and it runs no
stage (DG-ENG-07 lists it as a public module for the platform side). Standard library plus the
``erev_engine`` public modules ``bundle`` and ``canonical`` (DG-ARC-02).

Four concerns, each a pure function:

1. **Evidence codec** (T-CON-25). ``encode_input`` writes the canonical JSON *evidence encoding*
   of the full ``InputBundle`` including ``known_at``. Canonical JSON alone flattens ``Decimal``,
   ``date`` and ``datetime`` scalars to strings, and the engine converts only ``Decimal`` payload
   members to fractions (stage 01 ``convert_payload``), so a flat encoding could not be replayed
   faithfully. The evidence encoding therefore tags every such scalar (``{"$decimal": "…"}``,
   ``{"$date": "…"}``, ``{"$datetime": "…"}``) and ``decode_input`` rebuilds the frozen
   dataclasses type-directed, so ``decode_input(encode_input(b)) == b``, ``.sha256()`` agrees
   and a re-execution reproduces the stored output hash. The logical CV-25 hash is always taken
   from the decoded bundle, never from the bytes; the raw digest is ``hashlib`` over the bytes.
   Output evidence is plain ``canonical_bytes(output)``: outputs are compared at the JSON level
   and never rebuilt, and that digest equals the CV-26 ``output_sha256`` by construction.
2. **Input transforms** (RCP-28a "Candidate input"). ``INPUT_TRANSFORMS`` maps
   ``(from_version, to_version)`` to a function over the decoded bundle mapping. A chain is
   composed along registered links; a missing link is ``TransformUnavailable``
   (``NO_INPUT_TRANSFORM``). Source bytes and hashes are never replaced.
3. **Views**. ``cv25_view`` mirrors ``InputBundle.sha256`` (asserted by test); ``l1_view`` blanks
   exactly ``engine_version``, ``input_sha256`` and ``books[*].trace.engine_version`` of an output
   mapping; ``attribution_view`` keeps ``known_at`` and every engine-read member and blanks only
   ``engine_version`` and ``format_version`` (D-96 (F)).
4. **L2 representation diff**. ``representation_diff`` classifies every changed path as ``M``
   (monetary sections), ``P`` (posting intents), ``R`` (exactly the three stamp paths) or ``T``
   (everything else), keeping signed before/after values per row.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
import typing
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Final

from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex

__all__ = [
    "EVIDENCE_FORMAT",
    "INPUT_TRANSFORMS",
    "AttributionComparison",
    "DifferenceRow",
    "DifferenceSummary",
    "TransformUnavailable",
    "attribution_input_sha256",
    "attribution_comparison",
    "candidate_input",
    "cv25_view",
    "decode_input",
    "encode_input",
    "encode_output",
    "input_mapping",
    "l1_sha256",
    "l1_view",
    "normalised_input_sha256",
    "output_mapping",
    "raw_digest",
    "representation_diff",
    "transform_chain",
]

EVIDENCE_FORMAT: Final = 1
_TAG_DECIMAL: Final = "$decimal"
_TAG_DATE: Final = "$date"
_TAG_DATETIME: Final = "$datetime"
_TAGS: Final = frozenset({_TAG_DECIMAL, _TAG_DATE, _TAG_DATETIME})

# RCP-28a L2: the only paths classified R (representation); everything not M or P is T.
R_PATHS: Final = ("engine_version", "input_sha256", "books[*].trace.engine_version")
_MONETARY_SECTIONS: Final = frozenset(
    {
        "contract_version",
        "obligation_versions",
        "balances",
        "schedules",
        "cost_asset_versions",
        "loss_provision_versions",
        "fx_layer_movements",
    }
)
_LINEAGE_KEY: Final = "trace_nodes"


class TransformUnavailable(LookupError):
    """No registered transform chain links the source version to the candidate version."""


# --- Evidence codec ------------------------------------------------------------------------------


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("the evidence encoding requires a timezone-aware datetime")
    u = value.astimezone(UTC)
    return (
        f"{u.year:04d}-{u.month:02d}-{u.day:02d}T"
        f"{u.hour:02d}:{u.minute:02d}:{u.second:02d}.{u.microsecond:06d}Z"
    )


def _tagged(obj: object) -> object:
    """The evidence view of ``obj``: dataclasses and mappings as dicts, sequences as lists, and
    every ``Decimal``, ``date`` and ``datetime`` scalar wrapped in a one-key tag object."""
    if obj is None or isinstance(obj, bool | int | str):
        return obj
    if isinstance(obj, Enum):
        return _tagged(obj.value)
    if isinstance(obj, float):
        raise TypeError("the evidence encoding rejects float (DG-ENG-03)")
    if isinstance(obj, Fraction):
        raise TypeError("an input bundle holds Decimal, never Fraction (CV-30)")
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise ValueError("the evidence encoding rejects a non-finite Decimal")
        return {_TAG_DECIMAL: format(obj, "f")}
    if isinstance(obj, datetime):
        return {_TAG_DATETIME: _utc_text(obj)}
    if isinstance(obj, date):
        return {_TAG_DATE: obj.isoformat()}
    if isinstance(obj, Mapping):
        out: dict[str, object] = {}
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError("evidence mapping keys are strings")
            if key in _TAGS:
                raise ValueError(f"a bundle mapping key may not be the tag {key!r}")
            out[key] = _tagged(value)
        return out
    if isinstance(obj, list | tuple):
        return [_tagged(item) for item in obj]
    if isinstance(obj, set | frozenset):
        return sorted((_tagged(item) for item in obj), key=canonical_bytes)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _tagged(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    raise TypeError(f"the evidence encoding does not support {type(obj).__qualname__}")


def _untagged(obj: object) -> object:
    """Inverse of ``_tagged`` for scalars: tag objects become ``Decimal``/``date``/``datetime``;
    containers stay plain dicts and lists for the type-directed rebuild."""
    if isinstance(obj, dict):
        if len(obj) == 1:
            (key, value), *_ = obj.items()
            if key in _TAGS:
                if not isinstance(value, str):
                    raise ValueError(f"tag {key} carries a non-string value")
                if key == _TAG_DECIMAL:
                    return Decimal(value)
                if key == _TAG_DATE:
                    return date.fromisoformat(value)
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        return {str(key): _untagged(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_untagged(item) for item in obj]
    return obj


def _type_hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls, include_extras=False)


def _is_dataclass_type(tp: object) -> bool:
    return isinstance(tp, type) and dataclasses.is_dataclass(tp)


def _build(tp: Any, value: object, path: str) -> object:
    """``value`` (untagged JSON structure) as an instance of the annotation ``tp``."""
    if tp is Any or tp is object:
        return _freeze(value)
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is types.UnionType or origin is typing.Union:
        members = [arg for arg in args if arg is not type(None)]
        if value is None:
            if len(members) == len(args):
                raise ValueError(f"{path}: null is not allowed")
            return None
        return _build(_pick(members, value, path), value, path)
    if value is None:
        raise ValueError(f"{path}: null is not allowed")
    if _is_dataclass_type(tp):
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object for {tp.__qualname__}")
        return _build_dataclass(tp, value, path)
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected an array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_build(args[0], item, f"{path}[{i}]") for i, item in enumerate(value))
        if len(args) != len(value):
            raise ValueError(f"{path}: expected {len(args)} members, got {len(value)}")
        return tuple(
            _build(arg, item, f"{path}[{i}]")
            for i, (arg, item) in enumerate(zip(args, value, strict=True))
        )
    if origin in (Mapping, dict, typing.Mapping):
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        value_type = args[1] if len(args) == 2 else Any
        return {key: _build(value_type, item, f"{path}[{key!r}]") for key, item in value.items()}
    if origin in (frozenset, set):
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected an array")
        return frozenset(_build(args[0], item, path) for item in value)
    if tp in (str, int, bool, Decimal, date, datetime):
        if tp is int and isinstance(value, bool):
            raise ValueError(f"{path}: expected int, got bool")
        if not isinstance(value, tp):
            raise ValueError(f"{path}: expected {tp.__qualname__}, got {type(value).__qualname__}")
        return value
    raise TypeError(f"{path}: the evidence decoder does not support the annotation {tp!r}")


def _pick(members: Sequence[Any], value: object, path: str) -> Any:
    """The union member whose shape matches ``value`` (str | tuple[str, ...] | Mapping[str, str]
    and the ``X | None`` forms are the only unions on the input side)."""
    for member in members:
        origin = typing.get_origin(member)
        if isinstance(value, list) and origin in (tuple, frozenset, set):
            return member
        if isinstance(value, dict) and (
            origin in (Mapping, dict, typing.Mapping) or _is_dataclass_type(member)
        ):
            return member
        if not isinstance(value, list | dict) and origin is None and not _is_dataclass_type(member):
            if member is Any or member is object or isinstance(value, member):
                return member
    raise ValueError(f"{path}: no union member of {members!r} matches {type(value).__qualname__}")


def _build_dataclass(cls: type, value: dict[str, object], path: str) -> object:
    hints = _type_hints(cls)
    known = {f.name: f for f in dataclasses.fields(cls)}
    extra = sorted(set(value) - set(known))
    if extra:
        raise ValueError(f"{path}: unknown members {extra} for {cls.__qualname__}")
    kwargs: dict[str, object] = {}
    for name, field in known.items():
        if name in value:
            kwargs[name] = _build(hints[name], value[name], f"{path}.{name}")
        elif field.default is not dataclasses.MISSING:
            kwargs[name] = field.default
        elif field.default_factory is not dataclasses.MISSING:
            kwargs[name] = field.default_factory()
        else:
            raise ValueError(f"{path}: missing member {name!r} of {cls.__qualname__}")
    return cls(**kwargs)


def _freeze(value: object) -> object:
    """Untyped members (``Mapping[str, object]`` payloads and parameters): JSON objects stay dicts
    and JSON arrays stay lists, exactly as bundle assembly hands the stored ``jsonb`` payload to
    the engine (stage 01 ``convert_payload`` turns them into read-only tuples itself)."""
    if isinstance(value, dict):
        return {key: _freeze(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_freeze(item) for item in value]
    return value


def encode_input(bundle: InputBundle) -> bytes:
    """The T-CON-25 input evidence bytes: canonical JSON of ``{"evidence_format", "bundle"}``."""
    return canonical_bytes({"evidence_format": EVIDENCE_FORMAT, "bundle": _tagged(bundle)})


def input_mapping(evidence: bytes) -> dict[str, object]:
    """The untagged, dataclass-shaped mapping of the bundle inside ``evidence`` (the form input
    transforms operate on)."""
    parsed = json.loads(evidence.decode("utf-8"))
    if not isinstance(parsed, dict) or parsed.get("evidence_format") != EVIDENCE_FORMAT:
        raise ValueError("unknown input evidence format")
    body = _untagged(parsed["bundle"])
    if not isinstance(body, dict):
        raise ValueError("the evidence bundle is not an object")
    return body


def bundle_from_mapping(mapping: Mapping[str, object]) -> InputBundle:
    """A frozen ``InputBundle`` from a dataclass-shaped mapping (members absent in an older codec
    take the dataclass default, for example ``EstimateVersionInput.direction``)."""
    built = _build(InputBundle, dict(mapping), "$")
    assert isinstance(built, InputBundle)
    return built


def decode_input(evidence: bytes) -> InputBundle:
    """The bundle whose evidence bytes are ``evidence``; ``decode_input(encode_input(b)) == b``."""
    return bundle_from_mapping(input_mapping(evidence))


def encode_output(output: OutputBundle) -> bytes:
    """The T-CON-25 output evidence bytes: ``canonical_bytes(output)``, whose SHA-256 is the CV-26
    ``output_sha256`` itself."""
    return canonical_bytes(output)


def output_mapping(output: OutputBundle | bytes) -> dict[str, Any]:
    """The JSON-level mapping of an output (dataclass or evidence bytes); re-encoding it with
    ``canonical_bytes`` reproduces the same bytes, so views hash stably."""
    raw = output if isinstance(output, bytes) else encode_output(output)
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("an output bundle is an object")
    return parsed


def raw_digest(evidence: bytes) -> str:
    """The trusted raw-file digest of evidence bytes (R1): plain SHA-256, distinct from CV-25."""
    return hashlib.sha256(evidence).hexdigest()


# --- Input transforms ----------------------------------------------------------------------------

InputTransform = Callable[[Mapping[str, object]], Mapping[str, object]]


def _identity(mapping: Mapping[str, object]) -> Mapping[str, object]:
    return mapping


# Registered links between engine versions (RCP-28a). 0.1.0 → 0.2.0 (D-91 C606-01) changed
# results without changing the input schema; 0.2.0 → 0.3.0 (D-93 (5)) added the estimate member
# ``direction``, whose absence in an older bundle is the dataclass default that
# ``resolved_direction`` derives, so both links are the identity over the decoded mapping.
INPUT_TRANSFORMS: Final[Mapping[tuple[str, str], InputTransform]] = MappingProxyType(
    {
        ("0.1.0", "0.2.0"): _identity,
        ("0.2.0", "0.3.0"): _identity,
    }
)


def transform_chain(
    from_version: str,
    to_version: str,
    registry: Mapping[tuple[str, str], InputTransform] = INPUT_TRANSFORMS,
) -> tuple[tuple[str, str], ...]:
    """The shortest registered chain of links from ``from_version`` to ``to_version``; ``()`` when
    they are equal; ``TransformUnavailable`` when no chain exists."""
    if from_version == to_version:
        return ()
    previous: dict[str, tuple[str, str] | None] = {from_version: None}
    queue: deque[str] = deque([from_version])
    while queue:
        version = queue.popleft()
        for link in sorted(registry):
            source, target = link
            if source != version or target in previous:
                continue
            previous[target] = link
            if target == to_version:
                chain: list[tuple[str, str]] = []
                node = target
                while True:
                    step = previous[node]
                    if step is None:
                        break
                    chain.append(step)
                    node = step[0]
                return tuple(reversed(chain))
            queue.append(target)
    raise TransformUnavailable(f"no input transform from {from_version} to {to_version}")


def candidate_input(
    source: Mapping[str, object] | InputBundle,
    to_version: str,
    registry: Mapping[tuple[str, str], InputTransform] = INPUT_TRANSFORMS,
) -> tuple[InputBundle, str]:
    """A separate candidate bundle stamped ``to_version`` and the transform id
    ``"<from>-><to>:<link>+<link>"`` (``"identity"`` when the versions are equal). The source
    mapping is not modified."""
    mapping: dict[str, object] = (
        dict(source) if isinstance(source, Mapping) else dict(_mapping_of(source))
    )
    from_version = str(mapping["engine_version"])
    chain = transform_chain(from_version, to_version, registry)
    current: Mapping[str, object] = mapping
    for link in chain:
        current = registry[link](current)
    stamped = dict(current)
    stamped["engine_version"] = to_version
    label = "identity" if not chain else "+".join(f"{a}->{b}" for a, b in chain)
    return bundle_from_mapping(stamped), f"{from_version}->{to_version}:{label}"


def _mapping_of(bundle: InputBundle) -> dict[str, object]:
    """The dataclass-shaped mapping of a bundle (typed scalars kept), via the evidence codec so
    that transforms see exactly what a decoded evidence file would give."""
    return input_mapping(encode_input(bundle))


# --- Views ---------------------------------------------------------------------------------------


def cv25_view(bundle: InputBundle, *, engine_version: str | None = None) -> dict[str, object]:
    """The CV-25 hash view (mirrors ``InputBundle.sha256``: ``known_at`` removed, estimate versions
    through ``hash_view``), optionally with ``engine_version`` replaced (RCP-28a
    ``normalised_input_match``)."""
    view: dict[str, object] = {
        item.name: getattr(bundle, item.name) for item in dataclasses.fields(bundle)
    }
    del view["known_at"]
    view["estimate_versions"] = tuple(item.hash_view() for item in bundle.estimate_versions)
    if engine_version is not None:
        view["engine_version"] = engine_version
    return view


def normalised_input_sha256(bundle: InputBundle) -> str:
    """SHA-256 of the CV-25 view with ``engine_version := ""`` (RCP-28a, recorded separately from
    L1 as ``normalised_input_match``)."""
    return sha256_hex(cv25_view(bundle, engine_version=""))


def attribution_view(bundle: InputBundle) -> dict[str, object]:
    """D-96 (F): the full bundle — ``known_at`` retained, every engine-read member kept — with only
    ``engine_version`` and ``format_version`` normalised. Distinct from CV-25."""
    view: dict[str, object] = {
        item.name: getattr(bundle, item.name) for item in dataclasses.fields(bundle)
    }
    view["engine_version"] = ""
    view["format_version"] = 0
    return view


def attribution_input_sha256(bundle: InputBundle) -> str:
    return sha256_hex(attribution_view(bundle))


@dataclass(frozen=True, slots=True)
class AttributionComparison:
    """T-SL-11 ``input_comparison``; ``equal`` is None when no comparison was possible."""

    previous_attribution_input_sha256: str | None
    current_attribution_input_sha256: str
    transform_id: str | None
    equal: bool | None

    def as_json(self) -> dict[str, object]:
        return {
            "previous_attribution_input_sha256": self.previous_attribution_input_sha256,
            "current_attribution_input_sha256": self.current_attribution_input_sha256,
            "transform_id": self.transform_id,
        }


def attribution_comparison(
    previous: InputBundle | None,
    current: InputBundle,
    registry: Mapping[tuple[str, str], InputTransform] = INPUT_TRANSFORMS,
) -> AttributionComparison:
    """Compare the previous head's evidence bundle with the current bundle after bringing the
    older side to the current version through the registered transforms. No previous evidence or
    no transform chain → ``equal = None`` (label ``UPGRADE_CONTEXT``)."""
    current_sha = attribution_input_sha256(current)
    if previous is None:
        return AttributionComparison(None, current_sha, None, None)
    try:
        aligned, transform_id = candidate_input(previous, current.engine_version, registry)
    except TransformUnavailable:
        return AttributionComparison(None, current_sha, None, None)
    previous_sha = attribution_input_sha256(aligned)
    return AttributionComparison(
        previous_sha, current_sha, transform_id, previous_sha == current_sha
    )


def l1_view(output: Mapping[str, Any]) -> dict[str, Any]:
    """RCP-28a L1: the output mapping with exactly ``engine_version``, ``input_sha256`` and every
    ``books[i].trace.engine_version`` blanked; nothing else is touched."""
    view = json.loads(json.dumps(output))  # deep copy of a JSON-level mapping
    view["engine_version"] = ""
    view["input_sha256"] = ""
    for book in view.get("books", ()):
        trace = book.get("trace")
        if isinstance(trace, dict) and "engine_version" in trace:
            trace["engine_version"] = ""
    assert isinstance(view, dict)
    return view


def l1_sha256(output: Mapping[str, Any]) -> str:
    return sha256_hex(l1_view(output))


# --- L2 representation diff ----------------------------------------------------------------------

Category = typing.Literal["M", "P", "T", "R"]


@dataclass(frozen=True, slots=True)
class DifferenceRow:
    path: str
    category: Category
    before: object
    after: object


@dataclass(frozen=True, slots=True)
class DifferenceSummary:
    rows: tuple[DifferenceRow, ...]

    def count(self, category: Category) -> int:
        return sum(1 for row in self.rows if row.category == category)

    @property
    def changed_r_paths(self) -> tuple[str, ...]:
        return tuple(row.path for row in self.rows if row.category == "R")

    def as_json(self) -> dict[str, object]:
        """T-CON-26 ``difference_summary``: category counts and the changed R paths."""
        return {
            "M": self.count("M"),
            "P": self.count("P"),
            "T": self.count("T"),
            "R": self.count("R"),
            "changed_r_paths": list(self.changed_r_paths),
        }

    @property
    def only_representation(self) -> bool:
        return all(row.category == "R" for row in self.rows)


def _leaves(
    value: object, prefix: tuple[str | int, ...], out: dict[tuple[str | int, ...], object]
) -> None:
    if isinstance(value, dict):
        if not value:
            out[prefix] = {}
        for key in sorted(value):
            _leaves(value[key], (*prefix, str(key)), out)
    elif isinstance(value, list):
        if not value:
            out[prefix] = []
        for index, item in enumerate(value):
            _leaves(item, (*prefix, index), out)
    else:
        out[prefix] = value


def _classify(path: tuple[str | int, ...]) -> Category:
    if path == ("engine_version",) or path == ("input_sha256",):
        return "R"
    if len(path) >= 2 and path[0] == "books" and isinstance(path[1], int):
        rest = path[2:]
        if rest == ("trace", "engine_version"):
            return "R"
        if rest and rest[0] == "posting_intents":
            return "P"
        if rest and rest[0] in _MONETARY_SECTIONS:
            return "T" if _LINEAGE_KEY in rest else "M"
    return "T"


def _path_text(path: tuple[str | int, ...]) -> str:
    text = ""
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else part)
    return text


def representation_diff(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> DifferenceSummary:
    """Every leaf path whose value differs between the two JSON-level output mappings (a path
    present on one side only counts too), classified M/P/T/R (RCP-28a)."""
    before: dict[tuple[str | int, ...], object] = {}
    after: dict[tuple[str | int, ...], object] = {}
    _leaves(dict(expected), (), before)
    _leaves(dict(actual), (), after)
    rows: list[DifferenceRow] = []
    for path in sorted(set(before) | set(after), key=lambda p: tuple(str(part) for part in p)):
        left = before.get(path, _ABSENT)
        right = after.get(path, _ABSENT)
        if left != right:
            rows.append(
                DifferenceRow(
                    _path_text(path),
                    _classify(path),
                    None if left is _ABSENT else left,
                    None if right is _ABSENT else right,
                )
            )
    return DifferenceSummary(tuple(rows))


_ABSENT: Final = object()
