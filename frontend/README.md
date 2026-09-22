# React frontend

R19 Finder uses React 19, TypeScript, Vite, Tailwind CSS 4 and shadcn/ui (Radix). Motion handles gallery transitions and respects reduced-motion preferences. The interface stays dark throughout.

## Architecture

- `src/pages/`: requests, AI draft review, research, schedules, cars and configuration screens.
- `src/components/ui/`: locally owned shadcn components installed with the official CLI.
- `src/components/`: navigation, galleries, forms, status and Markdown components.
- `src/lib/`: typed page data, HTTP helpers and the tested three-way suggestion merge.
- `src/styles.css`: shared design tokens, layouts and responsive rules.
- `templates/app.html`: the single production HTML entry point.
- `static/app/`: generated, hashed assets and Vite manifest (ignored by Git).
- `e2e/`: browser tests using a dedicated database and mocked AI inference.

Flask routes provide a safely escaped JSON bootstrap payload and render the React entry point. React owns all visible page content. Navigation and validated form submissions retain the existing URLs, sessions, CSRF checks and redirects. Request drafts use the existing JSON API; active research polls the current page with `Accept: application/json`.

Production uses the Vite manifest. Fonts are served locally, page modules load on demand, and raw HTML in AI Markdown stays disabled. Per-response CSP nonces permit Radix's generated styles without enabling arbitrary inline scripts or styles.

React is the only frontend implementation. Flask renders `templates/app.html`; page identifiers in route handlers select React screens.

## Build and run

From the repository root:

```sh
make up
```

Docker installs frontend dependencies with `npm ci`, compiles React and copies only the production entry point, favicon and generated assets into the application image. The public app remains at `http://localhost:8000`.

For local work, use Node 22.12+ and a Python virtual environment:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python -m venv .venv
.venv/bin/pip install -r api/requirements.txt
docker compose up -d db
export DATABASE_URL='postgresql://r19finder:local-development-password@127.0.0.1:5433/r19finder'
export SECRET_KEY='local-development-only'
export APP_SECRET_DIR="$PWD/.venv/secrets"
.venv/bin/python api/src/init_db.py
PYTHONPATH=api/src .venv/bin/flask --app app run --port 8000
```

In another terminal, `npm --prefix frontend run dev` watches and rebuilds the assets. Refresh the Flask page after rebuilding. This uses the production integration and CSP, without a separate Vite HTML server. Adjust the database URL to match your local configuration.

## Checks

```sh
npm --prefix frontend run build
make test-frontend
```

Browser tests require Chromium and a dedicated database. They **truncate test records in `r19finder_frontend_test`** and never start AI workers or send Discord messages:

```sh
docker compose exec db createdb -h 127.0.0.1 -p 5433 -U r19finder r19finder_frontend_test
cd frontend
npx playwright install chromium
npm run test:e2e
```

If that database already exists, skip `createdb`. Set `R19_TEST_DATABASE_URL` to override the connection credentials/port; the database name must remain `r19finder_frontend_test`. Tests start and stop their own Flask server on port 8001.

The suite covers desktop/mobile routes, keyboard navigation, CSP, photo uploads, draft recovery and edits, AI conflicts, schedules, blacklist restoration, preferences, safe Markdown and automated WCAG A/AA checks. Actual external provider inference remains outside the browser suite.

See [the design system](../DESIGN.md) and [application setup](../README.md).
