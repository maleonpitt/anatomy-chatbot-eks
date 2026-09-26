# Production-oriented API image for ECR / EKS
FROM python:3.10-slim

WORKDIR /app

# Non-root user for Kubernetes
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

USER appuser

ENV PORT=5000 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

EXPOSE 5000

# Uvicorn = production ASGI server for FastAPI
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]
