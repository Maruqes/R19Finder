FROM node:22-alpine AS css
WORKDIR /build
RUN npm install tailwindcss@4 @tailwindcss/cli@4
COPY templates ./templates
COPY static/input.css ./static/input.css
RUN npx @tailwindcss/cli -i ./static/input.css -o ./static/style.css --minify

FROM node:22-bookworm-slim AS codex
RUN npm install -g @openai/codex@0.155.1

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app \
    && mkdir -p /home/app/.codex /home/app/.local/share/r19finder \
    && chown -R app:app /home/app \
    && chmod 700 /home/app/.codex /home/app/.local/share/r19finder
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
COPY --chown=app:app . .
COPY --from=css /build/static/style.css ./static/style.css
USER app
EXPOSE 8000
CMD ["sh", "-c", "python init_db.py && exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60 app:app"]
