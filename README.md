# Puppycat Travel App

A cost-conscious, single-user-first AI travel itinerary app. Its defining feature is a
**real-time verification pass**: before an itinerary is returned, every planned venue is
re-checked against live opening hours, one-off closures, transit strikes, local events, and
weather for the specific date you plan to visit. The app surfaces reservation deep-links
(it never books on your behalf), generates visa guidance, and produces downloadable trip
and visa documents.

It is built for one user (you) but models `user_id` everywhere and hides infrastructure
behind swappable interfaces, so growing to more users is a configuration change rather than
a rewrite.

## Architecture

```
puppycat/
├── apps/
│   ├── web/          # Next.js 15 frontend (chat + itinerary + map + PDF download)
│   └── api/          # FastAPI backend (pipeline, datasources, documents)
├── docker-compose.yml
├── .env.example
└── README.md
```

The backend runs a **deterministic pipeline** for itinerary generation rather than a
free-roaming agent:

```
parse intent -> fetch candidate POIs -> draft plan -> real-time verification -> re-rank -> documents
```

A lighter tool-calling path powers the free-form chat experience and reuses the same data
sources.

### Data sources

| Source | Purpose | Notes |
|---|---|---|
| Google Places API (New) | POIs, `business_status`, opening hours, website, lat/lng | Primary structured source |
| Web search (Tavily default, Brave alt) | Freshness: closures, strikes, events, advisories | Short-TTL cached |
| Open-Meteo | Weather forecast for trip dates | Free, no key |
| Visa (web search + curated JSON) | Visa requirements, fees, processing times | Advisory only, verify officially |

Redis and pgvector are intentionally **not** used in v1 (no corpus to justify them).
`CacheBackend` and `DataSource` interfaces leave room to add them later.

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
# edit .env and fill in OPENAI_API_KEY, GOOGLE_PLACES_API_KEY, TAVILY_API_KEY, etc.
```

### 2. Run with Docker (recommended)

```bash
docker compose up --build
```

This starts Postgres, the FastAPI backend (http://localhost:8001), and the Next.js
frontend (http://localhost:3000).

### 3. Run locally without Docker

Backend:

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

Frontend:

```bash
cd apps/web
npm install
npm run gen:types   # generate TS types from the backend OpenAPI schema
npm run dev
```

## API surface

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | signup code | Create an account (invite-only) and receive a JWT |
| `POST` | `/api/auth/login` | — | Exchange email + password for a JWT |
| `GET`  | `/api/auth/me` | Bearer | Current authenticated user |
| `POST` | `/api/itinerary` | Bearer | Generate a verified day-by-day itinerary |
| `GET`  | `/api/trips` | Bearer | List the current user's saved trips |
| `GET`  | `/api/itineraries/{id}` | Bearer | Fetch one of the user's saved itineraries |
| `POST` | `/api/visa-checklist` | Bearer | Visa requirements + document checklist |
| `POST` | `/api/chat` | Bearer | Streaming conversational planner |
| `POST` | `/api/documents/itinerary` | Bearer | Render itinerary PDF |
| `POST` | `/api/documents/visa` | Bearer | Render visa checklist PDF |
| `POST` | `/api/documents/cover-letter` | Bearer | Render proof-of-travel / cover letter PDF |
| `GET`  | `/health` | — | Liveness probe |

All app endpoints require an `Authorization: Bearer <jwt>` header. Obtain a token via
`/api/auth/register` (requires the shared `SIGNUP_CODE`) or `/api/auth/login`. Each user
only sees their own trips and itineraries.

Interactive docs are available at http://localhost:8001/docs once the backend is running.

## Disclaimer

Visa guidance and "is it open today" checks are best-effort and assembled from third-party
sources. Always confirm with official government and venue sources before you travel.
