"""Legal entities (04 T-REF-01, API-R-17; 03 REQ-REF-001; PRD §2.5; SCREENS_B SF-15:entities;
BUILD_SPEC RFD-2).

Pure rules and copy; the reference commands create and change entities. An entity names its
functional currency (T-REF-08), the IANA time zone in which its business dates are read (05 TZ-02,
TZ-03) and its fiscal calendar. ``functional_currency`` and ``time_zone`` freeze once a posting of
the entity exists; CTR-3 adds that DB-05 trigger with ``subledger_line`` (BS3-D-07).
"""

from __future__ import annotations

import re
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from erev_api.problems import ProblemError

RULE_ENTITY: Final = "T-REF-01"
# TY ``erev.tz_name``, checked before the zone database is consulted.
TZ_NAME: Final = re.compile(r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$")
COUNTRY_CODE: Final = re.compile(r"^[A-Z]{2}$")
CODE_TAKEN: Final = "Another entity already uses this code."
CURRENCY_UNKNOWN: Final = "Use the ISO 4217 code of an active currency, such as USD."
TIME_ZONE_UNKNOWN: Final = "Use an IANA time zone, such as America/New_York."
CALENDAR_UNKNOWN: Final = "Choose an existing calendar."
CALENDAR_EMPTY: Final = (
    "Generate a fiscal year of this calendar first: the entity's books start in one of its periods."
)
PARENT_UNKNOWN: Final = "Choose an existing entity as the parent."
PARENT_CYCLE: Final = "An entity cannot report to itself or to an entity below it."
COUNTRY_FORMAT: Final = "Use an ISO 3166-1 alpha-2 country code, such as US."


def time_zone_errors(value: str) -> list[ProblemError]:
    """The name is an IANA zone of the zone database (05 TZ-03)."""
    if TZ_NAME.fullmatch(value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
        else:
            return []
    return [ProblemError(field="time_zone", rule_id=RULE_ENTITY, message=TIME_ZONE_UNKNOWN)]


def country_code_errors(value: str | None) -> list[ProblemError]:
    """ISO 3166-1 alpha-2 in capitals, or no country."""
    if value is None or COUNTRY_CODE.fullmatch(value):
        return []
    return [ProblemError(field="country_code", rule_id=RULE_ENTITY, message=COUNTRY_FORMAT)]
