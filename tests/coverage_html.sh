#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p artifacts/coverage/backend artifacts/coverage/scheduler

echo "== Build (only if needed) =="
docker compose build backend scheduler >/dev/null

echo "== Backend coverage =="
docker compose exec -T backend bash -lc "coverage run manage.py test && coverage html -d /tmp/htmlcov-backend && coverage xml -o /tmp/coverage-backend.xml"
docker compose exec -T backend bash -lc "rm -rf /tmp/htmlcov-backend/.gitkeep 2>/dev/null || true"
docker compose cp backend:/tmp/htmlcov-backend artifacts/coverage/backend/htmlcov
docker compose cp backend:/tmp/coverage-backend.xml artifacts/coverage/backend/coverage.xml

echo "== Scheduler coverage =="
docker compose exec -T scheduler bash -lc "coverage run -m unittest discover -s tests -p 'test_*.py' && coverage html -d /tmp/htmlcov-scheduler && coverage xml -o /tmp/coverage-scheduler.xml"
docker compose cp scheduler:/tmp/htmlcov-scheduler artifacts/coverage/scheduler/htmlcov
docker compose cp scheduler:/tmp/coverage-scheduler.xml artifacts/coverage/scheduler/coverage.xml

echo "== Done =="
echo "Backend:   artifacts/coverage/backend/htmlcov/index.html"
echo "Scheduler: artifacts/coverage/scheduler/htmlcov/index.html"
