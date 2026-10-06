"""The worker's probe listener (05 OPR-23 rev 1.28; DPL-31; CFG-32; matrix G17).

A hosted worker is a Cloud Run service and must answer on ``$PORT``: ``GET`` / ``HEAD /startupz``
returns 200 once the process is ready to consume (the runtime built, the KEY-03 current key
verified, the DG-KRN-AUD-08 admission passed) and 503 before; ``GET`` / ``HEAD /livez`` returns
200 while the heartbeat file is fresh (the ``erev worker --check`` rule) and 503 otherwise; any
other path is 404. Bodies carry status only — never a version, key id, tenant or environment
detail. No per-request logging (OPR-21): one ``worker_probes.listening`` and one
``worker_probes.stopped`` line. The listener opens only when a port is configured
(``EREV_WORKER_PROBE_PORT`` or ``PORT``); ``make worker`` and the pid-file runbook open none.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final

from erev_api.logging import get_logger, register_logger_fields

STARTUP_PATH: Final = "/startupz"
LIVENESS_PATH: Final = "/livez"
CONTAINER_HOST: Final = "0.0.0.0"  # noqa: S104 — DPL-31: ingress internal only
_LOGGER: Final = "erev_api.jobs.probes"
register_logger_fields(_LOGGER, ("host", "port"))


def _body(status: str) -> bytes:
    return json.dumps({"status": status}).encode("utf-8")


class ProbeServer:
    """A stdlib threading HTTP server on a daemon thread answering the two probe paths."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        ready: Callable[[], bool],
        live: Callable[[], bool],
    ) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "erev-worker"  # no python version banner
            sys_version = ""

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return  # OPR-21: no per-request logging

            def _answer(self, *, with_body: bool) -> None:
                if self.path == STARTUP_PATH:
                    ok = outer._ready()
                    status, text = (
                        (HTTPStatus.OK, "ok")
                        if ok
                        else (HTTPStatus.SERVICE_UNAVAILABLE, "starting")
                    )
                elif self.path == LIVENESS_PATH:
                    ok = outer._live()
                    status, text = (
                        (HTTPStatus.OK, "ok") if ok else (HTTPStatus.SERVICE_UNAVAILABLE, "stale")
                    )
                else:
                    status, text = HTTPStatus.NOT_FOUND, "not_found"
                payload = _body(text)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if with_body:
                    self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                self._answer(with_body=True)

            def do_HEAD(self) -> None:  # noqa: N802
                self._answer(with_body=False)

        self._ready = ready
        self._live = live
        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="erev-worker-probes", daemon=True
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()
        get_logger(_LOGGER).info(
            "worker_probes.listening", host=self._server.server_address[0], port=self.port
        )

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        get_logger(_LOGGER).info("worker_probes.stopped", port=self.port)


def probe_server_if_configured(
    port: int | None,
    *,
    ready: Callable[[], bool],
    live: Callable[[], bool],
    host: str = CONTAINER_HOST,
) -> ProbeServer | None:
    """CFG-32: a listener only when a port is configured; None keeps pid-file mode unchanged."""
    if port is None:
        return None
    return ProbeServer(host=host, port=port, ready=ready, live=live)
