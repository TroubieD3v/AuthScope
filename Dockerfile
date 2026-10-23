# --- frontend build -----------------------------------------------------------
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- backend + built UI -------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 AUTHSCOPE_DB=/data/authscope.db AUTHSCOPE_STATIC=/app/ui
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install .
COPY --from=ui /ui/dist ./ui
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
EXPOSE 8080
# Inside the container we must bind 0.0.0.0; docker-compose publishes the port on 127.0.0.1 only.
CMD ["authscope", "serve", "--host", "0.0.0.0", "--port", "8080", "--i-know-this-is-exposed"]
