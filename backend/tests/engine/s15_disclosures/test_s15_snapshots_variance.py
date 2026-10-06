"""Lock snapshot datasets and variance between closes (ENGINE_SPEC_B §15.2.7 S15-R-18 to S15-R-20,
§15.2.8 S15-R-21 to S15-R-23, S15-INV-06, S15-INV-07, EX-15-D; 04 T-CLS-04, T-CLS-05, E-64;
DEV-099; BUILD_SPEC EDS-6; lane F-RPS + ENG-E1 prep).

Pure modules: the platform writes the files and the lock rows (CLO-6), the engine encodes and
decomposes. Figures are the EX-15-D / K-03 figures of the specification, never engine output.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine.stages.s15_disclosures.snapshots import (
    SNAPSHOT_KINDS,
    Column,
    Dataset,
    Money,
    encode,
    manifest_sha256,
    opening_from_rollforward,
    sum_money,
)
from erev_engine.stages.s15_disclosures.variance import (
    DRIVERS,
    Evaluation,
    decompose,
    totals_by_driver,
)


def usd(text: str) -> Money:
    return Money(int(Decimal(text) * 100), "USD", 2)


def jpy(text: str) -> Money:
    return Money(int(Decimal(text)), "JPY", 0)


ROLLFORWARD_COLUMNS = (
    Column("row_key", "text"),
    Column("currency", "text"),
    Column("contract_liability", "money"),
    Column("contract_asset", "money"),
    Column("unbilled_receivable", "money"),
)


def _rollforward(closing: str = "29944.11") -> Dataset:
    rows = (
        {
            "row_key": "OPENING",
            "currency": "USD",
            "contract_liability": usd("39708.49"),
            "contract_asset": usd("0.00"),
            "unbilled_receivable": usd("0.00"),
        },
        {
            "row_key": "REVENUE_FROM_OPENING",
            "currency": "USD",
            "contract_liability": usd("-9764.38"),
            "contract_asset": usd("0.00"),
            "unbilled_receivable": usd("0.00"),
        },
        {
            "row_key": "CLOSING",
            "currency": "USD",
            "contract_liability": usd(closing),
            "contract_asset": usd("0.00"),
            "unbilled_receivable": usd("0.00"),
        },
    )
    return Dataset("CONTRACT_BALANCE_ROLLFORWARD", ROLLFORWARD_COLUMNS, rows)


def test_s15_r18_dataset_encoding() -> None:
    """Bytes are UTF-8 CSV with a header row, rows sorted by row key, money with exactly the
    currency's minor-unit places ("1200" for JPY, "12.30" for USD), exact values trimmed, no index
    column (DEV-099); ``file_sha256`` is the SHA-256 of the bytes; two builds from the same state
    give identical bytes and control totals (S15-INV-06)."""
    columns = (
        Column("row_key", "text"),
        Column("entity", "text"),
        Column("amount", "money"),
        Column("ratio", "exact"),
        Column("count", "integer"),
        Column("as_of", "date"),
    )
    rows = (
        {
            "row_key": "b",
            "entity": "JP01",
            "amount": jpy("1200"),
            "ratio": Fraction(1, 3),
            "count": 2,
            "as_of": date(2026, 9, 30),
        },
        {
            "row_key": "a",
            "entity": "US01",
            "amount": usd("12.30"),
            "ratio": Fraction(1, 2),
            "count": 1,
            "as_of": date(2026, 9, 30),
        },
        {
            "row_key": "c, quoted",
            "entity": "US01",
            "amount": usd("-0.05"),
            "ratio": Fraction(0),
            "count": 0,
            "as_of": date(2026, 9, 30),
        },
    )
    dataset = Dataset("WATERFALL", columns, rows)
    encoded = encode(dataset, sum_money(rows, "amount"))
    text = encoded.content.decode("utf-8")
    assert text.splitlines() == [
        "row_key,entity,amount,ratio,count,as_of",
        "a,US01,12.30,0.5,1,2026-09-30",
        "b,JP01,1200,0.333333333333333333,2,2026-09-30",
        '"c, quoted",US01,-0.05,0,0,2026-09-30',
    ]
    assert text.endswith("\n") and "\r" not in text
    assert encoded.file_sha256 == hashlib.sha256(encoded.content).hexdigest()
    assert (encoded.row_count, encoded.control_totals) == (3, {"JPY": "1200", "USD": "12.25"})
    again = encode(Dataset("WATERFALL", columns, tuple(reversed(rows))), sum_money(rows, "amount"))
    assert (again.content, again.file_sha256, again.control_totals) == (
        encoded.content,
        encoded.file_sha256,
        encoded.control_totals,
    )
    # No coercion: a float, a bool or a str in a money column is refused (CV-30).
    for bad in (12.3, True, "12.30"):
        with pytest.raises(TypeError):
            encode(Dataset("WATERFALL", columns, ({**rows[1], "amount": bad},)))
    with pytest.raises(ValueError, match="row_key"):
        Dataset("WATERFALL", (Column("entity", "text"), *columns[1:]), ())
    with pytest.raises(ValueError, match="duplicate row_key"):
        Dataset("WATERFALL", columns, (rows[0], rows[0]))
    with pytest.raises(ValueError, match="unknown snapshot kind"):
        Dataset("BALANCES", columns, ())


def test_s15_r19_manifest_hash() -> None:
    """``manifest_sha256`` is the SHA-256 of the lines ``<kind>:<file_sha256>``, sorted by kind and
    joined with ``\\n``; insertion order and unknown kinds do not enter."""
    files = {
        "RPO": hashlib.sha256(b"rpo").hexdigest(),
        "CONTRACT_BALANCES": hashlib.sha256(b"balances").hexdigest(),
        "WATERFALL": hashlib.sha256(b"waterfall").hexdigest(),
    }
    expected = hashlib.sha256(
        "\n".join(f"{kind}:{files[kind]}" for kind in sorted(files)).encode()
    ).hexdigest()
    assert manifest_sha256(files) == expected
    assert manifest_sha256(dict(reversed(list(files.items())))) == expected
    assert manifest_sha256({}) == hashlib.sha256(b"").hexdigest()
    with pytest.raises(ValueError, match="unknown snapshot kind"):
        manifest_sha256({"BALANCES": files["RPO"]})
    with pytest.raises(ValueError, match="SHA-256"):
        manifest_sha256({"RPO": "abc"})
    assert len(SNAPSHOT_KINDS) == 12 and "COST_ROLLFORWARD" in SNAPSHOT_KINDS


def _evaluations() -> list[Evaluation]:
    """EX-15-D, K-03 cumulative revenue from the August 2026 lock to the September 2026 lock:
    ``PROGRESS`` (time) 0.00, ``MODIFICATION`` 91,463.41, ``PROGRESS`` 135,000.00,
    ``ESTIMATE_CHANGE`` (29,169.29), total 197,294.12."""
    values = [
        Fraction(0),
        Fraction("91463.41"),
        Fraction("91463.41") + Fraction(60000),  # two PROGRESS events of one run …
        Fraction("91463.41") + Fraction(135000),  # … whose run effect is 135,000.00
        Fraction("197294.12"),
    ]
    return [
        Evaluation("PROGRESS", values[0]),
        Evaluation("MODIFICATION", values[1], "K-03/EV-000007"),
        Evaluation("PROGRESS", values[2], "K-03/EV-000008"),
        Evaluation("PROGRESS", values[3], "K-03/EV-000009"),
        Evaluation("ESTIMATE_CHANGE", values[4], "K-03/EV-000010"),
    ]


def test_ex_15_d_variance_between_closes() -> None:
    result = decompose(Fraction(0), _evaluations())
    assert [(effect.driver, effect.amount) for effect in result.effects] == [
        ("PROGRESS", Fraction(0)),
        ("MODIFICATION", Fraction("91463.41")),
        ("PROGRESS", Fraction(135000)),
        ("ESTIMATE_CHANGE", Fraction("-29169.29")),
    ]
    assert result.effects[2].event_keys == ("K-03/EV-000008", "K-03/EV-000009")
    assert result.total == Fraction("197294.12") and result.sums_exactly
    assert totals_by_driver(result.effects)["PROGRESS"] == Fraction(135000)
    # September lock → re-lock (J-14): LATE_EVENT +32,558.82 on revenue, (32,558.82) on RPO.
    relock = decompose(
        Fraction("197294.12"), [Evaluation("LATE_EVENT", Fraction("229852.94"), "K-03/EV-000011")]
    )
    assert [(e.driver, e.amount) for e in relock.effects] == [("LATE_EVENT", Fraction("32558.82"))]
    rpo = decompose(
        Fraction("552705.88"), [Evaluation("LATE_EVENT", Fraction("520147.06"), "K-03/EV-000011")]
    )
    assert rpo.effects[0].amount == Fraction("-32558.82") and rpo.sums_exactly


def test_s15_inv_07_drivers_sum_exactly_whatever_the_grouping() -> None:
    """Σ drivers = metric(later) − metric(earlier) exactly; grouping consecutive events of one
    driver changes no driver total (S15-R-22 [J]); an empty replay is PROGRESS-free and total 0."""
    evaluations = _evaluations()
    grouped = decompose(Fraction(0), evaluations)
    split = decompose(
        Fraction(0),
        [
            *evaluations[:2],
            Evaluation("PROGRESS", evaluations[2].value, "a"),
            Evaluation("PROGRESS", evaluations[3].value, "b"),
            evaluations[4],
        ],
    )
    assert totals_by_driver(grouped.effects) == totals_by_driver(split.effects)
    assert grouped.sums_exactly and split.sums_exactly
    empty = decompose(Fraction("197294.12"), [])
    assert (empty.total, empty.effects, empty.sums_exactly) == (Fraction(0), (), True)
    assert tuple(totals_by_driver(()).keys()) == DRIVERS
    with pytest.raises(ValueError, match="unknown variance driver"):
        Evaluation("TIME", Fraction(0))
    with pytest.raises(TypeError):
        Evaluation("PROGRESS", 1.5)  # type: ignore[arg-type]


def test_s15_r20_opening_from_previous_snapshot() -> None:
    """The rollforward opening of period t equals the closing of the
    ``CONTRACT_BALANCE_ROLLFORWARD`` dataset of t − 1, read from its ``CLOSING`` row (or
    ``CLOSING:<ISO>``)."""
    previous = _rollforward()
    opening = opening_from_rollforward(
        previous.rows, ("contract_liability", "contract_asset", "unbilled_receivable")
    )
    assert opening == {
        "contract_liability": usd("29944.11"),
        "contract_asset": usd("0.00"),
        "unbilled_receivable": usd("0.00"),
    }
    mixed = tuple({**row, "row_key": f"{row['row_key']}:USD"} for row in previous.rows)
    assert opening_from_rollforward(mixed, ("contract_liability",))["contract_liability"] == usd(
        "29944.11"
    )
    with pytest.raises(ValueError, match="CLOSING rows"):
        opening_from_rollforward(previous.rows[:2], ("contract_liability",))
    encoded = encode(previous, sum_money(previous.rows, "contract_liability"))
    assert encoded.control_totals == {"USD": "59888.22"}  # Σ over the three rows of that column


# --- Codex review F-RPS-E1-R3 (PRODUCTION-F-RPS-E1-INDEPENDENT-642363e.md) ---


def test_r3_inconsistent_currency_scale_is_refused() -> None:
    """``Money(123, "USD", 2)`` and ``Money(123, "USD", 0)`` would encode "1.23" and "123" with one
    hash and a control total that depends on row order. The scale is validated against the currency
    table at construction (USD is 2 places), and a dataset or control total mixing two scales of one
    currency outside the table is refused before aggregation."""
    with pytest.raises(ValueError, match="minor_unit"):
        Money(123, "USD", 0)
    with pytest.raises(ValueError, match="minor_unit"):
        Money(1200, "JPY", 2)
    columns = (Column("row_key", "text"), Column("amount", "money"))
    rows = (
        {"row_key": "a", "amount": Money(123, "ZZZ", 2)},
        {"row_key": "b", "amount": Money(123, "ZZZ", 0)},
    )
    with pytest.raises(ValueError, match="scale"):
        sum_money(rows, "amount")
    with pytest.raises(ValueError, match="scale"):
        encode(Dataset("WATERFALL", columns, rows))
    with pytest.raises(ValueError, match="scale"):
        encode(Dataset("WATERFALL", columns, tuple(reversed(rows))))
    consistent = (
        {"row_key": "a", "amount": Money(123, "ZZZ", 2)},
        {"row_key": "b", "amount": Money(1, "ZZZ", 2)},
    )
    assert sum_money(consistent, "amount") == {"ZZZ": "1.24"}


def test_s15_r18_encoding_edge_cases() -> None:
    """Empty dataset (header only, zero rows, no totals); zero and large money; negative exact;
    RFC 4180 quoting of quotes and newlines; a full twelve-kind manifest; refused Money members."""
    columns = (
        Column("row_key", "text"),
        Column("note", "text"),
        Column("amount", "money"),
        Column("ratio", "exact"),
    )
    empty = encode(Dataset("JE_POPULATION", columns, ()), sum_money((), "amount"))
    assert empty.content == b"row_key,note,amount,ratio\n"
    assert (empty.row_count, empty.control_totals) == (0, {})
    rows = (
        {
            "row_key": "big",
            "note": 'say "hi"',
            "amount": usd("10000000000000.00"),
            "ratio": Fraction(-1, 3),
        },
        {"row_key": "zero", "note": "line\nbreak", "amount": jpy("0"), "ratio": Fraction(0)},
    )
    encoded = encode(Dataset("JE_POPULATION", columns, rows), sum_money(rows, "amount"))
    text = encoded.content.decode("utf-8")
    lines = text.split("\n")
    assert lines[1].startswith('big,"say ""hi""",10000000000000.00,-0.3333')
    assert lines[2] == 'zero,"line' and lines[3] == 'break",0,0'
    assert encoded.control_totals == {"JPY": "0", "USD": "10000000000000.00"}
    files = {kind: hashlib.sha256(kind.encode()).hexdigest() for kind in SNAPSHOT_KINDS}
    full = manifest_sha256(files)
    assert (
        full
        == hashlib.sha256(
            "\n".join(f"{kind}:{files[kind]}" for kind in sorted(files)).encode()
        ).hexdigest()
    )
    assert full != manifest_sha256(
        {kind: digest for kind, digest in files.items() if kind != "RPO"}
    )
    with pytest.raises(TypeError):
        Money(True, "USD", 2)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="minor_unit"):
        Money(1, "ZZZ", 7)
    with pytest.raises(ValueError, match="minor_unit"):
        Money(1, "ZZZ", 2.0)  # type: ignore[arg-type]
