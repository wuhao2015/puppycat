# Puppycat Travel

Puppycat Travel is being rebuilt as a small travel-planning application. The current foundation includes the Puppycat visual shell, FastAPI configuration, the initial PostgreSQL schema, and a concrete PostgreSQL cache. Authentication and trip APIs are not implemented yet.

## Project layout

```text
apps/
  api/
    app/       FastAPI configuration, database session, and models
    alembic/   Initial PostgreSQL migration
  web/         Next.js visual shell and static pages
docker-compose.yml
```

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

## Vercel

Create a Vercel project with `apps/web` as its root directory. The included `vercel.json` uses the standard Next.js build and sets the framework explicitly. Configure production environment variables in Vercel rather than committing them.
