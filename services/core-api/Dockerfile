FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY services/core-api/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY services/core-api/app /app/app
COPY db /app/db
COPY scripts /app/scripts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
