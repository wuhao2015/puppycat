# Puppycat Travel

Puppycat Travel is being rebuilt as a small travel-planning application. The current application includes the Puppycat visual shell, account authentication, Trip management, and persisted Trip-scoped chat history. Gemini is intentionally not connected yet, so the UI saves user messages and shows the current development status without creating fake assistant replies.

## Project layout

```text
apps/
  api/
    app/       FastAPI configuration, database models, auth, and Trip APIs
    tests/     PostgreSQL-backed API integration tests
    alembic/   Initial PostgreSQL migration
  web/         Next.js visual shell, authentication state, and account pages
docker-compose.yml
```

Registration uses the configured `SIGNUP_CODE`. After registering or signing in, the browser stores the access token locally, restores the account on refresh, and sends the token to protected API routes. The Profile page edits the display name and passport country codes.

An authenticated user can create a Trip by sending the first message, reopen it at `/trips/{trip_id}`, rename or delete it from the Sidebar, and recover saved messages after a refresh. Every Trip read and mutation is scoped to its owner.

The implemented Trip API surface is:

- `POST /api/trips`
- `GET /api/trips`
- `GET /api/trips/{trip_id}`
- `PATCH /api/trips/{trip_id}`
- `DELETE /api/trips/{trip_id}`
- `POST /api/trips/{trip_id}/chat`

## Start with Docker Compose

Docker is the only local prerequisite for the complete stack.

```bash
docker compose up --build
```

Then open:

- Web: http://localhost:3000
- API health: http://localhost:8001/health
- PostgreSQL: localhost:5432

The Compose defaults are safe for local development. Copy `.env.example` to `.env` only when you need to override them, and never commit real secrets.

## Run without Docker

The API requires Python 3.11 or newer:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

`alembic upgrade head` requires a running PostgreSQL instance and a matching `DATABASE_URL`. The API Docker image runs this migration automatically before starting Uvicorn.

The web application requires Node.js 20.9 or newer:

```bash
cd apps/web
npm ci
npm run dev
```

When both applications run directly on the host, Next.js forwards `/api/*` requests to `http://localhost:8001` by default.

## Run API tests

The integration tests use an isolated PostgreSQL database on port 5433 and never load the project `.env` file:

```bash
docker compose --env-file /dev/null -f docker-compose.test.yml -p puppycat-test up -d --wait
cd apps/api
pip install -e '.[test]'
DATABASE_URL=postgresql+asyncpg://puppycat_test:puppycat_test@127.0.0.1:5433/puppycat_test \
JWT_SECRET=test-only-jwt-secret-at-least-32-bytes \
SIGNUP_CODE=test-signup-code \
alembic upgrade head
DATABASE_URL=postgresql+asyncpg://puppycat_test:puppycat_test@127.0.0.1:5433/puppycat_test \
JWT_SECRET=test-only-jwt-secret-at-least-32-bytes \
SIGNUP_CODE=test-signup-code \
pytest
cd ../..
docker compose --env-file /dev/null -f docker-compose.test.yml -p puppycat-test down
```

## Vercel

Create a Vercel project with `apps/web` as its root directory. The included `vercel.json` uses the standard Next.js build and sets the framework explicitly. Configure production environment variables in Vercel rather than committing them.
