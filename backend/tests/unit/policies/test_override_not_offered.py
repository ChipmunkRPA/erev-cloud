"""What decides a parameter where no policy override is offered, without a database (item
POLICY-OVERRIDE-WITHDRAW-1, register index 308; supervisor ruling R-126 (b) (4) and (c); 04
T-CON-23 "Not offered in release 1.0" rev 1.322; POLICIES §0.5 rule 5 and table 0.5-A rev 1.124;
PRD ERR-102; dev-guide DG-KRN-REG-06 rev 1.298; BUILD_SPEC CTR-15).

``POST /policy-overrides`` refuses every creation in release 1.0 with two sentences:
``overrides.NOT_OFFERED`` and ``overrides.decided_instead(policy_key)``. This module pins the
second one over the whole registry catalogue:

* every parameter has one sentence, and a key the catalogue does not hold is told so;
* the parameters that list level CONTRACT or OBLIGATION — the only ones a row could be stored for
  — are exactly the 23 of ``overrides.DECIDED_BY``, whose sentences were read one by one against
  the code that takes the parameter. A parameter that gains or loses one of the two levels fails
  here until its sentence is read and restated;
* no sentence names a level the catalogue does not allow for its parameter, and a parameter that
  lists neither level is told the catalogue and no more;
* the 23 sentences are word for word those of POLICIES §0.5 table 0.5-A, the document the
  refusal's copy row (PRD ERR-102) points to.

The refusal itself — its status, type, field and rule id, that it comes after the 404 and the
403 and before any validation, and that nothing is stored — is witnessed through the product in
``tests/domain/policies/test_policy_overrides.py``.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from erev_api.domain.policies import overrides
from erev_api.enums import RegistryScope
from erev_api.registry import resolve as registry

POLICIES = Path(__file__).resolve().parents[4] / "docs" / "accounting" / "POLICIES.md"
OVERRIDE_LEVELS = frozenset({RegistryScope.CONTRACT, RegistryScope.OBLIGATION})
# The words by which a sentence names a level, and the level each must be allowed at.
WORKSPACE = "policy registry for the workspace"
ENTITY = "policy registry for a legal entity"
PRODUCT = "on the product or on its obligation template"
DEFAULT = "The framework's default applies to every contract in this release."
ROW = re.compile(r"^\| `([a-z0-9_.]+)` \| (POL-\d{3}) \| (.+) \|$")
# The six that neither a record nor another level decides: lane ACCT's document of stated limits
# names them. Five list level CONTRACT alone; POL-240 lists PRODUCT as well, where the engine does
# not read it (register index 309).
DEFAULT_DECIDES = frozenset(
    {
        "concession.allocation_basis",
        "cpc.incentive_asset_release_basis",
        "royalty.minimum_guarantee",
        "royalty.unreported_sales",
        "sfc.discount_rate_basis",
        "usage.tier_minimum_method",
    }
)


def listed_at_an_override_level() -> set[str]:
    return {
        key for key, spec in registry.PARAMETERS.items() if spec.allowed_levels & OVERRIDE_LEVELS
    }


def forced_in_both_books(key: str) -> bool:
    spec = registry.PARAMETERS[key]
    return bool(spec.is_forced_asc606 and spec.is_forced_ifrs15)


def catalogue_sentence(key: str) -> str:
    """What a parameter that lists neither override level is told, spelled out here from the
    catalogue: fixed, or its levels in the order workspace, legal entity, book, product."""
    spec = registry.PARAMETERS[key]
    if forced_in_both_books(key):
        return "The framework fixes this value."
    names = [
        name
        for level, name in (
            (RegistryScope.TENANT, "workspace"),
            (RegistryScope.ENTITY, "legal entity"),
            (RegistryScope.BOOK, "book"),
            (RegistryScope.PRODUCT, "product"),
        )
        if level in spec.allowed_levels
    ]
    if not names:
        return "It can be set at no level of the policy registry."
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"
    return f"It can be set only at {listed} level."


def table_rows() -> dict[str, tuple[str, str]]:
    """Key → (POL id, sentence) of POLICIES §0.5 table 0.5-A."""
    text = POLICIES.read_text(encoding="utf-8")
    start = text.index("**Table 0.5-A. ")
    section = text[start : text.index("\n### 0.6 Approval codes", start)]
    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        found = ROW.match(line)
        if found is not None:
            assert found.group(1) not in rows, line
            rows[found.group(1)] = (found.group(2), found.group(3))
    return rows


def test_each_parameter_of_the_catalogue_has_one_sentence() -> None:
    assert len(registry.PARAMETERS) == 155
    for key in registry.PARAMETERS:
        sentence = overrides.decided_instead(key)
        assert sentence[:1].isupper() and sentence.endswith("."), key
        assert ". " not in sentence and "\n" not in sentence, key  # one sentence, on one line
    unknown = overrides.decided_instead("returns.no_such_parameter")
    assert unknown == "The policy registry holds no parameter of this key."
    assert unknown not in {overrides.decided_instead(key) for key in registry.PARAMETERS}
    # The first sentence, once, as PRD ERR-102 has it.
    assert overrides.NOT_OFFERED == (
        "Policy overrides for a contract or an obligation are not offered in this release."
    )
    assert overrides.RULE_NOT_OFFERED == "POLICY_OVERRIDE_NOT_OFFERED"


def test_the_parameters_that_list_level_c_or_o_are_the_23_with_a_read_sentence() -> None:
    listed = listed_at_an_override_level()
    assert len(listed) == 23
    assert listed == set(overrides.DECIDED_BY), sorted(listed ^ set(overrides.DECIDED_BY))
    for key in listed:
        assert overrides.decided_instead(key) == overrides.DECIDED_BY[key], key
    # The kinds of POLICIES §0.5 rule 5 by what each sentence says: 9, 8 and 6.
    default = {key for key in listed if overrides.DECIDED_BY[key].startswith("The framework's ")}
    level = {
        key
        for key in listed - default
        if overrides.DECIDED_BY[key]
        in (
            f"It is set in the {WORKSPACE}.",
            f"It is set in the {ENTITY}.",
            f"It is set {PRODUCT}.",
        )
    }
    assert default == DEFAULT_DECIDES
    assert (len(listed - default - level), len(level), len(default)) == (9, 8, 6)
    # A parameter the default decides is not forced (a forced one says so), has a default in both
    # books, and — POL-240 apart — lists level CONTRACT alone.
    for key in default:
        spec = registry.PARAMETERS[key]
        assert not forced_in_both_books(key), key
        assert spec.default_asc606 is not None and spec.default_ifrs15 is not None, key
        if key == "sfc.discount_rate_basis":
            assert overrides.DECIDED_BY[key] == (
                "The framework's default basis applies to every contract in this release, and "
                "no discount rate can be given: a contract whose financing needs an adjustment "
                "is not computed (SFC_RATE_MISSING)."
            )
            assert "annual_rate" not in spec.default_asc606  # a basis and no rate
            continue
        assert overrides.DECIDED_BY[key] == DEFAULT, key
        expected = (
            {RegistryScope.CONTRACT, RegistryScope.PRODUCT}
            if key == "usage.tier_minimum_method"
            else {RegistryScope.CONTRACT}
        )
        assert set(spec.allowed_levels) == expected, key


def test_no_sentence_names_a_level_the_catalogue_does_not_allow() -> None:
    forms: Counter[str] = Counter()
    for key, spec in registry.PARAMETERS.items():
        sentence = overrides.decided_instead(key)
        if key not in overrides.DECIDED_BY:
            # Neither override level is listed: the catalogue's own statement, and no more.
            assert sentence == catalogue_sentence(key), key
            forms[sentence if "fixes" in sentence or "no level" in sentence else "levels"] += 1
            continue
        named = {
            RegistryScope.TENANT: WORKSPACE in sentence,
            RegistryScope.ENTITY: ENTITY in sentence,
            RegistryScope.PRODUCT: PRODUCT in sentence,
        }
        for scope, is_named in named.items():
            assert not is_named or scope in spec.allowed_levels, (key, scope)
        assert sentence.startswith("The framework fixes ") == forced_in_both_books(key), key
        assert "CONTRACT" not in sentence and "OBLIGATION" not in sentence, key
    # The 132 parameters that list neither level, by what the catalogue says of them.
    assert forms == Counter(
        {
            "levels": 94,
            "The framework fixes this value.": 33,
            "It can be set at no level of the policy registry.": 5,
        }
    )
    assert overrides.decided_instead("pob.shipping_as_fulfilment") == (
        "It can be set only at workspace, legal entity or product level."
    )
    assert overrides.decided_instead("returns.reversal_rate") == (
        "It can be set only at workspace level."
    )


def test_the_23_sentences_are_word_for_word_those_of_policies_table_0_5_a() -> None:
    rows = table_rows()
    assert {key: sentence for key, (_, sentence) in rows.items()} == dict(overrides.DECIDED_BY)
    for key, (pol_id, _) in rows.items():
        assert registry.PARAMETERS[key].pol_id == pol_id, key
    # The table is in POL order, as the register it points to.
    assert [pol_id for pol_id, _ in rows.values()] == sorted(pol_id for pol_id, _ in rows.values())
