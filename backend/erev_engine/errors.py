"""Engine errors (dev-guide §7; DG-ENG-06).

Codes are those of the 04 §15.4 finding and exception catalogue (for example ``NEGATIVE_WEIGHT``,
``TOTAL_WEIGHT_ZERO``) plus the engine codes ``ENGINE_VERSION_MISMATCH``, ``FLOAT_DETECTED``,
``TRACE_DUPLICATE_NODE`` and ``ENGINE_INVARIANT_VIOLATED``. The engine never returns partial
output, and messages carry no personal data. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["EngineError"]


class EngineError(Exception):
    """A computation stopped with a catalogue or engine code."""

    code: str
    message: str
    subject_key: str | None
    formula_id: str | None
    detail: Mapping[str, str]

    def __init__(
        self,
        code: str,
        message: str,
        *,
        subject_key: str | None = None,
        formula_id: str | None = None,
        detail: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code, message)
        self.code = code
        self.message = message
        self.subject_key = subject_key
        self.formula_id = formula_id
        self.detail = dict(sorted((detail or {}).items()))

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __reduce__(self) -> tuple[Any, ...]:
        # Keyword-only members survive pickling across engine worker processes.
        return (
            _restore,
            (self.code, self.message, self.subject_key, self.formula_id, dict(self.detail)),
        )


def _restore(
    code: str,
    message: str,
    subject_key: str | None,
    formula_id: str | None,
    detail: dict[str, str],
) -> EngineError:
    return EngineError(code, message, subject_key=subject_key, formula_id=formula_id, detail=detail)
