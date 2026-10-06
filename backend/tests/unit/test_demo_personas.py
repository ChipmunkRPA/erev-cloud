"""PRD §2.3 WLD-U-R2 (rev 1.153; supervisor ruling R-83 (f), item DEMO-MFA-PREPARER-1): whom the
demo seed enrols in a TOTP factor."""

from __future__ import annotations

from erev_api.auth.permissions import spec
from erev_api.domain.demo import personas


def _permissions(persona: personas.Persona, group: personas.TenantGroup) -> set[str]:
    return {
        permission
        for code in persona.roles_in(group)
        for permission in personas.role_permissions(code)
    }


def test_wld_u_r2_the_seed_enrols_the_mfa_holders_and_the_persona_who_signs_off() -> None:
    """A holder of a ``requires_mfa`` permission is enrolled, and so is ``maya``: none of her
    permissions requires a factor, but she prepares the reconciliations of J-13 and a sign-off
    needs an MFA-verified session whatever the permission's flag (04 T-CLS-08). She is named, not
    derived from a permission; nobody else is enrolled."""
    by_key = {persona.key: persona for persona in personas.PERSONAS}
    enrolled = {key for key, persona in by_key.items() if personas.needs_mfa(persona, "journey")}
    assert enrolled == {"maya", "priya", "marcus", "elena", "tomas", "grace", "nikhil"}
    assert personas.SIGN_OFF_PERSONAS == {"maya"}

    maya = by_key["maya"]
    held = _permissions(maya, "journey")
    assert "recon.prepare" in held
    assert not any(spec(permission).requires_mfa for permission in held)
    # One identity, one factor: she is enrolled in whichever workspace of a run she joins first.
    assert all(personas.needs_mfa(maya, group) for group in personas.GROUPS)

    for key in sorted(enrolled - personas.SIGN_OFF_PERSONAS):
        assert any(
            spec(permission).requires_mfa for permission in _permissions(by_key[key], "journey")
        )
