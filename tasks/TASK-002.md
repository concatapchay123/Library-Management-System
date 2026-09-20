# TASK-002 — Project foundation

## Task Information

- ID: TASK-002
- Name: Flask/React foundation, Compose and CI
- Priority: P0 — blocking

## Objective

Create the smallest runnable project foundation: Flask app factory, React TypeScript app, SQL Server migration bootstrap, Docker Compose services, configuration validation and CI jobs.

## Scope

Create `backend/`, `frontend/`, `infra/`, `contracts/openapi/` and `.github/workflows/`. Implement health endpoints and initial database connection only. Do not implement business modules.

## Files affected

- Create: `backend/pyproject.toml`, `backend/src/openlibrary/app/`, `backend/tests/`
- Create: `frontend/package.json`, `frontend/src/`, `frontend/tests/`
- Create: `infra/docker-compose.yml`, `infra/nginx/`, `.env.example`
- Create: `contracts/openapi/v1.yaml`, `.github/workflows/ci.yml`

## Implementation steps

1. Write a failing app-start and `/health/live` test.
2. Run it and confirm failure because the app factory does not exist.
3. Implement `create_app(config)` and the live/readiness routes.
4. Write a failing frontend build smoke test and minimal render entrypoint.
5. Add SQL Server/Redis configuration, Compose healthchecks and migration command.
6. Add CI jobs for Python checks, frontend checks, OpenAPI lint and Compose config validation.
7. Run focused tests, then the full Phase 1 checkpoint commands.

## Dependencies

TASK-001.

## Testing checklist

- [ ] Flask app factory test passes.
- [ ] `/health/live` does not require database connectivity.
- [ ] `/health/ready` reports dependency failure correctly.
- [ ] Frontend strict type-check and production build pass.
- [ ] SQL Server migration runs from a clean database.
- [ ] `docker compose config` passes.
- [ ] CI workflow syntax validates.

## Acceptance criteria

- `docker compose up` starts app, database, Redis, worker and Nginx with healthchecks.
- Backend and frontend have deterministic local commands.
- No secret is committed; `.env.example` contains names only.
- CI fails on lint/type/test/build failure.

## Reviewer checklist

- [ ] App factory has no import-time network connection.
- [ ] Compose does not expose SQL Server or Redis publicly by default.
- [ ] Health endpoints do not leak credentials or stack traces.
- [ ] CI uses pinned or explicitly controlled tool versions.
