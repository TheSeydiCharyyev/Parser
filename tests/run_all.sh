#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Build (only if needed) =="
# Users can skip rebuild if containers already up-to-date.
docker compose build backend scheduler >/dev/null

echo "== Backend tests =="
docker compose exec -T backend python manage.py test

echo "== Scheduler unit tests =="
docker compose exec -T scheduler python -m unittest discover -s tests -p 'test_*.py' -v

echo "== OK =="
