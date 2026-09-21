#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose up --build -d

for _attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:8001/health >/dev/null; then
    break
  fi
  sleep 2
done

curl --fail --silent --show-error http://127.0.0.1:8001/health >/dev/null
curl --fail --silent --show-error http://127.0.0.1:3000/ >/dev/null

status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:3000/api/auth/me)"
if [ "$status" != "401" ]; then
  echo "Expected the web /api rewrite to return 401 from /api/auth/me; got $status." >&2
  exit 1
fi

echo "Puppycat smoke check passed."
