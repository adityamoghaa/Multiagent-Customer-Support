# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install only slim production dependencies (no torch/transformers)
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements-prod.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY multiagent_support/ ./multiagent_support/
COPY app/ ./app/

# Create data directory for logs.db
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENV ENABLE_HF_MODELS=false
ENV LOG_DB_PATH=data/logs.db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
