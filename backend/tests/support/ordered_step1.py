"""Original bundles with ordered monetary and eligibility events."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import allocation_worlds, cpc_worlds
from support import step1_worlds as worlds

JAN = date(2026, 1, 1)
EXIT = date(2026, 2, 10)


def bundle_at_exit(kind, *, after, reenter=False):
    bundle = worlds.time_world(
        paid=None,
        steps=[("C", JAN, "")],
        template_changes={"recognition_method": "USAGE"} if kind == "usage" else {},
    )
    events = list(bundle.events)
    estimates = []
    if kind == "estimate":
        initial = replace(
            allocation_worlds.untargeted_element(),
            estimate_key="C-STEP1/BASE",
            version_key="C-STEP1/BASE@v1",
        )
        estimates = [initial, allocation_worlds.later_version(initial, 2, EXIT, "60")]
        events = cpc_worlds.pinned(events, initial)
    amendments = []
    events = worlds.significant_change(events, EXIT, "Customer deterioration")
    if after:
        events = worlds.not_probable(events, EXIT)
    if kind == "usage":
        events = cpc_worlds.then(
            events,
            "USAGE_REPORTED",
            EXIT,
            {
                "obligation_key": worlds.SERVICE,
                "usage_period_start": date(2026, 2, 1),
                "usage_period_end": EXIT,
                "metric": "CALLS",
                "quantity": Decimal(10),
                "rated_amount": Decimal(60),
            },
        )
    elif kind == "estimate":
        events = cpc_worlds.pinned(events, estimates[1])
    elif kind == "amendment":
        amendment = cpc_worlds.concession("120", EXIT, key=worlds.SERVICE)
        amendment = replace(
            amendment,
            price_change_amount=None,
            lines=tuple({**line, "product_code": "SERVICE"} for line in amendment.lines),
        )
        amendments.append(amendment)
        events = cpc_worlds.amended(events, amendment)
    if not after:
        events = worlds.not_probable(events, EXIT)
    if reenter:
        events = worlds.criteria_met(events, EXIT)
    return replace(
        bundle,
        events=tuple(events),
        estimate_versions=tuple(estimates),
        contracts=(replace(bundle.contracts[0], modifications=tuple(amendments)),),
        known_at=max(bundle.known_at, *(event.recorded_at for event in events)),
    )
