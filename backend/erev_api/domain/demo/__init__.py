"""Demo area: the PRD §2 sample world, built through the product's commands (WEB-10)."""


class SeedRefused(Exception):  # noqa: N818 - the CLI message names a refusal, not an error
    """``erev seed demo`` refuses before it writes (PRD WLD-R-04; dev-guide DG-MK-seed, DG-RUN-32).

    The message is the command's output; it names codes and rule ids, never personal data or a
    secret.
    """
