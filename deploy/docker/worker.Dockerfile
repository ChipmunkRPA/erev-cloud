# syntax=docker/dockerfile:1
# Worker image (docs/05-ARCHITECTURE.md §8.1 DPL-02, DPL-05; SAR-33; DG-KRN-JOB-08, DG-KRN-JOB-11).
# Build from the repository root: `docker build -f deploy/docker/worker.Dockerfile .`. The build stage
# equals api.Dockerfile's byte for byte, so both images reuse its layers. The worker consumes all eight
# queues (no --queues) and its health check reads the heartbeat file worker.heartbeat in EREV_RUN_DIR
# (default /app/.run; compose sets /tmp/erev on the container's tmpfs, DPL-14).

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --extra gcp --no-install-project
COPY backend/alembic.ini ./
COPY backend/erev_api ./erev_api
COPY backend/erev_engine ./erev_engine
RUN uv sync --frozen --no-dev --extra gcp

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EREV_ENV=production
COPY --from=build /app /app
# 05 REL-03: a production process refuses to start without release-manifest.json, so the image carries
# the one at the root of its build context (`make docker-build` places the embedded manifest in the context
# it exports, DPL-05; for a build from the working tree `make release-manifest EMBEDDED=1` writes it) at
# /app/release-manifest.json (erev_api.controls.release MANIFEST_PATH), root-owned and read-only to uid 10001.
COPY release-manifest.json /app/release-manifest.json
# SAR-33: uid and gid 10001, writable run and file directories, and no shell after this step.
# /data/files is the mount point of compose volume erev-files (DPL-14); a new named volume copies
# its ownership, so uid 10001 can write there.
# Rev 1.53 (ruling R-37 (b)): before the shells go, the base interpreter loses its pip (package,
# metadata, launchers) and ensurepip — the virtual environment never had one, so nothing can be
# installed into a running container — and every regular file loses its setuid and setgid bits
# (su, mount, passwd and their like in the Debian base). `make docker-build` probes the built image
# for both and fails on a finding (DPL-05).
RUN groupadd --system --gid 10001 erev \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --no-create-home --shell /usr/sbin/nologin erev \
    && mkdir -p /app/.run /app/.data/files /data/files \
    && chown -R 10001:10001 /app/.run /app/.data /data \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/lib/python3.12/site-packages/pip-*.dist-info /usr/local/lib/python3.12/ensurepip \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 \
    && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
    && rm -f /usr/bin/sh /usr/bin/dash /usr/bin/bash /usr/bin/rbash
WORKDIR /app
USER 10001
ENTRYPOINT ["/app/.venv/bin/erev"]
CMD ["worker"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["/app/.venv/bin/erev", "worker", "--check"]
