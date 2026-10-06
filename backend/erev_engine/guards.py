"""Bundle guards (dev-guide §7 DG-ENG-03; ENGINE_SPEC CV-30, CV-45).

``no_floats`` runs on the input and output bundles of ``compute``; ``assert_sorted`` rejects a
bundle tuple whose natural-key order was not established by bundle assembly. Standard library only.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any, Final

from erev_engine.errors import EngineError

__all__ = ["assert_sorted", "no_floats"]

_LEAVES: Final = (str, bytes, int, Fraction, Decimal, date, timedelta, timezone, Enum)


def no_floats(value: object) -> None:
    """Raise ``EngineError("FLOAT_DETECTED")`` when a float occurs anywhere inside ``value``.

    Frozen dataclasses, mappings (keys and values), lists, tuples and sets are walked; exact
    numbers, strings, dates and enum members are leaves. Any other type is a malformed bundle and
    raises ``TypeError`` (CV-45). Set members are walked in a sorted order, so the detail does not
    depend on ``PYTHONHASHSEED`` (DG-ENG-02; CV-23).
    """
    pending: list[tuple[object, str]] = [(value, "$")]
    seen: set[int] = set()
    while pending:
        item, path = pending.pop()
        if isinstance(item, float):
            raise EngineError(
                "FLOAT_DETECTED", "a float value reached the engine", detail={"path": path}
            )
        if item is None or isinstance(item, _LEAVES):
            continue
        if id(item) in seen:
            continue
        seen.add(id(item))
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            pending.extend(
                (getattr(item, field.name), f"{path}.{field.name}")
                for field in dataclasses.fields(item)
            )
        elif isinstance(item, Mapping):
            for index, (key, member) in enumerate(item.items()):
                pending.append((key, f"{path}{{key {index}}}"))
                pending.append((member, f"{path}[{key!r}]" if isinstance(key, str) else path))
        elif isinstance(item, list | tuple):
            pending.extend((member, f"{path}[{index}]") for index, member in enumerate(item))
        elif isinstance(item, set | frozenset):
            members = sorted(item, key=lambda m: (type(m).__qualname__, repr(m)))
            pending.extend((member, f"{path}[{index}]") for index, member in enumerate(members))
        else:
            raise TypeError(f"no_floats does not support {type(item).__qualname__} at {path}")


def assert_sorted[T](
    items: Sequence[T], key: Callable[[T], Any], *, name: str, unique: bool = True
) -> None:
    """``ValueError`` when ``items`` are not in ascending ``key`` order (CV-45).

    With ``unique`` true, equal keys are rejected as well, because bundle tuples are keyed by
    natural keys (DG-ENG-02).
    """
    previous: Any = None
    for index, item in enumerate(items):
        current = key(item)
        if index and (previous >= current if unique else previous > current):
            raise ValueError(f"{name} is not sorted by its key at position {index}")
        previous = current
