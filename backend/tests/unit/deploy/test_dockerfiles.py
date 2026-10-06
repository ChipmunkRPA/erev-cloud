"""Container images (05 §8.1 DPL-01 to DPL-05, §8.2 DPL-12; SAR-20, SAR-33; BUILD_SPEC DEP-1).

The Dockerfiles, the nginx configuration and ``.dockerignore`` are read as text: the loop never runs
Docker (DG-FORBID-12; ``make docker-build`` is a supervisor target). REQs contributed: REQ-OPS-001,
REQ-SEC-001.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOCKER = ROOT / "deploy" / "docker"
NGINX = DOCKER / "nginx"
PYTHON_BASE = "python:3.12-slim-bookworm"
EREV_BIN = "/app/.venv/bin/erev"


@dataclass(frozen=True)
class Stage:
    name: str
    base: str
    instructions: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def all(self, keyword: str) -> list[str]:
        return [value for name, value in self.instructions if name == keyword]

    def one(self, keyword: str) -> str:
        values = self.all(keyword)
        assert len(values) == 1, f"stage {self.name}: expected one {keyword}, found {values}"
        return values[0]

    def env(self) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for value in self.all("ENV"):
            for token in value.split():
                name, _, setting = token.partition("=")
                pairs[name] = setting
        return pairs


def logical_lines(text: str) -> list[str]:
    """Instructions with continuation lines joined; comments and blank lines dropped."""
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].strip() + " "
            continue
        lines.append(buffer + stripped)
        buffer = ""
    assert buffer == "", "a continuation line runs past the end of the file"
    return lines


def stages(path: Path) -> dict[str, Stage]:
    parsed: list[tuple[str, str, list[tuple[str, str]]]] = []
    for line in logical_lines(path.read_text(encoding="utf-8")):
        keyword, _, rest = line.partition(" ")
        keyword = keyword.upper()
        if keyword == "FROM":
            match = re.fullmatch(r"(\S+)\s+AS\s+(\S+)", rest.strip(), flags=re.IGNORECASE)
            assert match is not None, f"{path.name}: every stage is named ({line})"
            parsed.append((match.group(2), match.group(1), []))
        else:
            assert parsed, f"{path.name}: {keyword} before the first FROM"
            parsed[-1][2].append((keyword, rest.strip()))
    return {name: Stage(name, base, tuple(items)) for name, base, items in parsed}


def healthcheck_command(stage: Stage) -> list[str]:
    options, marker, command = stage.one("HEALTHCHECK").partition("CMD ")
    assert marker, "HEALTHCHECK has a CMD"
    assert "--interval=" in options and "--timeout=" in options
    parsed = json.loads(command)
    assert isinstance(parsed, list), "exec form: no shell in the runtime stage (SAR-33)"
    return [str(part) for part in parsed]


def python_runtime(stage: Stage) -> None:
    """SAR-33 and DPL-01: uid/gid 10001, production environment, the venv entrypoint, no shell."""
    assert stage.base == PYTHON_BASE
    assert stage.one("USER") == "10001"
    env = stage.env()
    assert env["EREV_ENV"] == "production"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    copies = stage.all("COPY")
    assert any(value.startswith("--from=build ") for value in copies)
    # 05 REL-03: a production process refuses to start without the release manifest, so the
    # runtime stage copies the one at the root of its build context (`make docker-build` places it
    # in the exported context, DPL-05), after the application tree.
    manifest = "release-manifest.json /app/release-manifest.json"
    assert manifest in copies, "the runtime stage copies release-manifest.json into /app"
    assert copies.index(manifest) > next(
        n for n, value in enumerate(copies) if value.startswith("--from=build ")
    )
    runs = stage.all("RUN")
    assert any("groupadd" in run and "--gid 10001" in run for run in runs)
    assert any("useradd" in run and "--uid 10001" in run for run in runs)
    assert re.search(r"\brm -f [^&]*/usr/bin/sh\b", runs[-1]), "the last RUN removes the shell"
    # 05 SAR-33, DPL-01, DPL-02 rev 1.53 (ruling R-37 (b)): the same RUN removes the base
    # interpreter's pip (package, metadata, launchers) and ensurepip and clears the setuid and
    # setgid bits of every regular file, all while a shell still exists. `make docker-build` probes
    # the built images for both (test_docker_build).
    steps = [step.strip() for step in runs[-1].split("&&")]
    (shells,) = [n for n, step in enumerate(steps) if "/usr/bin/sh" in step]
    assert shells == len(steps) - 1, "nothing runs after the shells are gone"
    lib = "/usr/local/lib/python3.12"
    (packages,) = [n for n, step in enumerate(steps) if step.startswith("rm -rf ")]
    assert steps[packages].split()[2:] == [
        f"{lib}/site-packages/pip",
        f"{lib}/site-packages/pip-*.dist-info",
        f"{lib}/ensurepip",
    ]
    (launchers,) = [n for n, step in enumerate(steps) if step.startswith("rm -f /usr/local/bin/")]
    assert steps[launchers].split()[2:] == [
        "/usr/local/bin/pip",
        "/usr/local/bin/pip3",
        "/usr/local/bin/pip3.12",
    ]
    assert stage.base.startswith("python:3.12-"), "the paths above name this interpreter version"
    (bits,) = [n for n, step in enumerate(steps) if step.startswith("find ")]
    assert steps[bits] == "find / -xdev -type f -perm /6000 -exec chmod a-s {} +"
    assert max(packages, launchers, bits) < shells
    assert json.loads(stage.one("ENTRYPOINT")) == [EREV_BIN]


def test_api_image() -> None:
    api = stages(DOCKER / "api.Dockerfile")
    assert list(api) == ["build", "runtime"]
    build, runtime = api["build"], api["runtime"]
    assert build.base == PYTHON_BASE
    uv_copies = [value for value in build.all("COPY") if "ghcr.io/astral-sh/uv" in value]
    assert len(uv_copies) == 1
    assert re.match(r"--from=ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ ", uv_copies[0]), "a pinned uv tag"
    assert build.env()["UV_PROJECT_ENVIRONMENT"] == "/app/.venv"
    syncs = [run for run in build.all("RUN") if run.startswith("uv sync")]
    assert syncs and all("--frozen" in run and "--no-dev" in run for run in syncs)
    # The hosted providers come from the `gcp` extra (05 SAR-21; lane P2), in every image layer.
    assert all("--extra gcp" in run for run in syncs)
    assert syncs[-1] == "uv sync --frozen --no-dev --extra gcp"

    python_runtime(runtime)
    assert runtime.one("EXPOSE") == "8080"
    assert json.loads(runtime.one("CMD")) == ["api", "--host", "0.0.0.0", "--port", "8080"]
    assert healthcheck_command(runtime) == [
        EREV_BIN,
        "healthcheck",
        "--url",
        "http://127.0.0.1:8080/api/v1/healthz",
    ]


def test_worker_image() -> None:
    api = stages(DOCKER / "api.Dockerfile")
    worker = stages(DOCKER / "worker.Dockerfile")
    assert list(worker) == ["build", "runtime"]
    # One build stage, byte for byte, so both images reuse the same Python layers (DPL-02).
    assert worker["build"] == api["build"]
    runtime = worker["runtime"]
    python_runtime(runtime)
    assert runtime.all("EXPOSE") == []
    command = json.loads(runtime.one("CMD"))
    assert command == ["worker"], "all eight queues: no --queues (DG-KRN-JOB-11)"
    assert healthcheck_command(runtime) == [EREV_BIN, "worker", "--check"]


def active_config(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def blocks(text: str, header: str) -> dict[str, str]:
    """``location <path> { ... }`` bodies keyed by path, from configuration without comments."""
    found: dict[str, str] = {}
    for match in re.finditer(rf"{header}\s+([^\s{{]+)\s*\{{", text):
        depth, index = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            index += 1
        found[match.group(1)] = text[match.end() : index - 1]
    return found


def directive(body: str, name: str) -> list[str]:
    return [value.strip() for value in re.findall(rf"(?m)^\s*{name}\s+([^;]+);", body)]


def vite_security_headers() -> dict[str, str]:
    source = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    body = source.split("SECURITY_HEADERS: Record<string, string> = {", 1)[1].split("};", 1)[0]
    headers: dict[str, str] = {}
    for name, value in re.findall(r'"([A-Za-z-]+)":\s*((?:"[^"]*"\s*\+?\s*)+),', body):
        headers[name] = "".join(re.findall(r'"([^"]*)"', value))
    return headers


def test_web_image_and_nginx() -> None:
    web = stages(DOCKER / "web.Dockerfile")
    assert list(web) == ["build", "runtime"]
    build, runtime = web["build"], web["runtime"]
    assert build.base == "node:22-bookworm-slim"
    assert build.env()["VITE_API_BASE"] == "/api"
    assert "VITE_EREV_DESIGN_GALLERY" not in build.env(), "no gallery in images (DG-FE-19)"
    install, compile_spa, strip_maps = build.all("RUN")
    assert (install, compile_spa) == ("npm ci --no-audit --no-fund", "npm run build")
    # 05 DPL-03 rev 1.53 (R-34 SF-5): the image serves no source map. Vite writes them next to
    # the assets, and the runtime stage copies dist/ as a whole, so the build stage moves them out
    # of dist/ and fails the build if one is left.
    assert strip_maps == (
        "mkdir /app/frontend/sourcemaps && find dist -type f -name '*.map' -exec mv {} "
        "/app/frontend/sourcemaps/ \\; && test -z \"$(find dist -type f -name '*.map')\""
    )
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert 'sourcemap: "hidden"' in vite, "the maps are still built, as an artefact of the build"
    assert runtime.base == "nginxinc/nginx-unprivileged:1.27-alpine"
    assert runtime.one("EXPOSE") == "8080"
    assert runtime.one("USER") == "101"
    copies = runtime.all("COPY")
    assert "deploy/docker/nginx/default.conf /etc/nginx/conf.d/default.conf" in copies
    assert (
        "deploy/docker/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf"
        in copies
    )
    assert "--from=build /app/frontend/dist /usr/share/nginx/html" in copies

    config = active_config((NGINX / "default.conf").read_text(encoding="utf-8"))
    servers = re.findall(r"(?m)^server\s*\{", config)
    assert len(servers) == 1, "one active server; the TLS server is commented"
    server = config.split("server {", 1)[1]
    assert directive(server, "listen") == ["8080"]
    locations = blocks(server, "location")
    assert "/metrics" not in config and not any("metrics" in path for path in locations)

    server_level = re.sub(r"location\s+[^\s{]+\s*\{[^}]*\}", "", server)
    assert directive(server_level, "client_max_body_size") == ["1m"]
    limits = {
        path: directive(body, "client_max_body_size")
        for path, body in locations.items()
        if path.startswith("/api/")
    }
    assert limits == {
        "/api/": ["1m"],
        "/api/v1/files": ["501m"],
        "/api/v1/attachments": ["1m"],
        "/api/v1/imports": ["1m"],
        "/api/v1/migrations": ["1m"],
    }
    # 05 DPL-12 rev 1.128 (ruling R-111 (8)): the api authenticates an upload before it reads
    # the body, and nginx's default — buffer the whole request, then hand it over — would store
    # the body first. The upload location passes the body through as it arrives; no other
    # location changes the default (their bodies are at most 1 MiB).
    assert {
        path: directive(body, "proxy_request_buffering")
        for path, body in locations.items()
        if directive(body, "proxy_request_buffering")
    } == {"/api/v1/files": ["off"]}
    assert directive(locations["/api/v1/files"], "proxy_http_version") == ["1.1"]
    # Lane OPS, first real run (2026-09-29): `GET /assets/missing.js` answered 404 with
    # `Cache-Control: public, max-age=31536000, immutable`, because the one header was `always`.
    # Only a served asset (200, 206, 304) is cached for a year; every other status is no-store.
    assert directive(locations["/assets/"], "add_header") == [
        "Cache-Control $erev_asset_cache_control always"
    ]
    (cache_map,) = re.findall(r"map \$status \$erev_asset_cache_control \{([^}]*)\}", config)
    assert dict(re.findall(r'(?m)^\s*(\S+)\s+"([^"]*)";$', cache_map)) == {
        "default": "no-store",
        "200": "public, max-age=31536000, immutable",
        "206": "public, max-age=31536000, immutable",
        "304": "public, max-age=31536000, immutable",
    }
    assert "immutable" not in "".join(
        body for path, body in locations.items() if path != "/assets/"
    )
    for path, body in locations.items():
        # add_header in a location replaces inherited headers, so each location includes SAR-20.
        assert directive(body, "include") == ["/etc/nginx/snippets/security-headers.conf"], path
        if path.startswith("/api/"):
            assert directive(body, "proxy_pass") == ["$erev_api"], path
            forwarded = {value.split()[0] for value in directive(body, "proxy_set_header")}
            assert {"X-Forwarded-For", "X-Forwarded-Proto", "X-Request-Id"} <= forwarded, path

    # 05 DPL-12 rev 1.53: the upstream is a variable, so nginx resolves the name api when it
    # proxies, through the DNS of the compose network. With the name in proxy_pass nginx resolved
    # it once at start: a recreated api container was proxied at its old address (502 until the
    # web container was restarted), and the image did not start where nothing is named api.
    assert directive(server_level, "set") == ["$erev_api http://api:8080"]
    assert directive(config.split("server {", 1)[0], "resolver") == [
        "127.0.0.11 valid=10s ipv6=off"
    ]
    # Where no resolver answers (outside a compose network) the wait is bounded.
    assert directive(config.split("server {", 1)[0], "resolver_timeout") == ["5s"]
    assert "api:8080" not in "".join(locations.values()), "no location names the host"
    assert "upstream " not in config, "an upstream block would be resolved at start too"

    headers_text = (NGINX / "security-headers.conf").read_text(encoding="utf-8")
    headers = dict(
        re.findall(
            r'(?m)^add_header\s+([A-Za-z-]+)\s+"([^"]*)"\s+always;$', active_config(headers_text)
        )
    )
    assert "Content-Security-Policy" in headers
    # 05 SAR-20 rev 1.53 (R-37 (a)): the resource policy joins the set; the embedder policy is
    # deliberately absent (docs/security/security-notes.md).
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "Cross-Origin-Embedder-Policy" not in headers
    # The api sends the same headers itself (hosted, the load balancer reaches it directly), so
    # every proxy location hides the api's copy of each: a response carries each header once.
    from erev_api.api.middleware import SECURITY_HEADERS as api_headers

    assert set(api_headers) == {*headers, "Cache-Control"}
    assert all(api_headers[name] == value for name, value in headers.items())
    for path, body in locations.items():
        if path.startswith("/api/"):
            assert sorted(directive(body, "proxy_hide_header")) == sorted(api_headers), path
    assert headers == vite_security_headers(), "nginx and vite preview serve the same headers"
    assert "'unsafe-inline'" not in headers["Content-Security-Policy"]

    # 05 SAR-20 rev 1.53 (R-34 SD-3): Strict-Transport-Security is sent by the server that
    # terminates TLS and by no other. The snippet every location includes carries the header with
    # a variable that is empty on a plain-HTTP connection (nginx omits an empty header) and the
    # policy when the connection is TLS.
    assert re.findall(
        r"(?m)^add_header\s+Strict-Transport-Security\s+(\S+)\s+always;$",
        active_config(headers_text),
    ) == ["$erev_hsts"]
    (hsts_map,) = re.findall(r"map \$https \$erev_hsts \{([^}]*)\}", config)
    assert dict(re.findall(r'(?m)^\s*(\S+)\s+"([^"]*)";$', hsts_map)) == {
        "default": "",
        "on": "max-age=31536000; includeSubDomains",
    }
    assert "Strict-Transport-Security" not in server, "the plain-HTTP server names no policy"

    raw = (NGINX / "default.conf").read_text(encoding="utf-8")
    commented = "\n".join(line for line in raw.splitlines() if line.lstrip().startswith("#"))
    assert re.search(r"#\s*server\s*\{", commented), "a commented TLS server block"
    assert re.search(r"#\s*listen\s+\d+\s+ssl;", commented)
    assert re.search(r"#\s*ssl_protocols\s+TLSv1\.2\s+TLSv1\.3;", commented)
    assert "ssl_protocols" not in config, "TLS stays documentation until an operator enables it"
    # A server-level add_header would be dropped by every location (each sets its own), so the
    # documented TLS server relies on the snippet and says so.
    assert not re.search(r"#\s*add_header\s+Strict-Transport-Security", commented)
    assert "Strict-Transport-Security: max-age=31536000; includeSubDomains" in commented
    # The documented TLS server needs the upstream variable its repeated locations pass to.
    assert re.search(r"#\s*set \$erev_api http://api:8080;", commented)


def test_dockerignore() -> None:
    entries = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required = {
        ".env",
        ".data",
        ".run",
        ".scratch",
        ".ralph",
        "node_modules",
        ".venv",
        "docs/research/rightrev-ui",
        "legacy-harness",
        "research-harness",
    }
    assert required <= entries, sorted(required - entries)
    assert not any(entry.startswith("!") for entry in entries), "nothing is re-included"
    # REL-03: the manifest written by make release-manifest must reach the build context.
    assert "release-manifest.json" not in entries
    assert not any(entry.endswith((".json", "*")) and "/" not in entry for entry in entries)
