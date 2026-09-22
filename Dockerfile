FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:22-bookworm-slim AS codex
RUN npm install -g @openai/codex@0.155.1

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/api/src
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt && useradd --create-home app \
    && mkdir -p /home/app/.codex /home/app/.local/share/r19finder \
    && chown -R app:app /home/app \
    && chmod 700 /home/app/.codex /home/app/.local/share/r19finder
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
COPY --chown=app:app api/src ./
COPY --chown=app:app api/db /app/api/db
COPY --chown=app:app frontend/templates/app.html /app/frontend/templates/app.html
COPY --chown=app:app frontend/static/favicon.svg /app/frontend/static/favicon.svg
COPY --from=frontend /build/static/app /app/frontend/static/app
USER app
EXPOSE 8000
CMD ["sh", "-c", "python init_db.py && exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60 app:app"]
