#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

cleanup() {
  docker compose --env-file /dev/null -f docker-compose.test.yml -p puppycat-test down
}

trap cleanup EXIT

docker compose --env-file /dev/null -f docker-compose.test.yml -p puppycat-test up -d --wait

(
  cd apps/api
  export DATABASE_URL="postgresql+asyncpg://puppycat_test:puppycat_test@127.0.0.1:5433/puppycat_test"
  export JWT_SECRET="test-only-jwt-secret-at-least-32-bytes"
  export SIGNUP_CODE="test-signup-code"
  python -m alembic upgrade head
  python -m pytest
)

(
  cd apps/web
  npm run typecheck
  npm run build
)
