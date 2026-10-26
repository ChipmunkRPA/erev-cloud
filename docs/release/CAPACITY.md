# Capacity and sizing

## Benchmark profile, not a product quota

The performance data generator defaults to 10,000 contracts, 50,000 performance obligations and
24 months across three legal entities and USD, GBP and EUR. These values live in
`backend/erev_api/domain/demo/volume.py` and parameterize the synthetic manifest and seed.
The generator accepts explicit contract, obligation, month and scale arguments. The application
contract-creation path does not use these constants as a quota.

The profile gives the performance harness a reproducible workload. Its 24 months describe the
benchmark's event history, not a universal contract-term or retention limit. Its three entities
and currencies describe that dataset, not the number every installation may configure.

The harness measures a close window and workbench latency. Assertions such as a 600-second close
window and 300-ms endpoint p95 are test targets, not demonstrated results. No verified maximum
production contract count, annual revenue amount, transactions-per-second figure or close-time
guarantee has been established for this release.

## What determines actual capacity

Annual revenue dollars alone do not measure computational work. Obligation count, recognition
methods, event/estimate/modification history, currencies, calendars and reporting horizons determine
how much accounting state must be recomputed, traced, stored and reported. Simultaneous imports,
recomputations, close jobs and reports add competing CPU, memory, database and storage demands.

The application separates API processes from background workers, so those resources can be sized
separately. Worker concurrency and engine-process counts have configurable per-instance safety
bounds of 1–64. The GCP template also configures instance counts, database tier and connection pools.
Its database connection-budget guard reserves headroom rather than allowing workers to exhaust
the database. These controls manage resource contention; they are not tenant contract-count caps.
Adding workers alone does not guarantee higher throughput when the database or another shared
resource is saturated.

To establish a production capacity, measure a representative workload on the intended infrastructure:
record data shape, CPU/memory, database configuration, worker counts, timings, failures and resource
saturation. Increase workload until the required close and interactive response targets stop being
met. That determines a supported operating range for that deployment. A larger advertised range
requires measured results; it does not follow just from increasing a generator constant.

This document describes sizing and evidence. It performs no deployment and changes no runtime limit.
