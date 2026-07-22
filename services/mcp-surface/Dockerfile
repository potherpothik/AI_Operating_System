# Build context is the REPO ROOT, same convention as every other
# service's Dockerfile since Phase 19. The "own isolated venv" rule
# (services/mcp-surface/README.md) exists to protect the SHARED repo
# .venv used across every other service's local dev workflow from the
# `mcp` package's newer starlette requirement — inside its own
# container, mcp-surface is already fully isolated, so this Dockerfile
# just installs its requirements.txt directly, no venv indirection
# needed.
FROM python:3.12-slim
WORKDIR /app
COPY services/mcp-surface/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/mcp-surface/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8025
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8025"]
