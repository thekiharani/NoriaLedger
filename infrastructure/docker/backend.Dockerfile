# syntax=docker/dockerfile:1.7
#
# Noria Ledger backend image.
#
# Extends the pinned official frappe/erpnext image (Frappe + ERPNext, built by
# frappe_docker) with the Noria Ledger Frappe apps. Upstream layers are reused
# unchanged, so only the thin Noria layer is rebuilt and pushed per release.
# See docs/TECHNICAL_AUDIT.md ("Image build strategy") for the rationale.
#
# Build context: repository root.

ARG ERPNEXT_IMAGE=docker.io/frappe/erpnext:v16.51.1@sha256:85b63c68a1e7992179f5448f334916a49b2e47e5e7382fc346039d073bc7ca27

FROM ${ERPNEXT_IMAGE} AS backend

ARG NORIA_VERSION=0.0.0-dev
LABEL org.opencontainers.image.title="noria-ledger-backend" \
      org.opencontainers.image.vendor="Noria Technologies Ltd" \
      org.opencontainers.image.version="${NORIA_VERSION}" \
      org.opencontainers.image.description="Frappe + ERPNext + Noria Ledger apps"

USER frappe
WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:0 apps/noria_practice apps/noria_practice
COPY --chown=frappe:0 apps/noria_ledger apps/noria_ledger

# - Register the apps on the bench virtualenv's path exactly like bench's editable
#   installs of frappe/erpnext (a .pth entry per app). Our apps have no extra
#   Python dependencies, so the build needs no network access and a development
#   bind mount over apps/<app> is picked up live.
# - Assets: the base image keeps baked assets in ./assets (the entrypoint links
#   them into the sites volume), so link the apps' public folders there.
# - sites/ is a VOLUME in the base image; sites/apps.txt is written by the
#   configurator service at runtime, not here.
RUN site_packages="$(env/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && for app in noria_practice noria_ledger; do \
         echo "/home/frappe/frappe-bench/apps/${app}" > "${site_packages}/${app}.pth"; \
         ln -sfn "../apps/${app}/${app}/public" "assets/${app}"; \
       done \
    && env/bin/python -c "import noria_practice, noria_ledger; print('apps importable')" \
    && find apps/noria_practice apps/noria_ledger -name '__pycache__' -prune -exec rm -rf {} + \
    && chmod -R g=u apps/noria_practice apps/noria_ledger
