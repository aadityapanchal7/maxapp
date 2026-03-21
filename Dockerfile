# Build from repo root (Render expects Dockerfile here when context is `.`).
# App lives in ./backend
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD sh -c 'uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}'
