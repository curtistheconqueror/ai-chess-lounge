FROM node:24-alpine AS web-builder
WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api \
    STOCKFISH_PATH=/usr/games/stockfish

RUN apt-get update \
    && apt-get install --no-install-recommends -y stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY alembic.ini ./
COPY services/ ./services/
COPY --from=web-builder /build/apps/web/dist ./apps/web/dist

EXPOSE 8000
CMD ["bash", "-lc", "alembic upgrade head && uvicorn lounge_api.main:app --app-dir services/api --host 0.0.0.0 --port 8000"]
