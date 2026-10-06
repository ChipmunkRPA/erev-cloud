"""PRF-1 volume tenant generator (05 PERF-10 to PERF-15; DG-PERF-01; REQ-OPS-009).

The first three tests are pure: they read the manifest and its event stream and touch no database.
``test_small_scale_through_commands`` seeds a 1/1000-scale dataset into a fresh test tenant through
the product's commands (PRD WLD-R-02) and is database-bound (``pg``).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from uuid import UUID

import pytest
from erev_api.domain.demo import builders, seed, tenants, volume
from erev_api.enums import RecognitionMethod
from erev_api.schemas.pob_templates import PobTemplateVersionIn

KEY = re.compile(r"^perf:[0-9a-f]{16}:\d+$")
EXPECTED_MIX = {
    "TIME_ELAPSED": Fraction(45, 100),
    "POINT_IN_TIME": Fraction(20, 100),
    "UNITS_DELIVERED": Fraction(15, 100),
    "USAGE": Fraction(8, 100),
    "MILESTONE": Fraction(5, 100),
    "COST_TO_COST": Fraction(4, 100),
    "MATERIAL_RIGHT": Fraction(3, 100),
}


@pytest.fixture(scope="module")
def full() -> volume.VolumeManifest:
    return volume.manifest()


def test_manifest_deterministic(full: volume.VolumeManifest) -> None:
    """Two manifests with seed 20260912 are byte-identical JSON with the same SHA-256 (PERF-10)."""
    again = volume.manifest(seed=volume.SEED)
    assert again.to_json() == full.to_json()
    assert again.sha256 == full.sha256 and len(full.sha256) == 64
    assert full.industry_cluster == f"perf:{full.sha256[:16]}"
    assert full.idempotency_key(17) == f"perf:{full.sha256[:16]}:17"
    # Another seed or scale is another dataset.
    assert volume.manifest(seed=volume.SEED + 1).sha256 != full.sha256
    assert volume.manifest(Fraction(1, 1000)).sha256 != full.sha256
    # The identity binds the generated reference recipe and the canonical event facts (Codex 2306
    # MANIFEST-BINDING-1): the recipe is in the JSON, and counts.events_sha256 equals the digest
    # recomputed over the stream.
    assert full.recipe.generator_version == volume.GENERATOR_VERSION
    assert full.recipe.fx_rates == volume._fx_rates(full.months)  # noqa: SLF001 — the bound recipe
    assert set(full.recipe.fx_rates) == {"EUR", "GBP"} and len(full.recipe.fx_rates["GBP"]) == 24
    digest = hashlib.sha256()
    for event in full.events():
        digest.update(volume.canonical_event(*event))
    assert digest.hexdigest() == full.counts.events_sha256
    assert full.counts.events_sha256 in full.to_json().decode("ascii")


def _counts_without_digest(m: volume.VolumeManifest) -> dict[str, object]:
    return (
        {k: v for k, v in vars(m.counts).items() if k != "events_sha256"}
        if hasattr(m.counts, "__dict__")
        else {
            name: getattr(m.counts, name)
            for name in m.counts.__dataclass_fields__
            if name != "events_sha256"
        }
    )


def test_identity_discriminates_values_and_dates_with_equal_counts(
    full: volume.VolumeManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 2306 MANIFEST-BINDING-1 discrimination cases: a changed event-date rule keeps every
    count and changes the event digest and the manifest hash; a changed FX base rate keeps the
    event digest and changes the manifest hash."""
    small = volume.manifest(Fraction(1, 100))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(volume, "_effective_day", lambda ordinal, contract_seq: 1)
        dated = volume.manifest(Fraction(1, 100))
    assert _counts_without_digest(dated) == _counts_without_digest(small)
    assert dated.counts.events_sha256 != small.counts.events_sha256
    assert dated.sha256 != small.sha256
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(volume, "FX_BASE", {"GBP": "1.300000", "EUR": "1.100000"})
        rated = volume.manifest(Fraction(1, 100))
    assert rated.counts == small.counts  # every event fact unchanged, digest included
    assert rated.recipe.fx_rates["GBP"] != small.recipe.fx_rates["GBP"]
    assert rated.sha256 != small.sha256
    assert full.sha256 != small.sha256


def test_full_scale_shape(full: volume.VolumeManifest) -> None:
    """From the manifest alone: entities, books, 10,000 contracts (6,000 / 2,500 / 1,500), 50,000
    obligations with 1 to 12 per contract, FY2025-P01 to FY2026-P12, 400 products, one SSP book
    with 2 versions, 12 POB templates (05 PERF-12)."""
    by_code = {e.code: e for e in full.entities}
    assert [(e.code, e.functional_currency, e.time_zone) for e in full.entities] == [
        ("VOL-US", "USD", "America/New_York"),
        ("VOL-UK", "GBP", "Europe/London"),
        ("VOL-DE", "EUR", "Europe/Berlin"),
    ]
    assert all("ASC606" in e.books for e in full.entities)
    assert by_code["VOL-UK"].books == ("ASC606", "IFRS15")
    assert "IFRS15" not in by_code["VOL-US"].books and "IFRS15" not in by_code["VOL-DE"].books
    assert len(full.contracts) == 10_000 == full.counts.contracts
    assert full.counts.contracts_by_entity == {"VOL-US": 6_000, "VOL-UK": 2_500, "VOL-DE": 1_500}
    per_contract = [len(c.obligations) for c in full.contracts]
    assert sum(per_contract) == 50_000 == full.counts.obligations
    assert min(per_contract) >= 1 and max(per_contract) <= 12
    assert full.periods[0] == "FY2025-P01" and full.periods[-1] == "FY2026-P12"
    assert len(full.periods) == 24 == full.months
    assert len(full.products) == 400 and len({p.code for p in full.products}) == 400
    assert full.ssp_book == "VOL-SSP" and len(full.ssp_versions) == 2
    assert [v.effective_from for v in full.ssp_versions] == ["2025-01-01", "2026-01-01"]
    assert len(full.templates) == 12 and len({t.code for t in full.templates}) == 12
    # Every template's outputs are a valid POB template version body, and every product names a
    # template of its class; every obligation names a product and template of its class.
    effective = datetime(2025, 1, 1, tzinfo=UTC)
    for template in full.templates:
        body = PobTemplateVersionIn.model_validate(
            {**template.outputs, "effective_from": effective}
        )
        assert body.effective_from == effective
    templates = {t.code: t for t in full.templates}
    products = {p.code: p for p in full.products}
    for product in full.products:
        assert templates[product.template_code].mix_class == product.mix_class
    for contract in full.contracts:
        for ob in contract.obligations:
            assert products[ob.product_code].mix_class == ob.mix_class
            assert templates[ob.template_code].mix_class == ob.mix_class
            assert RecognitionMethod(ob.recognition_method)
        assert contract.inception_date.startswith(
            volume.month_start(contract.inception_month).isoformat()[:7]
        )


def test_recognition_and_event_mix(full: volume.VolumeManifest) -> None:
    """Obligation mix within ±0.5 percentage points; 10% foreign currency and 5% cross-entity
    contracts; month 24 holds 8% of about 1.3 million events (within 5%); 0.5% late events;
    idempotency keys ``perf:<16 hex>:<event seq>`` (05 PERF-13, PERF-14)."""
    counts = full.counts
    for name, share in EXPECTED_MIX.items():
        observed = Fraction(counts.obligations_by_class[name], counts.obligations)
        assert abs(observed - share) <= Fraction(1, 200), (name, float(observed))
    assert counts.foreign_currency_contracts == 1_000
    assert counts.cross_entity_contracts == 500
    assert counts.cost_assets == 2_000  # 2 contract cost assets per 10 contracts
    assert all(
        c.currency != volume.ENTITY_BY_CODE[c.entity_code].functional_currency
        for c in full.contracts
        if c.foreign_currency
    )
    subscriptions = [
        ob.term_months
        for c in full.contracts
        for ob in c.obligations
        if ob.mix_class == "TIME_ELAPSED"
    ]
    assert all(term is not None and 12 <= term <= 36 for term in subscriptions)

    assert abs(counts.events - 1_300_000) <= 65_000, counts.events
    month_24 = Fraction(counts.events_by_month[-1], counts.events)
    assert abs(month_24 - Fraction(8, 100)) <= Fraction(1, 200), float(month_24)
    late = Fraction(counts.late_events, counts.events)
    assert abs(late - Fraction(5, 1000)) <= Fraction(1, 1000), float(late)

    # The stream agrees with the counts and numbers its events 1 … n with unique keys.
    streamed = Counter[str]()
    by_month = [0] * full.months
    late_seen = 0
    expected_seq = 0
    for event in full.events():
        expected_seq += 1
        assert event.seq == expected_seq
        streamed[event.event_type] += 1
        by_month[event.recorded_month - 1] += 1
        late_seen += int(event.late)
        if event.late:
            assert event.recorded_month == event.effective_month + 1
        else:
            assert event.recorded_month == event.effective_month
        assert 1 <= event.recorded_month <= full.months
    assert expected_seq == counts.events
    assert dict(streamed) == dict(counts.events_by_type)
    assert tuple(by_month) == counts.events_by_month
    assert late_seen == counts.late_events
    sample = next(full.events())
    assert KEY.match(full.idempotency_key(sample.seq))
    assert full.idempotency_key(1) != full.idempotency_key(2)
    assert {e.event_type for e in full.events_for_month(24)} <= set(counts.events_by_type)


# --- database-bound (PRD WLD-R-02): NOT RUN in the CPU gates of lane P7 --------------------------

WLD_VOLUME_TEST: str = "WLD-VOL-TEST"


# Database-bound through the demo scaffold (test_database); the `pg` marker stays under pg/
# (DG-TST-07).
@pytest.mark.slow
def test_small_scale_through_commands(
    test_database: object, keyring: object, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """``seed(scale=Fraction(1, 1000))`` into a fresh test tenant computes every group through
    commands and inserts no row outside a command except global catalogues (05 PERF-15;
    WLD-R-02). Runs through the demo scaffold: a stand-in tenant whose WLD id maps to the volume
    seed, so provisioning, personas and sign-ins are the product's (PRF-2 replaces the scaffold
    with ``erev perf seed``)."""
    import pyotp
    from erev_api.db.session import DbContext, platform_session, tenant_session
    from erev_api.db.tables import (
        combination_group,
        contract,
        contract_version,
        estimate,
        estimate_version,
        file_attachment,
        judgement_record,
        tenant,
    )
    from erev_api.domain.demo import personas
    from erev_api.files.store import LocalFileStore
    from sqlalchemy import func, select
    from support.clock import frozen_clock
    from support.factories import stamp_test_release

    small = volume.manifest(Fraction(1, 1000))
    root = tmp_path_factory.mktemp("prf-1")
    code = f"vol-{secrets.token_hex(4)}"
    stand_in = replace(tenants.CATALOGUE[1], code=code, wld_id=WLD_VOLUME_TEST)
    cast = tuple(
        replace(p, email=f"{p.key}.{secrets.token_hex(3)}@{personas.DEMO_DOMAIN}")
        for p in personas.PERSONAS
    )
    reports: list[volume.SeedReport] = []

    def build(ctx: builders.BuildContext) -> None:
        reports.append(volume.seed(ctx, scale=Fraction(1, 1000), cast=volume.DEMO_CAST))

    stamp_test_release()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, stand_in))
        patch.setitem(builders.BUILDERS, WLD_VOLUME_TEST, (build,))  # type: ignore[arg-type]
        result = seed.seed_demo(
            [code],
            frozen_clock(),
            keyring=keyring,  # type: ignore[arg-type]
            files=LocalFileStore(root / "files"),
            secrets=seed.DemoSecrets(
                password=f"Seed-{secrets.token_urlsafe(12)}", totp_secret=pyotp.random_base32()
            ),
            credentials_path=root / "run" / seed.CREDENTIALS_FILE,
            request_id=f"prf1-{secrets.token_hex(4)}",
            personas=cast,
        )
    assert result.outcomes == ((code, "seeded"),)
    (report,) = reports
    assert report.manifest_sha256 == small.sha256
    assert report.contracts == small.counts.contracts == len(small.contracts)
    with platform_session("tenant_directory", actor_user_id=None, request_id="prf1-read") as db:
        tenant_id = UUID(
            str(db.execute(select(tenant.c.id).where(tenant.c.code == code)).scalar_one())
        )
    scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        assert (
            db.execute(select(func.count()).select_from(contract)).scalar_one() == report.contracts
        )
        groups = db.execute(select(combination_group.c.id)).scalars().all()
        computed = db.execute(
            select(func.count(func.distinct(contract_version.c.combination_group_id)))
        ).scalar_one()
    assert len(groups) >= 1 and computed == len(groups) == report.groups_recomputed
    assert report.events_appended + report.events_deferred == small.counts.events

    # 04 §16.14 rev 1.241 (BUILD_SPEC CTR-12; generator version 7): every estimate version the
    # seed submitted holds its evidence document, and every variable-consideration version names
    # the reviewed CONSTRAINT record of its element — a record of the version itself. An EAC
    # version names none.
    with tenant_session(scope, read_only=True) as db:
        versions = db.execute(
            select(
                estimate_version.c.id,
                estimate_version.c.status,
                estimate_version.c.judgement_record_id,
                estimate.c.estimate_kind,
                estimate.c.element_code,
            ).select_from(
                estimate_version.join(estimate, estimate.c.id == estimate_version.c.estimate_id)
            )
        ).all()
        evidenced = set(
            db.execute(
                select(file_attachment.c.subject_id).where(
                    file_attachment.c.subject_type == volume.ESTIMATE_VERSION_SUBJECT,
                    file_attachment.c.voided_at.is_(None),
                )
            ).scalars()
        )
        records = {
            row.id: (str(row.topic), str(row.status), str(row.subject_type), row.subject_id)
            for row in db.execute(
                select(
                    judgement_record.c.id,
                    judgement_record.c.topic,
                    judgement_record.c.status,
                    judgement_record.c.subject_type,
                    judgement_record.c.subject_id,
                ).where(judgement_record.c.topic == "CONSTRAINT")
            )
        }
    changes = [e for e in small.events() if e.event_type == "ESTIMATE_CHANGED"]
    assert len(versions) == len(changes) > 0
    assert {str(row.status) for row in versions} <= {"APPROVED", "SUPERSEDED"}
    assert {row.id for row in versions} == evidenced
    constrained = [row for row in versions if str(row.estimate_kind) == "VARIABLE_CONSIDERATION"]
    assert constrained, "the small manifest changes a variable-consideration estimate"
    for row in constrained:
        assert records[row.judgement_record_id] == (
            "CONSTRAINT",
            "REVIEWED",
            volume.ESTIMATE_VERSION_SUBJECT,
            row.id,
        ), row.element_code
    assert len(records) == len(constrained)
    assert all(
        row.judgement_record_id is None
        for row in versions
        if str(row.estimate_kind) != "VARIABLE_CONSIDERATION"
    )
