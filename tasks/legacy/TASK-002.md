# TASK-002 — Project foundation

## Task Information

- ID: TASK-002
- Name: Flask/React foundation, Compose and CI
- Priority: P0 — blocking

## Objective

Create the smallest runnable project foundation: Flask app factory, React TypeScript app, SQL Server migration/bootstrap, control-plane organization registry, audit/outbox primitives, Docker Compose services, configuration validation and CI jobs.

## Scope

Create `backend/`, `frontend/`, `infra/`, `contracts/openapi/` and `.github/workflows/`. Implement health endpoints, initial database connection, RLS-protected `core.organizations`, security-definer `core.resolve_login_tenant`, `ops.audit_events`, `ops.outbox_events`, the shared fail-closed RLS predicate and separate migration/runtime database configuration. Do not implement business modules or public organization-management endpoints.

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
6. Write failing migration integration tests for missing tenant context, unauthorized direct pre-login organization query and unavailable runtime DDL/RLS privileges; implement the shared predicate, security-definer login resolver, RLS-protected root registry and audit/outbox schema.
7. Add CI jobs for Python checks, frontend checks, OpenAPI lint, Compose config validation and database-role/RLS catalog checks.
8. Run focused tests, then the full Phase 1 checkpoint commands.

## Dependencies

TASK-001.

## Testing checklist

- [ ] Flask app factory test passes.
- [ ] `/health/live` does not require database connectivity.
- [ ] `/health/ready` reports dependency failure correctly.
- [ ] Frontend strict type-check and production build pass.
- [ ] SQL Server migration runs from a clean database.
- [ ] Runtime database identity cannot alter schema or RLS policy.
- [ ] Missing tenant context fails closed for organization, audit/outbox tenant rows; resolver login là pre-context procedure duy nhất được grant hẹp.
- [ ] Audit/outbox foundation migration is reversible or has a documented forward-only reason.
- [ ] `docker compose config` passes.
- [ ] CI workflow syntax validates.

## Acceptance criteria

- `docker compose up` starts app, database, Redis, worker and Nginx with healthchecks.
- Backend and frontend have deterministic local commands.
- No secret is committed; `.env.example` contains names only.
- CI fails on lint/type/test/build failure.
- Pre-login organization lookup is limited to `core.resolve_login_tenant`; `core.organizations` remains RLS-protected for authenticated tenant access and is not a tenant-user listing API.

## Reviewer checklist

- [ ] App factory has no import-time network connection.
- [ ] Compose does not expose SQL Server or Redis publicly by default.
- [ ] Health endpoints do not leak credentials or stack traces.
- [ ] CI uses pinned or explicitly controlled tool versions.
- [ ] Migration and runtime identities are different; runtime is not `db_owner` and lacks DDL, `CONTROL`, `IMPERSONATE` and RLS-policy alteration rights.
