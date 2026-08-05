# The Hub in one image: the API, the MCP gateway, and the built UI.
#
# Digests rather than tags. A tag is a moving target, and "it worked yesterday" is not a property
# anyone wants to debug in a deployment.

# --- The UI ------------------------------------------------------------------------------------
FROM node:22-bookworm-slim@sha256:f32b81066cde10a75dbac96646099533316d94bac4150c55da1636e1f0ffdc46 AS ui

WORKDIR /ui
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- The Python packages -----------------------------------------------------------------------
FROM python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30 AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# The lock file is the source of truth for third-party versions; the four workspace packages are
# built as wheels so that nothing in the runtime image is an editable install pointing at a
# checkout that is not there.
#
# The filter is a substring match, not an anchored one: poetry writes a path dependency as
# `-e file:///src/packages/api/agentskills-hub-api`, so anchoring on the package name matches
# nothing and pip then tries to install a directory that has not been copied yet. The `file://`
# assertion is there so that a future change to that format fails here rather than at runtime.
COPY pyproject.toml poetry.lock ./
RUN pip install "poetry==2.2.1" "poetry-plugin-export==1.9.0" \
 && poetry export --only main --without-hashes --format requirements.txt \
      | grep -v "agentskills-hub" > /tmp/requirements.txt \
 && ! grep -q "file://" /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt

COPY packages/ ./packages/
RUN pip install --no-deps \
      ./packages/core/agentskills-hub-core \
      ./packages/api/agentskills-hub-api \
      ./packages/gateway/agentskills-hub-gateway \
      ./packages/server/agentskills-hub-server

# --- The runtime -------------------------------------------------------------------------------
FROM python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30 AS runtime

LABEL org.opencontainers.image.title="Agent Skills Hub" \
      org.opencontainers.image.description="Governed catalogue and delivery plane for Agent Skills" \
      org.opencontainers.image.source="https://github.com/pratikxpanda/agentskills-hub" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HUB_DATABASE_URL="sqlite+aiosqlite:////data/hub.db" \
    HUB_STORE_ROOT="/data/store" \
    HUB_WEB_ROOT="/app/web"

# A fixed uid so that a bind-mounted host directory can be chowned to something predictable.
RUN groupadd --gid 10001 hub \
 && useradd --uid 10001 --gid hub --home-dir /app --no-create-home hub \
 && mkdir -p /app /data \
 && chown hub:hub /data

COPY --from=build /opt/venv /opt/venv
COPY --from=ui /ui/dist /app/web
COPY --chmod=0555 deploy/entrypoint.sh /app/entrypoint.sh
# Seeding is optional, so the manifest and the skills it packs are optional too -- but an image
# that cannot demonstrate itself is the problem this whole item exists to solve.
COPY scripts/seed.py /app/scripts/seed.py
COPY examples/ /app/examples/

WORKDIR /app
USER hub
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "agentskills_hub_server.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
