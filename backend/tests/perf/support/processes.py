"""The harness processes (dev-guide DG-RUN-09, DG-RUN-09a, DG-PERF-05, DG-PERF-08; 05 PERF-20):
``api-perf`` on 127.0.0.1:8199 and ``perf-worker-1`` to ``perf-worker-4`` through
``scripts/proc.sh``, whose ``start`` polls the readiness check for 60 seconds and whose ``stop``
works by PID file. A failed start stops every process started so far and reports the last 40
lines of the failing process's log."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

API_NAME: Final = "api-perf"
API_PORT: Final = 8199
WORKER_COUNT: Final = 4
LOG_TAIL_LINES: Final = 40
WORKER_ENV: Final[Mapping[str, str]] = {
    "EREV_WORKER_CONCURRENCY": "2",
    "EREV_ENGINE_PROCESSES": "6",
}
PERF_ENV: Final[Mapping[str, str]] = {"EREV_ENV": "dev", "EREV_PERF_RUN": "1"}


@dataclass(frozen=True, slots=True)
class ProcessSpec:
    name: str
    port: str  # "-" binds no port (workers)
    command: tuple[str, ...]
    env: Mapping[str, str] = field(default_factory=dict)


def worker_names() -> tuple[str, ...]:
    return tuple(f"perf-worker-{n}" for n in range(1, WORKER_COUNT + 1))


def specs(root: Path, run_dir: Path, *, api_port: int = API_PORT) -> tuple[ProcessSpec, ...]:
    """api-perf first, then the four workers (DG-PERF-08)."""
    api = ProcessSpec(
        API_NAME,
        str(api_port),
        (
            str(root / "backend/.venv/bin/uvicorn"),
            "erev_api.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--no-access-log",
        ),
        PERF_ENV,
    )
    workers = tuple(
        ProcessSpec(
            name,
            "-",
            (
                str(root / "backend/.venv/bin/erev"),
                "worker",
                "--heartbeat-file",
                str(run_dir / f"{name}.heartbeat"),
            ),
            {**PERF_ENV, **WORKER_ENV},
        )
        for name in worker_names()
    )
    return (api, *workers)


class ReadinessFailed(RuntimeError):
    """A process did not become ready; carries the last 40 log lines (DG-PERF-08)."""

    def __init__(self, name: str, log_tail: str) -> None:
        super().__init__(
            f"{name} did not become ready; last {LOG_TAIL_LINES} lines of its log:\n{log_tail}"
        )
        self.name = name
        self.log_tail = log_tail


Runner = Callable[[Sequence[str], Mapping[str, str]], Any]  # returns an object with .returncode


def _default_runner(
    command: Sequence[str], env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), env=dict(env), capture_output=True, text=True, check=False)


def log_tail(run_dir: Path, name: str, lines: int = LOG_TAIL_LINES) -> str:
    path = run_dir / f"{name}.log"
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


@dataclass
class PerfStack:
    """Start and stop the five processes by PID file through ``scripts/proc.sh``."""

    root: Path
    run_dir: Path
    runner: Runner = _default_runner
    specs: tuple[ProcessSpec, ...] = ()
    started: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.specs:
            self.specs = specs(self.root, self.run_dir)

    @property
    def proc_sh(self) -> str:
        return str(self.root / "scripts" / "proc.sh")

    def _env(self, spec: ProcessSpec) -> dict[str, str]:
        return {**os.environ, "EREV_RUN_DIR": str(self.run_dir), **spec.env}

    def start_all(self) -> None:
        """Start every process in order; on the first readiness failure stop every started process
        (the failing one too, by its PID file) and raise ``ReadinessFailed``."""
        for spec in self.specs:
            result = self.runner(
                [self.proc_sh, "start", spec.name, spec.port, "--", *spec.command], self._env(spec)
            )
            self.started.append(spec.name)
            if int(getattr(result, "returncode", 1)) != 0:
                tail = log_tail(self.run_dir, spec.name)
                self.stop_all()
                raise ReadinessFailed(spec.name, tail)

    def stop_all(self) -> list[str]:
        """``scripts/proc.sh stop <name>`` for every started process, in reverse order (a stop never
        raises; the names stopped are returned)."""
        stopped: list[str] = []
        for name in reversed(self.started):
            self.runner(
                [self.proc_sh, "stop", name], {**os.environ, "EREV_RUN_DIR": str(self.run_dir)}
            )
            stopped.append(name)
        self.started.clear()
        return stopped
