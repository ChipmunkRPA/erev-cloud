"""Production startup refusals (05 SAR-40 rev 1.53 startup subset; CFG-17, CFG-18, CFG-26;
R-34 SD-5, SD-6).

The security review found that ``erev doctor`` is advisory: a production api or worker started with
the fake email backend (mail written to files nobody reads) and with the documentation
placeholders as master keys. The api lifespan and the worker now evaluate the doctor checks
``email-backend`` and ``master-keys`` on their own settings and refuse to start when either fails,
before the release is stamped and so before any database connection.
"""

from __future__ import annotations

import asyncio
import io
import json
import secrets
from pathlib import Path

import pytest
from erev_api import worker as worker_module
from erev_api.config import (
    MASTER_KEY_FIELDS,
    MASTER_KEY_MIN_DISTINCT_BYTES,
    REPO_ROOT,
    Environment,
    Settings,
    SettingsError,
)
from erev_api.controls import release
from erev_api.controls.doctor import EMAIL_BACKEND, MASTER_KEYS, STARTUP_CHECK_NAMES
from erev_api.controls.startup import (
    StartupRefused,
    production_refusals,
    refuse_unsafe_production,
)
from erev_api.main import create_app
from pydantic import SecretStr
from support.production import production_settings

# The three values deploy/compose.env.example shipped until 05 rev 1.53 (the review's SD-6).
SHIPPED_PLACEHOLDERS = tuple("0" * 63 + digit for digit in "123")
FAKE = (
    "FAIL email-backend: EREV_EMAIL_BACKEND is fake; production requires smtp (05 CFG-17, SAR-40)"
)


def _keys(*values: str) -> dict[str, SecretStr]:
    return {field: SecretStr(value) for field, value in zip(MASTER_KEY_FIELDS, values, strict=True)}


def _generated() -> tuple[str, str, str]:
    return (secrets.token_hex(32), secrets.token_hex(32), secrets.token_hex(32))


def test_a_sound_production_configuration_is_not_refused(app_settings: Settings) -> None:
    sound = production_settings(app_settings, **_keys(*_generated()))
    assert production_refusals(sound) == ()
    refuse_unsafe_production(sound)  # no exception
    # The rule never rejects a generated key: 32 random bytes hold about 30 distinct values.
    for _ in range(2000):
        assert len(set(secrets.token_bytes(32))) >= MASTER_KEY_MIN_DISTINCT_BYTES


def test_fake_email_is_refused_under_production_only(app_settings: Settings) -> None:
    assert production_refusals(production_settings(app_settings, email_backend="fake")) == (FAKE,)
    # The local environments require the fake backend (DG-KRN-CFG-02) and are never refused.
    assert app_settings.env is Environment.TEST and app_settings.email_backend == "fake"
    assert production_refusals(app_settings) == ()
    for env in (Environment.DEV, Environment.E2E):
        assert production_refusals(app_settings.model_copy(update={"env": env})) == ()


@pytest.mark.parametrize(
    ("missing", "finding"),
    [
        ({"smtp_host": None}, "EREV_SMTP_HOST is not set"),
        ({"smtp_from": None}, "EREV_SMTP_FROM is not set"),
        ({"smtp_host": None, "smtp_from": None}, "EREV_SMTP_HOST and EREV_SMTP_FROM are not set"),
    ],
)
def test_smtp_without_its_relay_or_sender_is_refused(
    missing: dict[str, None], finding: str, app_settings: Settings
) -> None:
    refusals = production_refusals(production_settings(app_settings, **missing))
    assert refusals == (
        f"FAIL email-backend: EREV_EMAIL_BACKEND is smtp and {finding} (05 CFG-18, SAR-40)",
    )


def test_placeholder_and_repeated_master_keys_are_refused(app_settings: Settings) -> None:
    """The shipped placeholders, a repeated pattern and an all-one-value key fail as placeholders;
    two keys with one value fail as repeated; the findings name variables and carry no value."""
    shipped = production_settings(app_settings, **_keys(*SHIPPED_PLACEHOLDERS))
    assert production_refusals(shipped) == tuple(
        f"FAIL master-keys: {name} is a placeholder, not a generated key: fewer than 16 distinct "
        "byte values (05 CFG-26)"
        for name in (
            "EREV_ENCRYPTION_KEY",
            "EREV_AUDIT_HMAC_MASTER_KEY",
            "EREV_SECURITY_EVENT_HMAC_KEY",
        )
    )
    first, second, third = _generated()
    # Fifteen distinct byte values (eighteen zero bytes and fourteen others) are one too few.
    fifteen = "00" * 18 + bytes(range(1, 15)).hex()
    for weak in ("0" * 64, "ab" * 32, "0123456789abcdef" * 4, fifteen):
        refusals = production_refusals(
            production_settings(app_settings, **_keys(first, weak, third))
        )
        assert len(refusals) == 1 and "EREV_AUDIT_HMAC_MASTER_KEY is a placeholder" in refusals[0]
        assert weak not in refusals[0]
    # The boundary: sixteen distinct byte values pass (seventeen zero bytes and fifteen others).
    sixteen = "00" * 17 + bytes(range(1, 16)).hex()
    assert len(set(bytes.fromhex(fifteen))) == 15 and len(set(bytes.fromhex(sixteen))) == 16
    assert (
        production_refusals(production_settings(app_settings, **_keys(first, sixteen, third))) == ()
    )
    repeated = production_refusals(production_settings(app_settings, **_keys(first, second, first)))
    assert repeated == (
        "FAIL master-keys: EREV_ENCRYPTION_KEY and EREV_SECURITY_EVENT_HMAC_KEY hold the same "
        "value; the master keys must differ (05 CFG-26)",
    )
    assert first not in repeated[0]
    # Under the gcp provider the master keys are not used, so they decide nothing.
    hosted = production_settings(app_settings, key_provider="gcp", **_keys(*SHIPPED_PLACEHOLDERS))
    assert production_refusals(hosted) == ()


def test_the_startup_subset_is_the_two_doctor_checks(app_settings: Settings) -> None:
    assert STARTUP_CHECK_NAMES == (EMAIL_BACKEND, MASTER_KEYS)
    both = production_settings(app_settings, email_backend="fake", **_keys(*SHIPPED_PLACEHOLDERS))
    checks = [line.split(":", 1)[0] for line in production_refusals(both)]
    assert checks == ["FAIL email-backend"] + ["FAIL master-keys"] * 3
    with pytest.raises(StartupRefused) as refused:
        refuse_unsafe_production(both)
    assert isinstance(refused.value, SettingsError)
    message = str(refused.value)
    assert message.startswith("production refuses to start: FAIL email-backend: ")
    assert all(placeholder not in message for placeholder in SHIPPED_PLACEHOLDERS)


def test_api_and_worker_refuse_before_the_release_is_stamped(
    app_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """The api lifespan and the worker entry point raise ``StartupRefused`` with every database
    path trapped: nothing is stamped, no job runs, no heartbeat is written, and the log names the
    findings."""

    def trapped(*args: object, **kwargs: object) -> object:
        raise AssertionError("the process went past the startup refusal")

    monkeypatch.setattr(release, "release_session", trapped)
    monkeypatch.setattr("erev_api.main.stamp_release", trapped)
    monkeypatch.setattr(worker_module, "stamp_release", trapped)
    monkeypatch.setattr(worker_module, "_run_worker", trapped)
    monkeypatch.setattr(worker_module, "configure_logging", lambda **kwargs: None)
    refusing = production_settings(app_settings, email_backend="fake")

    app = create_app(refusing)

    async def start() -> None:
        async with app.router.lifespan_context(app):
            pass  # pragma: no cover - startup raises first

    with pytest.raises(StartupRefused, match="EREV_EMAIL_BACKEND is fake"):
        asyncio.run(start())

    monkeypatch.setattr(worker_module, "get_settings", lambda: refusing)
    heartbeat = tmp_path / "worker.heartbeat"
    with pytest.raises(StartupRefused, match="EREV_EMAIL_BACKEND is fake"):
        worker_module.main(heartbeat_file=heartbeat)
    assert not heartbeat.exists()

    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    refused = [event for event in events if event["event"] == "startup.refused"]
    assert len(refused) == 2 and all(event["level"] == "error" for event in refused)
    assert refused[0]["findings"] == [FAKE]


def test_a_sound_production_process_reaches_the_release_stamp(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control: with a sound configuration the lifespan goes on to the release stamp (stood in
    for here), so the refusal is the only thing the bad configurations change."""
    reached: list[Environment] = []

    def stamp(env: Environment, *, request_id: str) -> object:
        reached.append(env)
        raise RuntimeError("stamp reached")

    monkeypatch.setattr("erev_api.main.stamp_release", stamp)
    app = create_app(production_settings(app_settings))

    async def start() -> None:
        async with app.router.lifespan_context(app):
            pass  # pragma: no cover - the stand-in raises

    with pytest.raises(RuntimeError, match="stamp reached"):
        asyncio.run(start())
    assert reached == [Environment.PRODUCTION]


# --- 05 SAR-15, CFG-18 rev 1.53 (supervisor ruling R-39): the private relay and its bundle -------

CA_FINDING = (
    "FAIL email-backend: EREV_SMTP_CA_FILE is not a readable PEM bundle of certificate authorities "
    "(05 CFG-18)"
)


def test_the_private_relay_opt_in_is_a_notice_and_never_a_refusal(app_settings: Settings) -> None:
    """The opt-in is the operator's statement, not a defect: ``email-backend`` warns and the
    process starts."""
    from erev_api.controls.doctor import email_backend, snapshot_settings

    opted = production_settings(app_settings, smtp_private_relay=True)
    assert production_refusals(opted) == ()
    refuse_unsafe_production(opted)  # no exception
    result = email_backend(snapshot_settings(opted))
    assert result.ok and [line.split(":", 1)[0] for line in result.lines()] == [
        "WARN email-backend"
    ]


def test_an_unreadable_certificate_bundle_is_refused(
    app_settings: Settings, tmp_path: Path
) -> None:
    """``EREV_SMTP_CA_FILE`` is loaded as the sender loads it: a missing file, a directory, an
    empty file and a file without a certificate each refuse the start, naming the variable and
    never the path; a bundle with a certificate does not."""
    from support.smtp_sink import authority

    missing = tmp_path / "absent.pem"
    empty = tmp_path / "empty.pem"
    empty.write_text("")
    no_certificate = tmp_path / "text.pem"
    no_certificate.write_text("not a certificate\n")
    for bundle in (missing, tmp_path, empty, no_certificate):
        settings = production_settings(app_settings, smtp_ca_file=bundle)
        assert settings.smtp_ca_findings() == (CA_FINDING.removeprefix("FAIL email-backend: "),)
        assert production_refusals(settings) == (CA_FINDING,)
        assert str(tmp_path) not in CA_FINDING
        with pytest.raises(StartupRefused):
            refuse_unsafe_production(settings)
    sound = production_settings(app_settings, smtp_ca_file=authority(tmp_path / "pki").ca_file)
    assert sound.smtp_ca_findings() == () and production_refusals(sound) == ()
    # Unset is the system trust store: nothing to find.
    assert production_settings(app_settings).smtp_ca_findings() == ()


def test_blank_relay_variables_leave_the_opt_in_off_and_the_bundle_unset() -> None:
    """Compose interpolates a variable its environment file does not name to the empty string: a
    file written before rev 1.53 must leave the opt-in off and the bundle unset, not fail the
    settings. A relative path resolves against the repository root, as the other paths do."""
    blank = Settings(**{"EREV_SMTP_PRIVATE_RELAY": "", "EREV_SMTP_CA_FILE": " "})
    assert (blank.smtp_private_relay, blank.smtp_ca_file) == (False, None)
    on = Settings(**{"EREV_SMTP_PRIVATE_RELAY": "true", "EREV_SMTP_CA_FILE": "/etc/erev/ca.pem"})
    assert (on.smtp_private_relay, on.smtp_ca_file) == (True, Path("/etc/erev/ca.pem"))
    relative = Settings(**{"EREV_SMTP_CA_FILE": "deploy/relay-ca.pem"})
    assert relative.smtp_ca_file == REPO_ROOT / "deploy" / "relay-ca.pem"
    assert Settings().smtp_private_relay is False and Settings().smtp_ca_file is None
