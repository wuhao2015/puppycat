# Puppycat Travel

Puppycat Travel is being rebuilt as a small travel-planning application. This repository currently contains the Phase 0 foundation only: a minimal Next.js page, a FastAPI health endpoint, PostgreSQL, Docker Compose, and Vercel configuration.

## Project layout

```text
apps/
  api/   FastAPI application
  web/   Next.js application
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
uvicorn app.main:app --reload --port 8001
```

The web application requires Node.js 20.9 or newer:

```bash
cd apps/web
npm ci
npm run dev
```

When both applications run directly on the host, Next.js forwards `/api/*` requests to `http://localhost:8001` by default.

## Vercel

Create a Vercel project with `apps/web` as its root directory. The included `vercel.json` uses the standard Next.js build and sets the framework explicitly. Configure production environment variables in Vercel rather than committing them.
