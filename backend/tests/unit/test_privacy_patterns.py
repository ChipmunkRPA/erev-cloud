"""05 PRV-08 redaction patterns (BUILD_SPEC SOP-5; 03 REQ-AI-009). CPU only."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from erev_api.privacy import patterns
from erev_api.privacy.patterns import (
    EMAIL_PLACEHOLDER,
    PHONE_PLACEHOLDER,
    Redaction,
    redact,
    redact_text,
    redact_value,
)

EMAILS = [
    "ada@example.com",
    "first.last+tag@sub.example.co.uk",
    "erased+2a1f3c4d-0000-4000-8000-000000000001@invalid.erev",
    "UPPER.Case@Example.ORG",
    "x_y%z@example.io",
    "12345@numbers.example",
]
PHONES = [
    "(415) 555-0100",
    "(415)555-0100",
    "415-555-0100",
    "415.555.0100",
    "415 555 0100",
    "+1 415 555 0100",
    "+1-415-555-0100",
    "+15551234567",
    "+44 20 7946 0958",
    "+49 (30) 901820",
    "+33 1 42 68 53 00",
    "+299 123456",
]
NOT_PERSONAL = [
    "1,234,567.89",
    "$12,345.00",
    "+1 234 567.89",
    "1 234 567.89",
    "2026-09-21",
    "09/21/2026",
    "21.09.2026",
    "INV-2026-000123",
    "PO 4500123456",
    "550e8400-e29b-41d4-a716-446655440000",
    "GB82 WEST 1234 5698 7654 32",
    "12.5%",
    "ASC 606-10-32-40",
    "T-PLT-29",
    "version 1.2.3",
    "1234567890123456",
    "acct 415-555",
    "ada at example dot com",
    "@handle",
    "user@localhost",
]


@pytest.mark.parametrize("email", EMAILS)
def test_prv_08_emails_are_replaced(email: str) -> None:
    result = redact(f"Contact {email} today.")
    assert result.text == f"Contact {EMAIL_PLACEHOLDER} today."
    assert (result.emails, result.phones) == (1, 0)


@pytest.mark.parametrize("phone", PHONES)
def test_prv_08_phones_are_replaced(phone: str) -> None:
    result = redact(f"Call {phone} now.")
    assert result.text == f"Call {PHONE_PLACEHOLDER} now.", phone
    assert (result.emails, result.phones) == (0, 1), phone


@pytest.mark.parametrize("text", NOT_PERSONAL)
def test_prv_08_financial_text_is_left_alone(text: str) -> None:
    result = redact(f"Line item {text} posted.")
    assert result.text == f"Line item {text} posted.", text
    assert not result.changed, text


def test_prv_08_placeholders_and_order() -> None:
    assert EMAIL_PLACEHOLDER == "[email]" and PHONE_PLACEHOLDER == "[phone]"
    text = "From +15551234567@example.com or +1 415 555 0100; invoice 1,234.56 due 2026-09-21."
    result = redact(text)
    assert result == Redaction(
        text=f"From {EMAIL_PLACEHOLDER} or {PHONE_PLACEHOLDER}; invoice 1,234.56 due 2026-09-21.",
        emails=1,
        phones=1,
    )
    # An address with a numeric local part is one [email], never a partial [phone].
    assert PHONE_PLACEHOLDER not in redact_text("+15551234567@example.com")


def test_prv_08_idempotent_and_counts() -> None:
    text = "ada@example.com, bob@example.com; (415) 555-0100 and +44 20 7946 0958"
    once = redact(text)
    assert (once.emails, once.phones) == (2, 2)
    twice = redact(once.text)
    assert twice.text == once.text and not twice.changed
    assert redact_text("nothing personal here") == "nothing personal here"
    assert not redact("").changed and redact("").text == ""


def test_prv_08_redact_value_walks_json_like_values() -> None:
    value = {
        "customer_email": "ada@example.com",
        "lines": [{"memo": "call (415) 555-0100"}, "plain", 12, None, True],
        "amount": "1,234.56",
        "nested": {"phone": "+44 20 7946 0958", "count": 3},
    }
    assert redact_value(value) == {
        "customer_email": EMAIL_PLACEHOLDER,
        "lines": [{"memo": f"call {PHONE_PLACEHOLDER}"}, "plain", 12, None, True],
        "amount": "1,234.56",
        "nested": {"phone": PHONE_PLACEHOLDER, "count": 3},
    }
    assert redact_value(("a@example.com", b"bytes")) == [EMAIL_PLACEHOLDER, b"bytes"]
    assert redact_value(7) == 7 and redact_value(None) is None
    # Keys are never rewritten: the key names the field, the value holds the data.
    assert set(redact_value({"ada@example.com": "x"})) == {"ada@example.com"}


def test_prv_08_module_is_a_standalone_kernel_module() -> None:
    """The patterns are shared by the AI adapter and the prompt builders, so the module imports
    nothing from ``erev_api`` (DG-LAY-03) and defines exactly the public names it documents."""
    tree = ast.parse(Path(patterns.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert "erev_api" not in imported
    assert set(patterns.__all__) == {
        "EMAIL",
        "EMAIL_PLACEHOLDER",
        "PHONE_INTERNATIONAL",
        "PHONE_NORTH_AMERICAN",
        "PHONE_PLACEHOLDER",
        "Redaction",
        "redact",
        "redact_text",
        "redact_value",
    }
