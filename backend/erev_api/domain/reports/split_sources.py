"""Read original collection dates retained by split-layer creation nodes."""

from datetime import date

from erev_engine.trace import TraceNode


def original_date(node: TraceNode | None, effective: date) -> date:
    if node is None or "original_created_on" not in node.params:
        return effective
    if node.formula_id not in {"alloc.largest_remainder.v1", "fx.split_restore.v1"}:
        raise ValueError("Historical split age has no retained allocation source")
    original = date.fromisoformat(node.params["original_created_on"])
    if original > effective or not node.params.get("original_source_key"):
        raise ValueError("Historical split age is inconsistent with its original source")
    return original
