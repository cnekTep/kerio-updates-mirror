# Production Dockerfile - builds venv only, application code is bind-mounted at runtime
FROM ghcr.io/astral-sh/uv:0.12.1-python3.14-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /mirror

# Install only dependencies (no project code baked in — it's bind-mounted at runtime)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Final stage - minimal runtime image without uv
FROM python:3.14.6-slim-trixie

# gosu lets entrypoint run as root (needed to set ACLs),
# then drop to appuser cleanly before starting the app.
# acl provides setfacl/getfacl for permission management.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu acl \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 999 appuser \
 && useradd --system --gid 999 --uid 999 --create-home appuser

# Only the venv comes from the image; application code is provided via bind mount
COPY --from=builder --chown=appuser:appuser /mirror/.venv /mirror/.venv

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

# Set PATH to use virtualenv
ENV PATH="/mirror/.venv/bin:$PATH"

# No USER directive here - container starts as root so entrypoint
# can set ACLs, then drops privileges via gosu before running the app.

WORKDIR /mirror

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "run"]