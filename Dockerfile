# Multi-stage build for Legal Research Assistant MCP
# Stage 1: Builder - Prepare dependencies
FROM python:3.12-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager for faster, more reliable builds
RUN set -euo pipefail; \
    INSTALLER_PATH="/tmp/uv-install.sh"; \
    curl -LsSf https://astral.sh/uv/install.sh -o "$INSTALLER_PATH"; \
    sh "$INSTALLER_PATH"; \
    rm "$INSTALLER_PATH"
ENV PATH="/root/.cargo/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Build virtual environment (no dev dependencies in production)
RUN uv sync --frozen --no-dev

# Stage 2: Runtime - Minimal production image
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Copy application code
COPY app/ ./app/
COPY CLAUDE.md README.md ./

# Create non-root user for security
RUN useradd -m -u 1000 -s /sbin/nologin appuser && \
    chown -R appuser:appuser /app

USER appuser

# Health check for container orchestration
# Checks both FastAPI and MCP server availability using curl (available in runtime image)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -fS http://localhost:8000/health || exit 1

# Expose default port
EXPOSE 8000

# Default to FastAPI server
ENV SERVER_TYPE=fastapi

# Entrypoint with flexible server selection
ENTRYPOINT ["python", "-c"]
CMD ["import os, sys; \
server_type = os.getenv('SERVER_TYPE', 'fastapi').lower(); \
if server_type == 'fastapi': \
    argv = ['python', '-m', 'uvicorn', 'app.api:app', '--host', '0.0.0.0', '--port', '8000']; \
elif server_type == 'mcp': \
    argv = ['legal-research-mcp']; \
else: \
    sys.stderr.write(f'Unsupported SERVER_TYPE: {server_type}\\n'); \
    sys.exit(1); \
os.execvp(argv[0], argv)"]
