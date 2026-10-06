"""Workbench latency and the endpoint mix (dev-guide DG-PERF-03, DG-PERF-04; 05 PERF-02, PERF-30).

Pure parts (unit-tested): nearest-rank percentiles, deterministic contract sampling with
stratification by obligation count, the PERF-30 mix, the request-log parser. Measured parts
(``measure_endpoint``, ``replay_mix``) drive httpx clients and are NOT RUN in the lane."""

from __future__ import annotations

import json
import random
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Final

SAMPLE_SEED: Final = 20260912
WARM_UP: Final = 20
MEASURED: Final = 200
CLIENTS: Final = 4
P95_LIMIT_MS: Final = 300.0
MIX_REQUESTS: Final = 2_000
MIX_CONCURRENCY: Final = 8
MIX_CONTRACTS: Final = 200

# DG-PERF-03: the seven endpoints (name → path template; {id} is a sampled contract id).
ENDPOINTS: Final[Mapping[str, str]] = {
    "contract": "/contracts/{id}",
    "obligations": "/contracts/{id}/obligations",
    "schedule": "/contracts/{id}/schedule",
    "balances": "/contracts/{id}/balances",
    "allocation": "/contracts/{id}/allocation",
    "history": "/contracts/{id}/history",
    "list": "/contracts?limit=50",
}
# 05 PERF-30: family → (path template, weight in percent).
MIX: Final[Mapping[str, tuple[str, int]]] = {
    "contract_list": ("/contracts?limit=50", 25),
    "contract_header": ("/contracts/{id}", 20),
    "obligations": ("/contracts/{id}/obligations", 15),
    "schedule": ("/contracts/{id}/schedule", 10),
    "balances": ("/contracts/{id}/balances", 10),
    "events": ("/contracts/{id}/events", 10),
    "subledger_lines": ("/contracts/{id}/subledger-lines", 5),
    "explain": ("/contracts/{id}/allocation", 5),  # one measure explained from the allocation view
}


def nearest_rank(samples: Sequence[float], percentile: float) -> float:
    """Nearest-rank percentile: the value at rank ceil(p × n) of the sorted samples."""
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    rank = max(1, -(-int(percentile * 100) * len(ordered) // 100))  # ceil(p × n) without floats
    return ordered[min(rank, len(ordered)) - 1]


def p95(samples: Sequence[float]) -> float:
    return nearest_rank(samples, 0.95)


def sample_ids(ids: Sequence[str], count: int, seed: int = SAMPLE_SEED) -> list[str]:
    """``count`` contract ids drawn without replacement with ``seed`` (fewer when fewer exist)."""
    rng = random.Random(seed)
    pool = list(ids)
    return rng.sample(pool, min(count, len(pool)))


def stratified_sample(
    contracts: Sequence[tuple[str, int]], count: int, seed: int = SAMPLE_SEED
) -> list[str]:
    """``count`` contract ids stratified by obligation count (DG-PERF-04): each obligation-count
    bucket contributes in proportion to its size (largest remainder), drawn with ``seed``."""
    if count <= 0 or not contracts:
        return []
    rng = random.Random(seed)
    buckets: dict[int, list[str]] = {}
    for contract_id, obligations in contracts:
        buckets.setdefault(obligations, []).append(contract_id)
    total = len(contracts)
    count = min(count, total)
    exact = {k: count * len(v) / total for k, v in buckets.items()}
    quotas = {k: int(value) for k, value in exact.items()}
    remainder = count - sum(quotas.values())
    for key in sorted(buckets, key=lambda k: (exact[k] - quotas[k], -k), reverse=True)[:remainder]:
        quotas[key] += 1
    chosen: list[str] = []
    for key in sorted(buckets):
        chosen.extend(rng.sample(sorted(buckets[key]), min(quotas[key], len(buckets[key]))))
    return chosen


def mix_plan(
    families: Mapping[str, tuple[str, int]], requests: int, seed: int = SAMPLE_SEED
) -> list[str]:
    """``requests`` family names in the PERF-30 proportions (largest remainder), shuffled."""
    weights = {name: weight for name, (_, weight) in families.items()}
    total = sum(weights.values())
    exact = {name: requests * weight / total for name, weight in weights.items()}
    counts = {name: int(value) for name, value in exact.items()}
    for name in sorted(weights, key=lambda n: (exact[n] - counts[n], n), reverse=True)[
        : requests - sum(counts.values())
    ]:
        counts[name] += 1
    plan = [name for name, n in counts.items() for _ in range(n)]
    random.Random(seed).shuffle(plan)
    return plan


@dataclass(frozen=True, slots=True)
class LoggedRequest:
    route: str
    method: str
    status: int | None
    duration_ms: float


def parse_request_log(lines: Iterable[str]) -> list[LoggedRequest]:
    """The ``http.request`` events of ``.run/api-perf.log`` (JSON lines; ``route`` is the route
    template, ``duration_ms`` the server time)."""
    out: list[LoggedRequest] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "http.request" or "duration_ms" not in event:
            continue
        out.append(
            LoggedRequest(
                route=str(event.get("route", "")),
                method=str(event.get("method", "")),
                status=event.get("status"),
                duration_ms=float(event["duration_ms"]),
            )
        )
    return out


def summarise(samples: Sequence[float]) -> dict[str, float]:
    return {
        "count": float(len(samples)),
        "p50": nearest_rank(samples, 0.50),
        "p95": p95(samples),
        "p99": nearest_rank(samples, 0.99),
    }


# --- measured (NOT RUN in the lane) ---------------------------------------------------------------

ClientFactory = Callable[[], Any]  # a signed-in PerfClient per thread


@dataclass
class Measurement:
    endpoint: str
    samples_ms: list[float] = field(default_factory=list)
    failures: int = 0

    @property
    def p95_ms(self) -> float:
        return p95(self.samples_ms)


def measure_endpoint(
    client_factory: ClientFactory,
    path_template: str,
    contract_ids: Sequence[str],
    *,
    endpoint: str,
    warm_up: int = WARM_UP,
    measured: int = MEASURED,
    clients: int = CLIENTS,
) -> Measurement:
    """DG-PERF-03: ``warm_up`` requests, then ``measured`` requests from ``clients`` concurrent
    httpx clients over the sampled ids; wall time per request in milliseconds."""
    result = Measurement(endpoint)
    lock = threading.Lock()
    local = threading.local()

    def client() -> Any:
        if not hasattr(local, "client"):
            local.client = client_factory()
        return local.client

    def one(index: int, record: bool) -> None:
        path = path_template.replace("{id}", contract_ids[index % len(contract_ids)])
        started = perf_counter()
        response = client().get_response(path)
        elapsed = (perf_counter() - started) * 1000.0
        if record:
            with lock:
                if response.status_code >= 400:
                    result.failures += 1
                else:
                    result.samples_ms.append(elapsed)

    with ThreadPoolExecutor(max_workers=clients) as pool:
        list(pool.map(lambda i: one(i, False), range(warm_up)))
        list(pool.map(lambda i: one(i, True), range(measured)))
    return result


def replay_mix(
    client_factory: ClientFactory,
    contract_ids: Sequence[str],
    *,
    requests: int = MIX_REQUESTS,
    concurrency: int = MIX_CONCURRENCY,
    seed: int = SAMPLE_SEED,
) -> dict[str, int]:
    """DG-PERF-04: ``requests`` requests over the PERF-30 mix with ``concurrency`` clients; returns
    the requests sent per family (the server-side timing is read from the api-perf log)."""
    plan = mix_plan(MIX, requests, seed)
    rng = random.Random(seed)
    local = threading.local()

    def client() -> Any:
        if not hasattr(local, "client"):
            local.client = client_factory()
        return local.client

    def one(family: str) -> None:
        path = MIX[family][0].replace("{id}", rng.choice(list(contract_ids)))
        client().get_response(path)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, plan))
    counts: dict[str, int] = {}
    for family in plan:
        counts[family] = counts.get(family, 0) + 1
    return counts
