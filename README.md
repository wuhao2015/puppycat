# Puppycat Travel

Puppycat Travel is a full-stack travel-planning application. Users keep a Trip
conversation, generate a verified daily itinerary in the background, review a
Visa checklist grounded in official sources, and download a concise visa
itinerary PDF.

## Architecture

```text
Browser
  └─ Next.js web (`apps/web`, port 3000)
       └─ `/api/*` rewrite
            └─ FastAPI (`apps/api`, host port 8001 / container port 8000)
                 ├─ PostgreSQL 16 (Trips, itineraries, jobs, cache)
                 ├─ Gemini (chat, extraction, itinerary and visa structuring)
                 ├─ Google Places (destination and place verification)
                 ├─ Tavily (official visa-source discovery)
                 └─ Open-Meteo (per-day forecast)
```

The API owns authentication, authorization, persistence, external calls, and
PDF rendering. The web stores the access token in the browser and uses the
Next.js `/api` rewrite for every API request. Authentication responses use
`Cache-Control: no-store`.

Plan generation is an asynchronous, idempotent job. `POST /plan` returns a
queued job immediately; API workers generate the itinerary and the active Trip
page polls only while it is queued or running. Gemini latency therefore does
not hold the Create/Update Plan button open, and completed plans survive page
navigation and refresh.

## Requirements

Docker Compose is the only prerequisite for the complete local stack.

For non-Docker development, use Python 3.11+, Node.js 24+, npm, and PostgreSQL
16.

## Configuration

Copy the example only when you need to override Compose defaults:

```bash
cp .env.example .env
```

Never commit `.env` or real API keys. The API starts without external keys, but
chat and itinerary generation require Gemini. Places, Tavily, and Mapbox
features degrade gracefully when their optional keys are absent.

| Variable | Required | Purpose |
| --- | --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Docker | PostgreSQL credentials and database name. |
| `JWT_SECRET` | Production | Long random secret for access-token signing. |
| `JWT_ALGORITHM` | No | JWT algorithm; default `HS256`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Token lifetime; default `10080` (7 days). |
| `SIGNUP_CODE` | Production | Private registration code. |
| `GEMINI_API_KEY` | Chat/planning | Gemini API key. |
| `GEMINI_DEFAULT_MODEL` | No | Preferred Gemini model before fallback discovery. |
| `GOOGLE_PLACES_API_KEY` | Place verification | Google Places API key. |
| `TAVILY_API_KEY` | Visa sources | Tavily API key. |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Map | Public Mapbox token embedded during web build. |
| `CORS_ALLOW_ORIGINS` | Direct API browser access | Comma-separated allowed origins. |
| `API_HTTP_PROXY`, `API_HTTPS_PROXY`, `API_NO_PROXY` | No | API-container outbound proxy settings. |

`API_INTERNAL_BASE_URL` is not needed by Docker Compose: Compose fixes the
web-to-API address at `http://api:8000`. It is used when the web is deployed
separately, such as on Vercel.

## Start with Docker Compose

From the repository root:

```bash
docker compose up --build
```

The API container runs `alembic upgrade head` before Uvicorn starts, so a fresh
database is migrated automatically. Open:

- Web: <http://127.0.0.1:3000>
- API health: <http://127.0.0.1:8001/health>
- API OpenAPI docs: <http://127.0.0.1:8001/docs>
- PostgreSQL from the host: `127.0.0.1:5432`

The mapping `8001:8000` means the API listens on port 8000 inside its container
and is exposed as 8001 only to the host. The web container reaches `api:8000`
over the Compose network; it does not use host port 8001.

For a repeatable container check after configuring services, run:

```bash
bash scripts/smoke.sh
```

It builds and starts Compose, checks API health and the web page, and confirms
that a web `/api` request reaches the API by expecting an unauthenticated 401.

## Run without Docker

Start PostgreSQL and set `DATABASE_URL`, `JWT_SECRET`, and `SIGNUP_CODE` in
your shell (or a local, uncommitted `.env`). Then start the API:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

Start the web in a second terminal:

```bash
cd apps/web
npm ci
npm run dev
```

For direct host development, the Next.js rewrite defaults to
`http://localhost:8001`.

## API surface

All `/api` routes except registration and login require a bearer token. A user
can only read or mutate their own Trips.

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Register with `SIGNUP_CODE`. |
| `POST` | `/api/auth/login` | Sign in and receive a bearer token. |
| `GET` | `/api/auth/me` | Restore the authenticated user. |
| `PATCH` | `/api/auth/profile` | Update display name and passport countries. |
| `POST` | `/api/trips` | Create a Trip. |
| `GET` | `/api/trips` | List the current user's Trips. |
| `GET` | `/api/trips/{trip_id}` | Read chat, itinerary, and generation state. |
| `PATCH` | `/api/trips/{trip_id}` | Rename a Trip. |
| `DELETE` | `/api/trips/{trip_id}` | Delete a Trip and related records. |
| `POST` | `/api/trips/{trip_id}/chat` | Stream a Gemini response as NDJSON. |
| `POST` | `/api/trips/{trip_id}/plan` | Queue a plan job (`202 Accepted`). |
| `GET` | `/api/trips/{trip_id}/visa` | Get grounded Visa checklists. |
| `POST` | `/api/trips/{trip_id}/documents/itinerary` | Download the latest itinerary PDF. |
| `GET` | `/health` | Unauthenticated process health check. |

## Test and verification

Install API test dependencies and web dependencies once for the non-Docker
workflow, then run:

```bash
bash scripts/test.sh
```

The script starts an isolated `puppycat_test` PostgreSQL on port 5433 with
`--env-file /dev/null`; it never loads the project `.env`. It applies all
migrations, runs the API suite, type-checks the web application, builds the
production web bundle, and stops the isolated test database on exit.

Before release, perform one manual end-to-end smoke test with real configured
services:

1. Register, sign in, and add a passport country in Settings.
2. Create a Trip, chat, and refresh to confirm persistence.
3. Create a plan, navigate away if desired, then return after completion.
4. Review Guide notices, daily city/country, weather, accommodation, and
   intercity transport.
5. Open the Visa checklist and confirm its official-source links.
6. Download the itinerary PDF and verify its date/city/accommodation/transport
   table.

## Vercel web deployment

Deploy `apps/web` as the Vercel project root. The included
[`vercel.json`](apps/web/vercel.json) selects the Next.js build. Configure:

- `API_INTERNAL_BASE_URL`: publicly reachable HTTPS URL of the separately
  deployed API, without a trailing `/api`.
- `NEXT_PUBLIC_MAPBOX_TOKEN`: optional Mapbox public token, set before build.

`apps/web/next.config.mjs` rewrites `/api/:path*` server-side to
`${API_INTERNAL_BASE_URL}/api/:path*`, so the browser continues to use
same-origin `/api` calls, including streamed chat. Plan queuing returns `202`
instead of waiting for Gemini, so it remains within Vercel request-duration
limits.

Deploy the API and PostgreSQL separately, run `alembic upgrade head` as part of
that deployment, set production secrets there, and set `CORS_ALLOW_ORIGINS`
only when a browser accesses the API directly.
