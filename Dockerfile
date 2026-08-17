# SupportPilot AI — Phase 12: Dockerfile
#
# ONE image for the whole app. The original phase plan (see README.md's
# reference example) assumed a separate React frontend + FastAPI backend,
# each with their own Dockerfile. We deliberately merged those back in
# Phase 4 — the frontend is served BY the FastAPI app (GET /) to avoid
# CORS entirely — so there's only one real service here to containerize.
# See PHASE_PLAN.md's Phase 12 notes for the full reasoning.
#
# Uses uv inside the container too, consistent with local dev. Layering
# is deliberate and follows Astral's own recommended pattern: dependency
# files are copied and synced BEFORE the rest of the source code, so
# editing application code doesn't invalidate the (slower) dependency-
# install layer on rebuild — only editing pyproject.toml/uv.lock does.

FROM python:3.12-slim

# Copy the uv binary from Astral's official image rather than installing
# it via pip — faster, and matches Astral's own documented pattern.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 1) Dependencies first, without the project itself. This layer is
#    cached and only re-runs when pyproject.toml/uv.lock change — not on
#    every source code edit, which keeps rebuilds fast during iteration.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 2) Now the actual application code.
COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Same command as local dev (`uv run uvicorn api:app --reload`), minus
# --reload (that's a dev-only convenience, not for a container image)
# and bound to 0.0.0.0 so it's reachable from outside the container.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
