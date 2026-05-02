# ============================================================
# Banking MCP Server — Multi-stage Docker build
# Stage 1: build deps
# Stage 2: runtime with nginx + supervisord
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Runtime system packages: nginx + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    apache2-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY banking_mcp/ ./banking_mcp/
COPY main.py ./
COPY supervisord.conf /etc/supervisord.conf
COPY nginx.conf /etc/nginx/nginx.conf

# Create logs and htpasswd dirs
RUN mkdir -p /app/logs /etc/nginx

# Generate default htpasswd (admin / banking123) — override via env in production
RUN htpasswd -bc /etc/nginx/.htpasswd admin banking123

# Expose: 80 (nginx), 8080 (FastAPI), 8501 (Streamlit)
EXPOSE 80 8080 8501

ENV MCP_TRANSPORT=http \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8080 \
    DASHBOARD_PORT=8501 \
    DASHBOARD_URL=http://localhost:8501 \
    AUDIT_LOG_PATH=/app/logs/audit.log \
    LOG_LEVEL=INFO \
    ENV=prod

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisord.conf"]
