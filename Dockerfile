# ── build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools needed for any compiled extensions (e.g. psutil)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt -r requirements-web.txt

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY src/ src/
COPY pyproject.toml ./

# ── Environment-variable configuration ────────────────────────────────────────
# CLI / dashboard knobs (all optional; defaults match the argparse defaults)
ENV SIGNALSCOPE_INTERVAL=2.0
ENV SIGNALSCOPE_TOP=""
ENV SIGNALSCOPE_CPU_THRESHOLD=50.0
ENV SIGNALSCOPE_MEM_THRESHOLD=10.0
ENV SIGNALSCOPE_NO_DAEMON=false
ENV SIGNALSCOPE_USER=""
ENV SIGNALSCOPE_ALERT_LOG=""
ENV SIGNALSCOPE_LOG_LEVEL=WARNING
# Set to "web" to start the FastAPI web dashboard instead of the CLI
ENV SIGNALSCOPE_MODE=cli
# Web-specific knobs
ENV SIGNALSCOPE_WEB_HOST=0.0.0.0
ENV SIGNALSCOPE_WEB_PORT=8000

# Expose the web-dashboard port (only used when SIGNALSCOPE_MODE=web)
EXPOSE 8000

# ── Entry point ────────────────────────────────────────────────────────────────
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
