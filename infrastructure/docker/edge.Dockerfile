# syntax=docker/dockerfile:1.7
#
# Noria Ledger public edge: Caddy + prebuilt React SPA.
# Build context: repository root. No Node/Bun toolchain in the runtime image.

ARG BUN_IMAGE=docker.io/oven/bun:1.4-alpine@sha256:629e17411f1f129dbec3af78d5af9c9f2a937435c80349437206c6b0b7422373
ARG CADDY_IMAGE=docker.io/library/caddy:2.11-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f

FROM ${BUN_IMAGE} AS build
WORKDIR /src
COPY frontend/package.json frontend/bun.lock ./
# Optional extra CA bundle (corporate TLS-intercepting proxies) passed as a
# BuildKit secret: used for this step only, never written into a layer.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

FROM ${CADDY_IMAGE} AS edge
ARG NORIA_VERSION=0.0.0-dev
LABEL org.opencontainers.image.title="noria-ledger-edge" \
      org.opencontainers.image.vendor="Noria Technologies Ltd" \
      org.opencontainers.image.version="${NORIA_VERSION}"
COPY infrastructure/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv
RUN NORIA_SITE_ADDRESS=:80 NORIA_HUB_SITE=hub.example caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
