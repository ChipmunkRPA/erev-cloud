# syntax=docker/dockerfile:1
# Web image (docs/05-ARCHITECTURE.md §8.1 DPL-03, DPL-05, §8.2 DPL-12; SAR-20; D-47). Build from the
# repository root: `docker build -f deploy/docker/web.Dockerfile .` (make docker-build). The build
# stage compiles the SPA without the design gallery (DG-FE-19); the runtime stage is unprivileged nginx
# on 8080 serving the bundle and proxying /api/ to the api service.

FROM node:22-bookworm-slim AS build
WORKDIR /app/frontend
ENV VITE_API_BASE=/api
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build
# The image serves no source map (05 DPL-03 rev 1.53). Vite writes them next to each asset
# (build.sourcemap "hidden": no sourceMappingURL comment), and the runtime stage copies dist/ as a
# whole, so they are moved out of it here. A release process that wants them exports
# /app/frontend/sourcemaps from this stage (docker build --target build).
RUN mkdir /app/frontend/sourcemaps && find dist -type f -name '*.map' -exec mv {} /app/frontend/sourcemaps/ \; && test -z "$(find dist -type f -name '*.map')"

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY deploy/docker/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/docker/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
