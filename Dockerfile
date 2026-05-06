# ============================================================
# Banking MCP Server - Multi-stage Docker build
# Stage 1: build deps
# Stage 2: runtime with nginx + supervisord
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY banking_mcp/ ./banking_mcp/
COPY main.py ./
COPY supervisord.conf /etc/supervisord.conf
COPY nginx.conf /etc/nginx/nginx.conf

RUN mkdir -p /app/logs /etc/nginx

EXPOSE 80 8080

ENV MCP_TRANSPORT=http \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8080 \
    AUDIT_LOG_PATH=/app/logs/audit.log \
    LOG_LEVEL=INFO \
    ENV=prod

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisord.conf"]
