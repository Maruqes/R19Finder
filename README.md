# R19 Finder

A simple application for managing car part requests. Built with a React 19 and shadcn/ui frontend, TypeScript, Tailwind CSS, Python/Flask and PostgreSQL. The interface is in English with dark mode enabled by default. Everything runs with Docker Compose.

## Features

- Create requests with a description, an optional vehicle and up to six photos.
- Browse a paginated request list and view details and photos.
- Edit descriptions and vehicles; keep, remove or add photos.
- Configure and check Codex CLI and Open WebUI connections.
- Research a part with Codex or an Open WebUI model, using photos, vehicle details and extra instructions.
- Keep a history of background searches, answers, source links and the request details used.
- Persist requests, photos, AI settings and credentials across container restarts.

Connection checks do not generate responses. Starting a part search sends the request details and photos to the selected provider and may use account credits.

## Quick start

Requirements: Docker, Docker Compose and Make. The Compose configuration uses host networking, supported natively on Linux. On supported Docker Desktop versions, enable host networking first.

```sh
make up
```

Run the commands below from the repository root.

Open **http://localhost:8000**. To use another port:

```sh
PORT=8080 make up
```

| Command | Effect |
| --- | --- |
| `make up` | Build images and start services in the background. |
| `make down` | Stop and remove application containers, preserving data. |
| `make remove` | Remove application containers, volumes and the local application image. **Deletes requests, photos, AI settings and authentication.** |
| `make codex-login` | Start Codex device code authentication inside the application container. |

Inspect logs and service health:

```sh
docker compose logs -f web
docker compose ps
```

## Configuration and networking

Optionally copy `.env.example` to `.env` before the first start:

```sh
cp .env.example .env
```

| Variable | Purpose | Default |
| --- | --- | --- |
| `PORT` | Application listening port. | `8000` |
| `POSTGRES_PORT` | PostgreSQL listening port on loopback. | `5433` |
| `POSTGRES_PASSWORD` | PostgreSQL password. | Local development password. |
| `SECRET_KEY` | Flask session signing key. | Local development key. |

All services use `network_mode: host`, sharing the PC's network stack. There are no Docker port mappings. Services on the PC are accessible using `localhost`, including Open WebUI. The application listens on `0.0.0.0:${PORT}`, so it is also accessible through the PC's LAN address where permitted by its firewall. PostgreSQL listens only on `127.0.0.1:${POSTGRES_PORT}`. Port 5433 avoids the PostgreSQL service already using port 5432 on the development machine.

Choose free ports if other services already use these defaults:

```sh
PORT=8080 POSTGRES_PORT=5434 make up
```

See [Docker host networking](https://docs.docker.com/engine/network/drivers/host/) for platform requirements. Host networking provides direct access to the host's network; it does not give the containers a separate LAN IP address.

The default credentials are for local development. Generate a random `SECRET_KEY` with `openssl rand -hex 32` before deployment. Changing `POSTGRES_PASSWORD` after the database volume exists also requires changing the password inside PostgreSQL.

Run `make up` after code or configuration changes to rebuild and recreate the application.

## Requests and photos

Click **New request**, enter the part description and optionally add vehicle details and photos. Open an existing request and click **Edit request** to make changes. Existing photos are kept unless selected for removal. Changes only take effect after clicking **Save changes**; **Cancel** leaves the saved request untouched.

- Description: 10–5000 characters.
- Vehicle: optional, up to 120 characters.
- Photos: optional, up to six per request, including retained photos when editing.
- Accepted formats: JPG, PNG and WebP, up to 5 MB and 20 million pixels per image.
- Maximum upload size: 32 MB.

Images are validated by their contents, resized to fit within 2000 × 2000 pixels and converted to JPEG without EXIF metadata. Descriptions and photos are saved in one database transaction. Photo bytes are stored in the PostgreSQL `photos` table using `BYTEA`; no upload directory is needed. Dates are shown in UTC. User-entered content is stored as written and is not translated.

## AI connections

Open **http://localhost:8000/ai** or click **AI** in the navigation.

### Codex CLI

Codex CLI is installed in the application image. Authenticate with:

```sh
make codex-login
```

Follow the link and code displayed in the terminal. Your account may need device code login enabled in ChatGPT security settings. Then click **Check authentication and refresh models** on the AI page.

This check runs `codex login status`, then queries `model/list` through `codex app-server` and displays the returned catalogue. Search forms discover models and supported reasoning levels automatically, with a short cache and the local catalogue as an offline fallback. No search or response generation is required to populate the selector. Listing models does not verify usage credits or successful inference. The container uses its own session and does not automatically reuse your host computer's Codex login. See the [official authentication documentation](https://developers.openai.com/codex/auth) and [app-server documentation](https://developers.openai.com/codex/app-server).

To sign out:

```sh
docker compose exec web codex -c 'cli_auth_credentials_store="file"' logout
```

### Open WebUI

Connect an existing Open WebUI installation:

1. Enable API keys in the Open WebUI administration settings and create a key in **Settings → Account**.
2. On the AI page, enter the base URL and API key, then click **Save settings**.
3. Click **Test saved connection** to list the models available to that account.

For Open WebUI running on this PC, use a URL such as `http://localhost:3000`, adjusting the port to match your installation. The containers use host networking, so localhost reaches the PC's services. For another computer, use its reachable IP address or hostname.

The test calls `GET /api/models` using Bearer authentication. It does not generate text. If API endpoint restrictions are enabled, allow `/api/models`. Redirects are not followed: configure the final base URL, without `/api/models`.

Leave the API key field blank to keep the saved key. When changing servers, enter the key for the new server again. Saved keys are never returned to the browser.

HTTPS certificate verification is disabled for Open WebUI requests to support the private VPN installation and its local CA. Traffic remains encrypted, but the server certificate and hostname are not verified. This setting applies only to the Open WebUI connector.

References: [Open WebUI API](https://docs.openwebui.com/reference/api-endpoints/) and [API keys](https://docs.openwebui.com/features/authentication-access/api-keys/).

## Research a part

### Cars and vehicle profiles

Open **Cars → Add car** to save a named vehicle profile. Make and model are required; year, generation/phase, body style, trim, engine/displacement/code, power, fuel, transmission, driven wheels, ABS, brakes and steering position are optional. Notes hold modifications, measurements and known references. Unknown details should stay blank rather than be guessed.

Each car can have any number of profile photos (JPG, PNG or WebP, no individual file size limit; up to 32 MB per upload). Upload several when creating or editing a car; new uploads append to the gallery. Select individual existing photos for removal when saving. All uploads are validated before any changes are saved. Existing single-photo profiles migrate without losing their image. Images are resized, normalized to JPEG and stored in PostgreSQL. Profile photos are not sent to AI searches; those continue to use the part photos attached to each request.

The homepage shows **Your cars** above part requests. Car galleries on the homepage, Cars list and profile page automatically advance every 5 seconds when multiple photos exist. Use arrows or numbered selectors to choose a photo (this pauses autoplay), and Play/Pause to control rotation. Autoplay pauses while hovering, focusing a gallery, or hiding the tab; it starts paused when reduced motion is preferred. Photos retain their proportions inside a stable responsive frame, without cropping. One-photo galleries have no unnecessary controls.

Phone EXIF orientation is applied during upload before resizing. Portrait and landscape photos keep their aspect ratio; the frontend scales them within the available width and viewport height without cropping or stretching. If a source image has no orientation metadata and its pixels are already sideways, rotate it before uploading.

Choose **Car profile** when creating or editing a request, or use **New part request** from a car's page. Existing requests without a profile still work with the free-text vehicle name. Each search, manual or scheduled, snapshots the linked car's current specifications and sends them to the selected provider. Profile edits affect future runs only; previous search snapshots remain unchanged. Do not enter personal information in the technical notes.

**Parts Found**, above search history, collects structured listings across completed searches into horizontally scrollable cards. Cards show image, price, shipping costs, seller/location, pickup/shipping status, availability and expandable fitment checks. Listing URLs are deduplicated, ignoring fragments and common tracking parameters, retaining the latest result. This is accumulated search history, not live stock; it refreshes automatically alongside the history without resetting horizontal scroll.

Use **Remove & blacklist** on a card, optionally add a reason, then confirm. The listing is persistently hidden from Parts Found for that request, even if another search returns it. Open **Blacklist** below the cards to restore a listing. Other requests are unaffected, and original AI answers remain in Search history. Both manual and scheduled searches snapshot all previously found and blocked URLs for Codex/Open WebUI to avoid. The worker refreshes exclusions before and after every research round and filters saved listings, linked summary paragraphs and source URLs on the server. Restoring a blocked item returns it to Parts Found; subsequent searches still seek new listings. Filtering in Parts Found also covers searches already in progress. Matching ignores fragments, query parameter order, `utm_*`, `fbclid` and `gclid`; a different seller URL or a relisted advert cannot reliably be identified as the same physical part.

### Weekly automations

Inside a request, configure **Find this part with AI**, then open **Schedule this search weekly**. Select weekdays and a separate time for each (e.g. Monday 16:30 and Thursday 20:50), then **Save weekly schedule**. Times use **Europe/Lisbon**, with automatic daylight saving. Each slot saves the provider, model, effort, instructions, preferences and priority website list. Current request text and photos are snapshotted when the scheduled search is queued. Saving the same day/time updates that slot instead of duplicating it.

The independent Docker `scheduler` service checks every 15 seconds and adds jobs to the same queue as manual searches. Results appear in the same auto-updating history, marked **Automatic weekly search**. Execution may start later if the worker is busy. An active search on the same request delays that scheduled occurrence until it finishes. The app never intentionally runs two searches for the same request concurrently.

Keep the computer and Docker running. After downtime, each overdue schedule runs once, rather than replaying every missed week, then resumes its weekly timing. In the spring DST gap, a nonexistent time moves forward; a repeated autumn time runs only once. **Disable**, **Enable** and **Delete schedule** manage future runs; already queued searches and past history are preserved. Enabling resumes at the next future occurrence. Automated searches can consume provider credits without further confirmation.

### Priority websites

Availability checks: providers must inspect the current listing, exclude sold/reserved/out-of-stock items, and supply page evidence for any availability claim. Cards show **Listed as available at search time (AI-reported)** or **Not confirmed**. The parser also removes structured items marked sold, reserved or unavailable and downgrades availability claims without evidence. This is not real-time stock synchronization or independent verification; availability can change after the search. No seller contacts or purchases are made to check stock.

Open **Websites** in the navigation to manage **Website listings**. Enter up to 30 public HTTP/HTTPS URLs, one per line, in priority order. Edit/remove/reorder lines and click **Save websites**; duplicates are removed. An empty list means normal web search. The shared list applies to Codex and Open WebUI.

Each new search snapshots this list. Both providers are instructed to check these sites first, then search the wider internet, and disclose inaccessible sites or missing results in the summary. This is a research instruction, not a guarantee that a provider can browse every site. Existing searches keep their original list, visible in their history. Routes: `GET /websites` displays the list; CSRF-protected `POST /websites` saves it.

**Preferred number of options** accepts 1–20 and defaults to 6. Both providers are asked to search multiple sellers and return distinct relevant listings, prioritizing fitment over quantity. This is a soft target: fewer matches are acceptable, and the AI should explain the shortfall without inventing or duplicating offers. The chosen count is saved with each search and displayed in its history. Larger targets may take longer within the existing search timeout.

1. Open a request and find **Find this part with AI**.
2. Click **Refresh Open WebUI models** to load the available models, or select **Codex CLI**.
3. When Codex CLI is selected, choose a **Codex model** from its dropdown, or keep **Default model**. Options come from the local CLI catalogue; if it is empty, run a default-model search and reload. The dropdown is hidden and disabled for Open WebUI. Set a **Preferred price**, including currency (e.g. €150): this is a soft preference, not a cap; the AI may suggest more expensive alternatives. Add **In-person pickup areas** (e.g. Northern Portugal / Galicia), **Seller countries or regions for shipping** (e.g. Europe), or both. These are separate alternatives, not intersecting filters. Blank areas mean no preference. Use additional instructions for the delivery destination, marketplaces, condition or response language.
4. Click **Search for this part**. The vehicle, description, instructions and all current photos are saved as a snapshot and queued for the background worker.
5. **Search history** updates automatically every four seconds while a search is queued or running, without clearing the form. When idle it checks every 15 seconds, including for searches started in another tab. Hidden tabs pause polling and network errors retry with backoff. **Refresh status** remains available only as a manual fallback; clicking it is not required.

Both providers are prompted to answer in Markdown. Responses render headings, bold text, lists, tables and blue clickable links, including older saved answers. Raw HTML and Markdown images are disabled, and unsafe link schemes are rejected. Results appear when the provider finishes; this is status polling, not token streaming.

New research asks both providers for a JSON envelope containing a Markdown summary and up to 20 structured listings. Cards display seller links, price/currency, description, location, condition, pickup/shipping availability, shipping cost and compatibility notes. Missing details are marked unconfirmed; the app does not independently verify AI-reported listings. Invalid listing URLs are discarded. If a provider ignores the structure, its original answer remains visible as Markdown. Existing answers are not automatically reprocessed.

The research prompt treats request photos as the visual reference and asks the provider to inspect candidate listing photos, compare mounting points and other distinguishing details, and check exact vehicle variants, brakes and part references. Known mismatches must be excluded. Cards show AI-reported photo-comparison status, observations and version checks. This is not an independent vision-verification pipeline: image access depends on the provider's tools. Missing image access must be disclosed as **Not checked**, and visual similarity alone never confirms fitment. These instructions apply to new searches, not past answers.

When the provider finds a direct HTTPS product photo URL on a listing, the browser loads it with no referrer. The external image host still sees the visitor's IP address. Missing or blocked photos have a fallback; there is no server-side scraping or image proxy, and the app never guesses image URLs. Product images are separate from the Markdown renderer, where embedded images remain disabled.

Only one search per request can be active at a time. Searches across requests are processed in order. Editing a request later does not change the inputs of an existing search. Failed searches keep their error in the history; start a new search to retry.

Codex uses the entered model ID (passed as `--model`), or its default when empty, attached image files and live web search in non-interactive mode. Shell execution and unrelated integrations are disabled. It runs in a temporary directory with a read-only sandbox and without the application's database credentials in its environment. User configuration and execution rules are not loaded for these runs. [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive).

Both providers save queued, running, completed and failed searches in the same history, including the selected model and price/location preferences. Direct CLI commands outside the app are not imported into this history. Existing history is preserved when the new preference columns are added automatically at startup.

For a specific Codex model, **Reasoning effort** lists its supported levels from the local catalogue (for example Low, Medium, High or Xhigh). **Model default** leaves the setting to Codex. Unsupported combinations are rejected before queueing. The chosen effort is passed using `model_reasoning_effort` and saved in search history. Higher effort may increase latency and usage. These controls are hidden for Open WebUI.

Open WebUI needs a model that supports vision for photos and native tool calling for research. Enable web search and configure a search engine in Open WebUI. The connector creates a conversation, starts server-side tool execution with web search enabled, waits for completion and retrieves the answer. The conversation remains available through **Open conversation in Open WebUI**. API permissions must allow `/api/config`, `/api/models`, `/api/v1/chats`, `/api/chat/completions` and `/api/tasks`. [Open WebUI server-side tool calling](https://docs.openwebui.com/reference/server-side-tool-calling/).

Research uses at most three rounds, each with a 10-minute execution limit and a 30-minute overall budget (HTTP/cancellation overhead can add a few seconds). It stops early at the requested new-listing count, when a follow-up brings no new listings, when web-search evidence is absent, or when reported usage reaches 24,000 tokens. The token budget is checked between rounds and can be exceeded by an individual provider round; it is not a hard billing cap. Missing provider usage is labelled explicitly. Open WebUI receives a 5,000-token response limit and its active task is cancelled when a round times out. Individual HTTP requests retain a 30-second network timeout (connection checks use 10 seconds). `SEARCH_TIMEOUT_SECONDS` is no longer used. On a worker restart, interrupted jobs are marked failed instead of automatically repeated. An Open WebUI task may still be running remotely after a connection failure or worker restart; inspect its conversation before retrying.

Each round searches configured priority websites and the open web, with instructions to use at most six search queries (at least two unrestricted) and eight new listing-page visits. These tool-use counts are prompt guidance; the round and time limits are enforced by the application. Later rounds receive compact query/reference notes, missing evidence and newly found URLs, rather than full prior transcripts. Codex uses a strict JSON output schema; both providers share server-side validation, fitment/availability ranking and exclusion filtering. Search history shows rounds, new/filtered counts, reported usage and the stopping reason. Partial results survive a later-round failure.

The app requests web search, but model capability and provider configuration determine whether it actually happens. Results explicitly state when the provider supplied no search evidence. Check seller links, price, availability and compatibility before ordering. The app does not buy parts or contact sellers.

Worker logs:

```sh
docker compose logs -f worker
```


## Discord notifications and listing rejection

Open **Discord** in the sidebar. Create a Discord application and bot in the [Developer Portal](https://discord.com/developers/applications). Install it on your server with the `bot` and `applications.commands` scopes and the **View Channels**, **Send Messages**, **Embed Links** and **Read Message History** permissions. No Message Content intent or public inbound endpoint is needed.

Enable Discord Developer Mode, then copy a text channel ID and your own user ID into the settings page. Save the bot token there; it is encrypted using the existing persistent application encryption key and is never rendered back into the page. Only the configured user in the configured channel can run bot commands or use rejection buttons. An optional application URL adds a link to each request; use an address accessible from your phone. **Test connection** only checks credentials and channel access, without sending a message. Enable channel notifications on your phone.

Each weekly schedule has its own **Discord notifications** switch, off by default. It can be set when creating schedules or changed independently on an existing slot. Scheduled jobs snapshot that preference. The sender also checks the current switch before delivery: turning it off or deleting the schedule suppresses remaining deliveries. Disabling the global bot pauses the delivery queue. Manual searches and searches without new eligible listings do not generate notifications.

The separate `discord` Docker service sends one message per new piece, with price, seller, location, shipping information and listing links. A PostgreSQL outbox is committed with completed research results. Network/server errors and rate limits are retried with backoff (up to five consecutive attempts per piece); permanent failures appear under **Recent deliveries** with a **Retry** button. Successfully recorded messages are not resent. A stable Discord nonce suppresses short-term duplicates after an interrupted send; Discord only guarantees nonce deduplication for a few minutes, so a crash after remote delivery but before the local commit can still produce a duplicate after a long outage. Notification failures never change completed searches to failed. Restarts preserve the queue and the controls on previously sent messages.

**Reject** opens a private confirmation with **Confirm rejection** and **Cancel**. Only confirmation adds the URL to the same request-scoped blacklist used by the web UI. Confirmation expires after five minutes and cannot be reused. Future research excludes that URL, including normalized tracking variants. Restore a rejected listing from **Parts Found → Blacklist** in the application.

Commands, available in the configured server/channel:

- `/requests`: the latest 10 requests.
- `/schedules`: the next 10 schedule slots and their Discord preferences.
- `/help`: available commands and actions.

These commands are read-only and do not call an AI model. Bot configuration changes reconnect automatically. Keep Docker running to receive alerts and use the buttons.


## Persistence and backups

| Docker volume | Contents |
| --- | --- |
| `postgres_data` | Requests, photos, search history and input snapshots, AI settings and encrypted Open WebUI API keys. |
| `app_secrets` | Random encryption key used to protect saved API keys. |
| `codex_auth` | Codex authentication session. |

All volumes persist with `make down`. Include all three in backups. Losing `app_secrets` requires entering API keys again. **`make remove` and `docker compose down -v` delete the volumes and their contents.**

## Project structure

Paths below are relative to the repository root:

```text
api/
  src/             Flask routes, business logic, integrations and background workers
  db/              PostgreSQL schema and additive migrations
  tests/           Python unit and integration tests
  docs/            Architecture, workflows and implementation notes
  requirements.txt Python dependencies
frontend/
  src/             React pages, shadcn components, styles and typed helpers
  templates/       React HTML entry point
  static/          Built React assets and favicon
  tests/           JavaScript merge tests
  e2e/             Browser integration and accessibility tests
  package.json     React dependencies and build/watch commands
  Makefile         Frontend check, test and build commands
  README.md        Frontend structure and development notes
Dockerfile         Application image, including the React production build
compose.yaml       Application services and PostgreSQL
Makefile           Service management and test commands
.dockerignore      Docker build exclusions
.env.example       Configuration example
README.md          Application setup and usage
```

Flask serves the React entry point with a safely escaped page-data payload and resolves hashed assets through the Vite manifest. React renders every screen; existing form actions, CSRF checks and URLs are preserved. Frontend paths resolve from the source file location, so asset loading does not depend on the working directory. Public URLs, including `/static/`, stay the same. `api/src/init_db.py` likewise resolves `api/db/init.sql` from its own location.

`compose.yaml` uses the repository root as its build context and keeps the Compose project name `r19finder`, preserving the existing named volumes. If you previously used a custom project name, continue passing the same `-p` option or `COMPOSE_PROJECT_NAME`.

Shared build, service configuration and project documentation live at the root. Backend and frontend files live under `api/` and `frontend/`.

## Routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Paginated request list. |
| GET | `/requests/new` | New request form. |
| POST | `/requests` | Create a request using multipart form data and a CSRF token. |
| GET | `/requests/<uuid>` | Request details. |
| GET / POST | `/requests/<uuid>/edit` | Edit a request and its photos. |
| POST | `/requests/<uuid>/search` | Queue a part search with a provider/model and optional instructions. |
| POST | `/requests/<uuid>/search/models` | Refresh available Open WebUI models. |
| GET | `/photos/<uuid>` | Retrieve a photo. |
| GET | `/ai` | AI connection settings. |
| POST | `/ai/openwebui` | Save Open WebUI settings. |
| POST | `/ai/<provider>/test` | Check `codex` or `openwebui`. |
| GET | `/health` | Application and database health. |

URLs are now in English. Update any bookmarks that used the previous Portuguese routes.

## Tests

With the containers running, from the repository root:

```sh
make test-api
```

Run all tests with `make test` (requires Node.js and `npm --prefix frontend ci`). See [frontend development and browser tests](frontend/README.md) for the local watch workflow and isolated browser suite. Use `make test-api` or `make test-frontend` to run each suite separately.

For local Python development, install `api/requirements.txt` in a virtual environment and export `DATABASE_URL` and `SECRET_KEY`. With an initialized test database, run `PYTHONPATH=src python -m unittest discover -s tests` from `api/`.

Database changes made by tests are rolled back. AI tests use mocks and a local HTTP fixture, so they do not require provider credentials or perform paid inference.

## Current scope

This is a shared application without user authentication: visitors can view and edit requests and manage the global AI settings. Before exposing it publicly, add authentication and authorization, HTTPS, rate limits and backups. For large photo collections, consider object storage with references in PostgreSQL.

## Part profiles and Fill with AI

**New request** opens the **New part** form. Start with a description, optionally choose a car and add photos, then expand **Part details** to add references, alternative names, technical characteristics, other compatible vehicles and purchasing requirements. Lists accept multiple entries. Include the maker/type in references, units in measurements, and years, engine and restrictions in donor-vehicle entries. Quantity is independent of the number of search results.

Click **Fill with AI** and choose a Codex model or an Open WebUI model (including Ollama models exposed by that server). This uses the existing AI connections; it does not require a separate OpenAI or Ollama configuration. Images can be excluded for text-only models. The selected model must support images if they are included. Model vision/tool capabilities are not assumed; providers may reject unsupported inputs. Open WebUI enrichment uses a tool-free structured completion based on model knowledge; it does not browse. Codex can use web search. All AI facts start unverified. The Open WebUI transport follows its [chat completion API](https://docs.openwebui.com/reference/api-endpoints/).

AI fill saves a session-owned draft and queues a separate enrichment task. It sends the description, current facts, car specifications and selected photos to the chosen connection and may consume credits. The `enrichment` Compose service processes these jobs. Generation is serialized with the research worker to protect shared provider sessions, so a long sale search may delay enrichment. AI fill is one bounded generation per click; failures are not automatically regenerated.

Suggestions fill empty fields or add list entries. Existing values and edits made during generation are preserved; conflicting suggestions appear with **Keep mine** and **Use suggestion as unverified**. Review highlighted suggestions before **Create part** or **Save changes**. Acceptance is not proof of compatibility: **I have confirmed this fact** is a separate user decision. Source links are citations reported by the model, not independently verified evidence. The AI cannot decide purchase quantity or acceptable alternatives.

**Save draft** retains fields and normalized photos for seven days after the last save. The form address includes its draft ID and **Resume draft** restores it in the same browser session. A draft URL does not grant another session access. Unsaved edits still require saving; clearing browser cookies loses draft access. Errors leave the form available. Cancelling prevents application of late results; the worker attempts to stop an active provider task, but remote cancellation is not always confirmable.

Creating the part is idempotent and does not start a sale search or send a Discord notification. Subsequent manual and scheduled searches snapshot the saved part profile. Names, references and possible donor vehicles widen discovery; unverified compatibility remains a lead, never proof that an advertised part fits. Existing requests with no profile continue to work, and manual entry remains available without JavaScript.

AI fill progress reports the selected model, elapsed time, queue position and the last status check. Queue messages distinguish another AI fill, an active sale search using the shared connection, a delayed pickup and an unresponsive AI service. During execution, the panel reports preparation, connection checks, generation and validation; it does not invent a completion percentage. Worker availability is based on a heartbeat every five seconds (considered stale after 25 seconds). Advisory lock IDs for enrichment and generation are distinct from Discord's lifetime and configuration locks.

## Search languages and exact part identifiers

Open **Settings** to choose an **AI response language** and one or more **Search languages**: English, Portuguese, French, German and Spanish. All five search languages are enabled initially. Menus/buttons remain in English. AI explanations use the response language, while names and queries cover the selected search languages. Codes, manufacturers, URLs and quoted source text retain their original spelling. Languages do not restrict seller countries.

Preferences are shared by this installation. Each new AI fill or reference-research task snapshots them when queued. Manual and scheduled sale searches snapshot the current preferences when enqueued; a weekly schedule therefore uses the latest preferences at its next occurrence. Existing results and jobs already queued keep their snapshots. Research rounds receive an explicit language plan, with the order rotated in later rounds within the existing query budget.

Under **References**, click **Research exact identifiers** to investigate this specific part using the selected connection and photos. It looks for OEM, manufacturer, casting, catalogue and supersession codes, matching the component, side, phase, body, years and relevant physical features. Codex uses live research; Open WebUI requires configured web search and a model capable of using tools. This action never silently falls back to model memory.

AI reference proposals require a concrete identifier and source notes from a run that reported web research. Unsupported references are omitted and the review explains what information is missing. A proposed reference records its code, type, manufacturer, matched characteristics, unresolved checks and sources. A source-backed candidate remains **unverified** until the user confirms it; unresolved fitment or sources absent from tool reports downgrade it to a candidate. This is not independent catalogue verification.

Ordinary **Fill with AI** also investigates identifiers with Codex and generates names in the selected search languages. Open WebUI's ordinary fill uses model knowledge for names/details and cannot add reference codes without research evidence; use **Research exact identifiers** for those. Existing manually entered references are preserved, and new findings go through the same review before saving.
