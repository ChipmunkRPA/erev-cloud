"""A level P value that no computation of a contract reads is not stated, without a database (item
PRODUCT-POLICY-VALUE-NOT-READ-1, register index 309; POLICIES §0.5 rule 1 rev 1.125; 04 T-REF-20
and T-REF-23 rev 1.323; PRD ERR-103 rev 1.210; supervisor ruling R-126 (c) and the supervisor's
rulings of 2026-10-03 on the lane's list and on the words).

Bundle assembly gives a product's and an obligation template's policy value to the engine for an
OBLIGATION. The engine reads three parameters that list level P for a CONTRACT — POL-240
``usage.tier_minimum_method``, POL-029 ``upfront_fee.recognition_period`` and POL-021
``pob.shipping_as_fulfilment`` — so such a value was stored, approved with its template version
and taken by no rule. ``reference.products.policy_values_errors``, the one check of the four
doors that store level P values, refuses it by name with what applies instead. This module
pins, as pure functions:

* the named set, its two sentences word for word and its rule id;
* what the door admits of the three and what it refuses, beside its older findings;
* that the default it admits is one value for both frameworks, and that the registry answers
  that default for POL-240 and POL-029 whatever the book;
* the product's own assembly: a value of the three stands in the bundle at OBLIGATION scope,
  level P, and the read each engine reader makes — the contract alone — does not meet it;
* what is not touched: every other parameter that lists level P, among them the four that
  nothing reads at any level (a stated limit and no door), and the values the legacy import
  gives a product;
* the one seeded value of the set, which leaves its industry template, and the demo
  generator's version, which moves with what the seed stores.

The four doors on the database are witnessed in ``tests/domain/reference/test_products.py`` and
``tests/domain/policies/test_templates.py``, the engine's readers in
``tests/architecture/test_level_p_readers.py`` and a run of the whole engine in
``tests/unit/answer_keys/test_level_p_row_not_read.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.contracts import bundles
from erev_api.domain.demo import seed
from erev_api.domain.imports.legacy_v1 import sku_ssp
from erev_api.domain.policies import industry
from erev_api.domain.reference import products
from erev_api.enums import BookCode, RegistryScope
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS, RegistryParameterSpec
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.state import PolicyResolver

TIER = "usage.tier_minimum_method"  # POL-240
BENEFIT = "upfront_fee.recognition_period"  # POL-029
SHIPPING = "pob.shipping_as_fulfilment"  # POL-021
RULE = "POLICY_PRODUCT_LEVEL_NOT_READ"
# The ruled words (the supervisor, 2026-10-03): lane ACCT's limits document quotes them, with
# <key> where the sentence names the parameter by its code.
DEFAULT_APPLIES = (
    "This release reads {key} from no product or template. The framework's default applies to "
    "every contract: leave it out, or state the default."
)
REGISTRY_APPLIES = (
    "This release reads {key} from no product or template. The entity's or the workspace's "
    "value applies where the framework does not fix it: set it by a policy version."
)
NOW = datetime(2026, 9, 12, 12, tzinfo=UTC)
CONTRACT = "K-01"


def refusals(values: dict[str, Any]) -> list[tuple[str | None, str | None, str]]:
    """What the door answers for ``values``: field, rule id and sentence of each error."""
    return [
        (error.field, error.rule_id, error.message)
        for error in products.policy_values_errors(values)
    ]


def not_read(code: str) -> tuple[str, str, str]:
    """The error of PRD ERR-103 for parameter ``code``: its field, the rule id and the sentence
    of the parameter, which names it."""
    sentence = REGISTRY_APPLIES if code == SHIPPING else DEFAULT_APPLIES
    return (f"policy_values.{code}", RULE, sentence.format(key=code))


def options(spec: RegistryParameterSpec) -> list[Any]:
    """Every option of an enumerated parameter; the default of any other."""
    listed = spec.value_schema.get("enum")
    return list(listed) if listed else [spec.default_asc606]


def test_the_named_set_its_sentences_and_its_rule_id() -> None:
    """Three parameters, each with the sentence that refuses it; the catalogue keeps level P for
    them and neither framework fixes all of one, so the door answers by its own name and not as
    a level the parameter does not list or a value the framework fixes."""
    assert products.RULE_LEVEL_P_NOT_READ == RULE
    assert (products.POLICY_NOT_READ_DEFAULT, products.POLICY_NOT_READ_REGISTRY) == (
        DEFAULT_APPLIES,
        REGISTRY_APPLIES,
    )
    assert dict(products.LEVEL_P_NOT_READ) == {
        TIER: DEFAULT_APPLIES,
        BENEFIT: DEFAULT_APPLIES,
        SHIPPING: REGISTRY_APPLIES,
    }
    assert {code: POLICY_PARAMETERS[code].pol_id for code in products.LEVEL_P_NOT_READ} == {
        TIER: "POL-240",
        BENEFIT: "POL-029",
        SHIPPING: "POL-021",
    }
    for code in products.LEVEL_P_NOT_READ:
        spec = POLICY_PARAMETERS[code]
        assert RegistryScope.PRODUCT in spec.allowed_levels, code
        assert not (spec.is_forced_asc606 and spec.is_forced_ifrs15), code
        assert spec.pin == "K", code


@pytest.mark.parametrize(
    ("code", "default", "other"),
    [
        (TIER, "DERIVED", "ESTIMATE_MEASUREMENT_PERIOD_TP"),
        (BENEFIT, "EXPECTED_BENEFIT_PERIOD", "CONTRACT_TERM"),
    ],
    ids=["POL-240", "POL-029"],
)
def test_the_frameworks_default_alone_may_be_stated(code: str, default: str, other: str) -> None:
    """POL-240 and POL-029: the default is admitted, since it is the value every contract takes;
    every other value is refused with what applies instead — the other option, and a value
    outside the options, which is not read either and gets the door's own name. The door
    compares with ONE value: the two frameworks' defaults are equal."""
    spec = POLICY_PARAMETERS[code]
    assert (spec.default_asc606, spec.default_ifrs15) == (default, default)
    assert sorted(spec.value_schema["enum"]) == sorted([default, other])
    assert refusals({code: default}) == []
    for value in (other, "NOPE", None, 1):
        assert refusals({code: value}) == [not_read(code)], value
    assert products.level_p_read(code, default)
    assert not any(products.level_p_read(code, value) for value in (other, "NOPE", None, 1))


@pytest.mark.parametrize("value", ["TRUE", "FALSE", "NOPE"])
def test_no_value_of_the_shipping_election_may_be_stated(value: str) -> None:
    """POL-021: every value is refused, the default of each framework included — the registry
    decides it. It lists the workspace and the legal entity, where a policy version sets it, and
    IFRS 15 fixes ``FALSE``, which is why the sentence says "where the framework does not fix
    it"."""
    spec = POLICY_PARAMETERS[SHIPPING]
    assert {RegistryScope.TENANT, RegistryScope.ENTITY} <= spec.allowed_levels
    assert (spec.default_asc606, spec.default_ifrs15) == ("TRUE", "FALSE")
    assert (spec.is_forced_asc606, spec.is_forced_ifrs15) == (False, True)
    assert refusals({SHIPPING: value}) == [not_read(SHIPPING)]
    assert not products.level_p_read(SHIPPING, value)


@pytest.mark.parametrize("code", [TIER, BENEFIT], ids=["POL-240", "POL-029"])
def test_the_registry_answers_the_default_of_the_two_for_every_book(code: str) -> None:
    """The words "The framework's default applies to every contract", on the registry: neither
    parameter lists a level a registry version has (04 T-PLT-32: BOOK, ENTITY, TENANT), so
    resolution reads no version for it, and bundle assembly, which asks without a contract, reads
    no override either — the answer is the framework's default for any book, entity and instant.
    No session is used."""
    spec = POLICY_PARAMETERS[code]
    assert not spec.allowed_levels & {scope for scope, _ in registry.VERSION_LEVELS}
    for book in (BookCode.ASC606, BookCode.IFRS15, BookCode.LEGACY):
        found = registry.resolve(
            None,  # type: ignore[arg-type]  # no level of the parameter reads a table
            code,
            book_code=book,
            entity_id=UUID(int=0xE1),
            known_at=NOW,
        )
        assert (found.value, found.level, found.source_id) == (spec.default_asc606, "DEFAULT", None)


def test_the_door_stands_beside_its_older_findings() -> None:
    """One error a key, in key order: the new branch names its own values and leaves every other
    finding of the check as it was. A stated default of the set and a value another parameter
    admits raise nothing."""
    found = refusals(
        {
            "no.such": 1,
            "pob.principal_or_agent": "AGENT",
            "rounding.posting_mode": "HALF_UP",
            "ssp.method_hierarchy": "legacy_range",
            "material_right.ssp_method": "NOPE",
            "returns.model": "EXPECTED_RETURNS",
            SHIPPING: "TRUE",
            TIER: "ESTIMATE_MEASUREMENT_PERIOD_TP",
            BENEFIT: "EXPECTED_BENEFIT_PERIOD",
        }
    )
    assert [(field, rule) for field, rule, _ in found] == [
        ("policy_values.material_right.ssp_method", "POLICY_VALUE_INVALID"),
        ("policy_values.no.such", "POLICY_VALUE_INVALID"),
        ("policy_values.pob.principal_or_agent", "REQ-REF-012"),
        (f"policy_values.{SHIPPING}", RULE),
        ("policy_values.rounding.posting_mode", "POLICY_LEVEL_NOT_ALLOWED"),
        ("policy_values.ssp.method_hierarchy", "POLICY_VALUE_INVALID"),
        (f"policy_values.{TIER}", RULE),
    ]
    # each sentence names its parameter by the code, as the field has it after ``policy_values.``
    assert [message for _, rule, message in found if rule == RULE] == [
        "This release reads pob.shipping_as_fulfilment from no product or template. The entity's "
        "or the workspace's value applies where the framework does not fix it: set it by a "
        "policy version.",
        "This release reads usage.tier_minimum_method from no product or template. The "
        "framework's default applies to every contract: leave it out, or state the default.",
    ]
    assert [error for error in found if error[1] == RULE] == [not_read(SHIPPING), not_read(TIER)]


def test_every_other_parameter_that_lists_level_p_is_stated_as_before() -> None:
    """The door is for the three alone. Of the 131 parameters 23 list level P: the three of the
    set; POL-030, the product's conclusion, by approval; POL-074 and POL-146, which both
    frameworks fix; and seventeen of which the check admits every option. Four of the seventeen
    are read by nothing at any level (POL-015, POL-026, POL-142, POL-231): a stated limit of the
    release and no door, so the values the legacy import gives a product stand."""
    listed = {
        str(spec.pol_id): spec
        for spec in POLICY_PARAMETERS.values()
        if RegistryScope.PRODUCT in spec.allowed_levels
    }
    assert (len(POLICY_PARAMETERS), len(listed)) == (131, 23)
    answers: dict[str, set[str | None]] = {
        pol_id: {rule for value in options(spec) for _, rule, _ in refusals({spec.code: value})}
        for pol_id, spec in listed.items()
    }
    refused = {pol_id: rules for pol_id, rules in answers.items() if rules}
    assert refused == {
        "POL-021": {RULE},
        "POL-029": {RULE},
        "POL-240": {RULE},
        "POL-030": {"REQ-REF-012"},
        "POL-074": {"POLICY_VALUE_INVALID"},
        "POL-146": {"POLICY_VALUE_INVALID"},
    }
    admitted = sorted(pol_id for pol_id, rules in answers.items() if not rules)
    assert admitted == [
        "POL-015",
        "POL-026",
        "POL-051",
        "POL-053",
        "POL-055",
        "POL-071",
        "POL-072",
        "POL-090",
        "POL-091",
        "POL-095",
        "POL-122",
        "POL-140",
        "POL-141",
        "POL-142",
        "POL-143",
        "POL-231",
        "POL-241",
    ]
    # of the two whose default applies, the default is the one option the check admits
    assert {value for value in options(listed["POL-240"]) if not refusals({TIER: value})} == {
        "DERIVED"
    }
    assert {value for value in options(listed["POL-029"]) if not refusals({BENEFIT: value})} == {
        "EXPECTED_BENEFIT_PERIOD"
    }


def test_the_values_the_legacy_import_gives_a_product_pass() -> None:
    """Beside the door the legacy SKU import and the migration's prerequisites give every product
    they create ``product_parity_values()``. It holds no parameter of the set, and the check
    admits it whole — POL-026 and POL-231 among its members."""
    values = sku_ssp.product_parity_values()
    assert not set(values) & {TIER, BENEFIT, SHIPPING}
    assert {"material_right.ssp_method", "scope.lessor_combination_expedient"} <= set(values)
    assert refusals(values) == []


def test_the_assembly_states_level_p_for_an_obligation_and_a_read_for_the_contract_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Why the three are in the set, on the product's own assembly (``bundles._policies``; 05
    RCP-15): a product's value and its template's — which wins where both state the key — become
    ONE row for the line's obligation, scope ``OBLIGATION``, level ``P``, beside the registry's
    ``GROUP`` row. The engine's resolver hands that row to a read that names the obligation and
    never to a read that names the contract alone, which is what each reader of the three makes
    (``tests/architecture/test_level_p_readers.py``). The registry is a stub that answers the
    framework's default; no session is used."""
    stated = {TIER: "ESTIMATE_MEASUREMENT_PERIOD_TP", BENEFIT: "CONTRACT_TERM", SHIPPING: "FALSE"}

    def of_the_framework(
        _session: object, code: str, *, book_code: BookCode, **_scope: object
    ) -> registry.ResolvedValue:
        return registry.framework_default(registry.parameter(code), book_code)

    monkeypatch.setattr(bundles.registry, "resolve", of_the_framework)
    rows = bundles._policies(
        None,  # type: ignore[arg-type]  # the registry is the stub above
        book_code="ASC606",
        entity_id=None,
        entities=(),
        known_at=NOW,
        pinned=None,
        lines=((CONTRACT, {"product_code": "P-1", "obligation_key": "L1"}),),
        product_rows={"P-1": {"policy_values": {SHIPPING: stated[SHIPPING], TIER: "DERIVED"}}},
        template_values={
            "P-1": {
                "version_key": "TPL-1@v1",
                "policy_values": {TIER: stated[TIER], BENEFIT: stated[BENEFIT]},
                "ratable_convention": None,
            }
        },
    )
    subject = obligation_subject_key(CONTRACT, "L1")
    of_the_set = [
        (row.code, row.scope, row.subject_key, row.value, row.level)
        for row in rows
        if row.code in stated
    ]
    assert of_the_set == [
        (SHIPPING, "GROUP", "", "TRUE", "DEFAULT"),
        (SHIPPING, "OBLIGATION", subject, "FALSE", "P"),
        (BENEFIT, "GROUP", "", "EXPECTED_BENEFIT_PERIOD", "DEFAULT"),
        (BENEFIT, "OBLIGATION", subject, "CONTRACT_TERM", "P"),
        (TIER, "GROUP", "", "DERIVED", "DEFAULT"),
        (TIER, "OBLIGATION", subject, "ESTIMATE_MEASUREMENT_PERIOD_TP", "P"),
    ]
    resolver = PolicyResolver(rows)
    for code, value in stated.items():
        for_the_contract = resolver.resolved(code, contract=CONTRACT)
        assert (for_the_contract.scope, for_the_contract.level) == ("GROUP", "DEFAULT"), code
        assert for_the_contract.value != value, code
        for_the_obligation = resolver.resolved(code, contract=CONTRACT, obligation=subject)
        assert (for_the_obligation.scope, for_the_obligation.level, for_the_obligation.value) == (
            "OBLIGATION",
            "P",
            value,
        ), code


def test_no_industry_template_states_a_value_the_door_refuses() -> None:
    """The demo seed creates each cluster's templates by the template command, so through the
    door (``demo.industry.reference``). ``IND-D05-FRANCHISE-RIGHT`` stated POL-029
    ``CONTRACT_TERM`` — the one seeded value of the set that was not the default. It leaves and
    is not replaced by the default; the usage template of the software cluster keeps stating
    POL-240's default, which the door admits."""
    stated = {
        template.code: dict(template.outputs.get("policy_values", {}))
        for cluster in industry.CLUSTERS.values()
        for template in cluster.templates
    }
    assert (len(industry.CLUSTERS), len(stated)) == (6, 31)
    for code, values in stated.items():
        assert refusals(values) == [], code
    assert "policy_values" not in industry.cluster_of("D05").templates[-1].outputs
    assert industry.cluster_of("D05").templates[-1].code == "IND-D05-FRANCHISE-RIGHT"
    assert {
        code: values for code, values in stated.items() if set(values) & {TIER, BENEFIT, SHIPPING}
    } == {"IND-D01-USAGE-OVERAGE": {TIER: "DERIVED"}}


def test_the_demo_generator_moves_with_what_the_seed_stores() -> None:
    """Version 13 persists loss tests; the draft template of WLD-T-05 no longer holds the
    POL-029 value, so a workspace seeded at 9 is not the one this generator builds — it is
    refused by name and seeded again."""
    assert seed.GENERATOR_VERSION == 13
    earlier = seed._DirectoryEntry(tenant_id=UUID(int=0x7E), is_demo=True, generator_version=9)
    assert seed._refusal("juniper-street", earlier) == (
        "Refusing to seed juniper-street: generator version 9 built it; run make seed RESET=1"
    )
    current = seed._DirectoryEntry(tenant_id=UUID(int=0x7E), is_demo=True, generator_version=13)
    assert seed._refusal("juniper-street", current) is None
