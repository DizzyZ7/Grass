FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    groupadd -r grass && useradd --no-log-init -r -g grass grass
COPY backend ./backend
COPY alembic.ini ./
COPY --from=web /web/dist ./frontend/dist
RUN chown -R grass:grass /app
USER grass
EXPOSE 8000
# Fail deployment if migrations cannot connect; never run concurrent migration workers.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips 127.0.0.1 "]
