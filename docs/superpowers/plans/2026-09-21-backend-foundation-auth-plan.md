# Backend Foundation and Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and verify BE-002 through BE-010 with real SQL Server integration, secure tenant boundaries, authentication/session/RBAC behavior, and recorded evidence.

**Architecture:** Flask API adapters call application services, which depend on explicit infrastructure ports. SQL Server migrations own schemas, roles, RLS, stored procedures, and persistent security controls; the runtime identity is intentionally unable to alter them. Tests exercise the Compose SQL Server service for every database acceptance criterion and use the Flask test client only at the HTTP edge.

**Tech Stack:** Python 3.11, Flask 3, SQLAlchemy 2, Alembic/Flask-Migrate, pyodbc, SQL Server 2022, Redis 7, Celery, Argon2id, PyJWT/cryptography, pytest, Ruff, mypy, Docker Compose, OpenAPI 3.1 validation.

**Spec:** `docs/superpowers/specs/2026-09-21-backend-foundation-auth-design.md`

## Global Constraints

- Work only in this isolated worktree; do not change `main` directly.
- Every persistent tenant-owned table has `organization_id UNIQUEIDENTIFIER NOT NULL`, tenant-aware keys, and SQL Server RLS filter and block protection.
- `core.organizations` is RLS-protected; pre-auth tenant resolution occurs only through narrowly granted `EXECUTE AS OWNER` procedures.
- Migration and runtime SQL Server credentials are separate. Runtime is denied DDL, `CONTROL`, `IMPERSONATE`, ownership, and RLS-policy changes.
- Integration tests use the Compose SQL Server service, never SQLite or another database substitute.
- Protected routes derive organization context only from a verified principal. Passwords, secrets, tokens, and raw payment payloads never appear in database event payloads, logs, or API responses.
- Each task follows RED → GREEN → REFACTOR, records exact focused-command output in its task file, receives a task-scoped review, and commits independently.
- `rtk` is unavailable in this environment; run the underlying command directly and preserve its output in evidence.

## File map

- `backend/src/openlibrary/app/`: settings parsing, factory, API-wide Problem Details/request ID behavior.
- `backend/src/openlibrary/infrastructure/sqlserver/`: engines, transactions, tenant context, migrations and SQL Server ports.
- `backend/src/openlibrary/modules/core/{application,domain,infrastructure,api}/`: organization/login, audit/outbox, identity, JWT/session, and RBAC services.
- `backend/migrations/`: Alembic configuration and ordered SQL Server revisions.
- `backend/tests/{unit,integration,contract,api}/`: focused RED/GREEN evidence and full coverage.
- `infra/`: Compose topology, app/worker images, Nginx proxy, names-only environment template.
- `contracts/openapi/v1.yaml` and `.github/workflows/backend.yml`: machine contract and blocking CI gates.
- `tasks/backend/BE-00{2..9}.md`, `tasks/backend/BE-010.md`: append command, exit code, and concise sanitized evidence after each task.

### Task 1: BE-002 runtime configuration and Compose services

**Files:**
- Create: `backend/tests/integration/app/test_runtime_config.py`, `backend/src/openlibrary/app/runtime.py`, `backend/.env.example`, `infra/docker-compose.yml`, `infra/Dockerfile.backend`, `infra/nginx/default.conf`.
- Modify: `backend/src/openlibrary/app/config.py`, `backend/src/openlibrary/app/factory.py`, `backend/pyproject.toml`, `backend/README.md`, `tasks/backend/BE-002.md`.

**Interfaces:**
- Produces `RuntimeSettings.from_environ(environ: Mapping[str, str]) -> RuntimeSettings`, raising `ConfigurationError` for missing required values.
- Produces `create_runtime_app(settings: RuntimeSettings) -> Flask`; later tasks add dependencies through the settings object rather than global environment reads.

- [ ] **Step 1: Write the failing configuration tests.** Define an environment fixture containing all names-only required values; assert missing `APP_SECRET_KEY`, `DATABASE_RUNTIME_URL`, and `REDIS_URL` each raise `ConfigurationError`; assert `APP_ENV` defaults to `development` and secret values do not default.

```python
def test_missing_database_runtime_url_stops_app_creation() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_RUNTIME_URL"):
        RuntimeSettings.from_environ(required_environment_without("DATABASE_RUNTIME_URL"))
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/integration/app/test_runtime_config.py -q`; confirm import/behavior fails because `RuntimeSettings` is absent, then paste the sanitized failure summary under BE-002 Evidence checkpoint.
- [ ] **Step 3: Implement the smallest runtime boundary.** Add frozen `RuntimeSettings` with explicit settings names, no secret defaults, a settings-to-`AppConfig` adapter, and `create_runtime_app`. Add Compose services `database`, `redis`, `app`, `worker`, and `nginx`; place only app/nginx on public host ports, give every service a health check and `depends_on.condition: service_healthy`, and configure an internal network for database/Redis. Add names only to `.env.example`.
- [ ] **Step 4: Run GREEN and Compose validation.** Run `cd backend; python -m pytest tests/integration/app/test_runtime_config.py -q` and `docker compose -f infra/docker-compose.yml config`; verify exit 0, no exposed SQL Server/Redis port, health checks, and dependency order. Append both outputs and mark only verified checklist items in BE-002.
- [ ] **Step 5: Review and commit.** Review the diff for secret values and config fallbacks, run `git diff --check`, then commit `feat: add runtime configuration and local compose services`.

### Task 2: BE-003 SQL Server migrations and database identities

**Files:**
- Create: `backend/tests/integration/migrations/test_database_roles.py`, `backend/migrations/env.py`, `backend/migrations/versions/0001_database_identities.py`, `backend/src/openlibrary/infrastructure/sqlserver/migrate.py`, `backend/scripts/run_migrations.py`.
- Modify: `backend/pyproject.toml`, `backend/README.md`, `infra/docker-compose.yml`, `tasks/backend/BE-003.md`.

**Interfaces:**
- Produces `run_migrations(database_url: str) -> None` and `verify_runtime_restrictions(runtime_url: str) -> None`.
- Produces SQL Server principals `openlibrary_migrator` and `openlibrary_runtime`; later migrations execute only through the former.

- [ ] **Step 1: Write failing SQL Server integration tests.** Add a fixture that requires `DATABASE_MIGRATION_URL` and `DATABASE_RUNTIME_URL`, invokes the migration command against a clean Compose database, then asserts the runtime connection cannot execute `CREATE TABLE` or `ALTER SECURITY POLICY`.

```python
def test_runtime_identity_cannot_run_ddl(runtime_connection: Connection) -> None:
    with pytest.raises(DBAPIError):
        runtime_connection.execute(text("CREATE TABLE core.runtime_escape (id int NOT NULL)"))
```

- [ ] **Step 2: Run RED evidence against Compose SQL Server.** Start only required services with `docker compose -f infra/docker-compose.yml up -d database`; run `cd backend; python -m pytest tests/integration/migrations/test_database_roles.py -q`; record the failing absent-runner/role output in BE-003.
- [ ] **Step 3: Implement SQL Server-only migration bootstrap.** Add Alembic/Flask-Migrate and SQL Server dependencies; configure migration URL separately from runtime URL. The first revision creates `core`, `ops`, `education`, and `public_library`, creates/grants principals with explicit least privilege, denies runtime DDL/CONTROL/IMPERSONATE, and records migration version. Document the exact clean-database command in `backend/README.md`.
- [ ] **Step 4: Run GREEN evidence.** Recreate the named Compose database volume only after confirming its exact project-scoped target, start SQL Server, run the focused role test and `python scripts/run_migrations.py`; verify migration succeeds and both runtime DDL and policy alteration are denied. Append output to BE-003.
- [ ] **Step 5: Review and commit.** Inspect grants and catalog queries for least privilege, run `git diff --check`, and commit `feat: add sql server migration baseline and roles`.

### Task 3: BE-004 organization registry, RLS, and pre-login resolver

**Files:**
- Create: `backend/tests/integration/tenancy/test_prelogin_resolver.py`, `backend/migrations/versions/0002_organizations_rls.py`, `backend/src/openlibrary/modules/core/infrastructure/organizations.py`.
- Modify: `backend/src/openlibrary/infrastructure/sqlserver/migrate.py`, `tasks/backend/BE-004.md`.

**Interfaces:**
- Produces `resolve_login_tenant(connection: Connection, slug: str) -> LoginTenant | None`, where `LoginTenant` contains only `organization_id`, `slug`, and `status`.
- Produces `set_tenant_context(connection: Connection, organization_id: UUID) -> None` and `clear_tenant_context(connection: Connection) -> None`.

- [ ] **Step 1: Write failing RLS/resolver tests.** Seed two organizations through the migration identity; assert runtime direct reads with no context return no rows or fail, tenant A cannot read/mutate tenant B, an insert with B's ID under A context is blocked, and `resolve_login_tenant` returns no more than the documented fields.

```python
def test_runtime_can_discover_login_tenant_only_through_resolver(runtime: Connection) -> None:
    assert direct_organization_select(runtime, "campus-a") is None
    assert resolve_login_tenant(runtime, "campus-a").slug == "campus-a"
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/integration/tenancy/test_prelogin_resolver.py -q`; record missing policy/procedure failure in BE-004.
- [ ] **Step 3: Implement registry and policy migration.** Create `core.organizations`, schema-bound `core.tenant_access_predicate`, filter/block policy, and owner-executing `core.resolve_login_tenant`; grant only procedure execution before tenant context. Implement parameterized resolver/context helpers and ensure context clears when a connection returns to the pool.
- [ ] **Step 4: Run GREEN and catalog evidence.** Run the focused test plus a catalog assertion verifying both predicates protect `core.organizations`; append successful command output to BE-004.
- [ ] **Step 5: Review and commit.** Review procedure result columns, grants, `EXECUTE AS OWNER`, and both RLS predicates; commit `feat: add organization rls and login resolver`.

### Task 4: BE-005 transactional audit and outbox persistence

**Files:**
- Create: `backend/tests/integration/ops/test_audit_outbox.py`, `backend/migrations/versions/0003_audit_outbox.py`, `backend/src/openlibrary/modules/core/application/transactions.py`, `backend/src/openlibrary/modules/core/infrastructure/audit_outbox.py`.
- Modify: `tasks/backend/BE-005.md`.

**Interfaces:**
- Produces `AuditEvent(action: str, entity_type: str, entity_id: UUID, payload: Mapping[str, object])` and `OutboxEvent(topic: str, aggregate_type: str, aggregate_id: UUID, payload_version: int, payload: Mapping[str, object])`.
- Produces `TransactionalWriter.commit(mutation: Callable[[Connection], None], audit: AuditEvent, outbox: OutboxEvent, organization_id: UUID) -> None`.

- [ ] **Step 1: Write failing atomicity and redaction tests.** Assert a successful writer call creates one mutation, one audit record, and one outbox record; an injected exception creates none. Parameterize prohibited keys `password`, `token`, `secret`, and `raw_payment_payload` and expect payload rejection before persistence.

```python
def test_rollback_leaves_no_audit_or_outbox_records(writer: TransactionalWriter) -> None:
    with pytest.raises(RuntimeError):
        writer.commit(raising_mutation, audit_event(), outbox_event(), ORGANIZATION_A)
    assert count_events(ORGANIZATION_A) == (0, 0)
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/integration/ops/test_audit_outbox.py -q`; record absent transaction-record failure in BE-005.
- [ ] **Step 3: Implement append-only event storage.** Add RLS-protected `ops.audit_events` and `ops.outbox_events`, tenant indexes, payload version, correlation ID, server-derived organization ID, and an idempotency constraint. Implement the transaction writer with one SQLAlchemy transaction and a recursive forbidden-field validator; deny update/delete privileges on audit records.
- [ ] **Step 4: Run GREEN evidence.** Run the focused SQL Server test and assert catalog/RLS coverage for both tables; append atomic commit, rollback, and redaction outputs to BE-005.
- [ ] **Step 5: Review and commit.** Verify no best-effort write occurs outside the transaction and commit `feat: add transactional audit and outbox persistence`.

### Task 5: BE-006 OpenAPI base and backend CI gates

**Files:**
- Create: `backend/tests/contract/test_openapi_base.py`, `contracts/openapi/v1.yaml`, `.github/workflows/backend.yml`, `scripts/validate_openapi.py`.
- Modify: `backend/src/openlibrary/app/factory.py`, `backend/src/openlibrary/app/health.py`, `backend/README.md`, `tasks/backend/BE-006.md`.

**Interfaces:**
- Produces `problem_response(status: int, type_uri: str, title: str, detail: str, instance: str, request_id: str) -> Response`.
- Produces OpenAPI `/api/v1` health/auth foundations and `X-Request-ID` contract behavior.

- [ ] **Step 1: Write failing contract tests.** Load `contracts/openapi/v1.yaml` and assert OpenAPI version, `/api/v1` server path, health endpoints, Problem Details schema with `request_id`, request ID header, and login schema with required `organization_slug`.

```python
def test_openapi_declares_request_id_and_problem_details() -> None:
    document = load_openapi_document()
    assert document["components"]["schemas"]["ProblemDetails"]["required"][-1] == "request_id"
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/contract/test_openapi_base.py -q`; record missing contract failure in BE-006.
- [ ] **Step 3: Implement versioned contract and gates.** Add valid OpenAPI 3.1 YAML, centralized request ID generation/validation and RFC Problem Details serialization. Add CI jobs that block on `ruff format --check .`, `ruff check .`, `mypy src`, backend tests, SQL Server integration setup, OpenAPI validation/compatibility, and `docker compose -f infra/docker-compose.yml config`.
- [ ] **Step 4: Run GREEN evidence.** Run the focused contract test and `python scripts/validate_openapi.py`; inspect the workflow for every required blocking command and append outputs to BE-006.
- [ ] **Step 5: Review and commit.** Verify contract is machine-readable/versioned and CI does not substitute frontend checks; commit `feat: add openapi base and backend quality gates`.

### Task 6: BE-007 Argon2id login

**Files:**
- Create: `backend/tests/api/auth/test_login.py`, `backend/migrations/versions/0004_users_profiles.py`, `backend/src/openlibrary/modules/core/domain/passwords.py`, `backend/src/openlibrary/modules/core/application/login.py`, `backend/src/openlibrary/modules/core/api/auth.py`.
- Modify: `backend/pyproject.toml`, `backend/src/openlibrary/app/factory.py`, `contracts/openapi/v1.yaml`, `tasks/backend/BE-007.md`.

**Interfaces:**
- Produces `PasswordService.hash(password: str) -> str`, `PasswordService.verify(password: str, encoded_hash: str) -> bool`, and `LoginService.login(slug: str, email: str, password: str) -> LoginResult`.
- Produces `POST /api/v1/auth/login`; `LoginResult` has no password, hash, raw token, or profile dump.

- [ ] **Step 1: Write failing API tests.** Cover successful login, wrong password, missing slug, disabled organization, and the same email in two organizations. Assert wrong slug, disabled slug, and wrong password have identical public Problem Details while corresponding audit actions contain no credential values.

```python
def test_wrong_slug_and_wrong_password_have_identical_public_failure(client: FlaskClient) -> None:
    assert login(client, "missing", "a@test", "wrong").get_json() == login(client, "campus-a", "a@test", "wrong").get_json()
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/api/auth/test_login.py -q`; record absent login-service failure in BE-007.
- [ ] **Step 3: Implement users, profiles, and uniform login.** Add RLS-protected tenant user/profile migrations with composite FK/unique constraints. Use Argon2id and an injected dummy encoded hash for unresolved/disabled tenants. Resolve tenant only through the BE-004 stored procedure, write success/failure audit events through the BE-005 writer, and return a uniform authentication problem for all required public failures.
- [ ] **Step 4: Run GREEN evidence.** Run the login suite and audit/outbox integration suite against SQL Server; append duplicate-email and uniform-failure evidence to BE-007.
- [ ] **Step 5: Review and commit.** Search staged code/events/logs for plaintext passwords and hashes in responses, then commit `feat: add argon2id login`.

### Task 7: BE-008 access JWT and protected principal

**Files:**
- Create: `backend/tests/api/auth/test_access_tokens.py`, `backend/src/openlibrary/modules/core/application/tokens.py`, `backend/src/openlibrary/modules/core/api/principal.py`.
- Modify: `backend/src/openlibrary/modules/core/application/login.py`, `backend/src/openlibrary/modules/core/api/auth.py`, `backend/src/openlibrary/app/factory.py`, `contracts/openapi/v1.yaml`, `tasks/backend/BE-008.md`.

**Interfaces:**
- Produces `TokenIssuer.issue(principal: Principal, now: datetime) -> str`, `TokenVerifier.verify(token: str, now: datetime) -> Principal`, and immutable `Principal(user_id: UUID, organization_id: UUID, session_id: UUID, authorization_ids: tuple[UUID, ...])`.
- Produces protected `GET /api/v1/auth/me`.

- [ ] **Step 1: Write failing token/API tests.** Generate RS256 test keys and independently assert rejection for `none`/HS algorithm, bad issuer, bad audience, expiration, and unknown `kid`; assert `/auth/me` returns only documented principal fields and protected tenant derives from the verified token.

```python
@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "kid"])
def test_verifier_rejects_invalid_claim(claim: str) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(tampered_rs256_token(claim))
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/api/auth/test_access_tokens.py -q`; record missing verifier failure in BE-008.
- [ ] **Step 3: Implement issuer/verifier and principal middleware.** Use configured RS256 keys, explicit `algorithms=["RS256"]`, issuer/audience checks, `kid` lookup, and expiry/nbf validation. Retain retiring public keys until configured access-token lifetime ends. Make route protection fail closed before any tenant context setter runs.
- [ ] **Step 4: Run GREEN evidence.** Run focused tests and add a key-rotation assertion proving old public keys remain valid only through issued-token expiry; append output to BE-008.
- [ ] **Step 5: Review and commit.** Inspect claim construction and logs for profile/password/permission-list leakage; commit `feat: add access token verification and principal`.

### Task 8: BE-009 refresh rotation, revocation, and CSRF

**Files:**
- Create: `backend/tests/api/auth/test_refresh_sessions.py`, `backend/migrations/versions/0005_refresh_sessions.py`, `backend/src/openlibrary/modules/core/application/refresh_sessions.py`.
- Modify: `backend/src/openlibrary/modules/core/api/auth.py`, `contracts/openapi/v1.yaml`, `tasks/backend/BE-009.md`.

**Interfaces:**
- Produces `RefreshSessionService.rotate(raw_token: str, csrf: str) -> RefreshResult`, `RefreshSessionService.logout(raw_token: str, csrf: str) -> None`, and `RefreshResult(access_token: str, refresh_cookie: str, csrf_token: str)`.
- Produces `POST /api/v1/auth/refresh` and `POST /api/v1/auth/logout`.

- [ ] **Step 1: Write failing refresh tests.** Cover valid rotation, replaying the original value revoking the entire chain, logout revocation, invalid token, and missing/invalid CSRF. Assert database rows contain only token hashes, cookie attributes include Secure/HttpOnly, and raw values are absent from audit/outbox data.

```python
def test_reuse_of_rotated_token_revokes_its_chain(client: FlaskClient) -> None:
    original = login_and_extract_refresh(client)
    rotate(client, original)
    assert reuse(client, original).status_code == 401
    assert active_chain_count(original) == 0
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/api/auth/test_refresh_sessions.py -q`; record missing refresh-session failure in BE-009.
- [ ] **Step 3: Implement opaque hashed single-use sessions.** Add RLS-protected `core.refresh_sessions` with a unique indexed hash, parent chain, expiry/revocation metadata, composite user references, and owner-executing resolver. Generate opaque values with `secrets`, hash with a domain-separated cryptographic hash, lock/atomically consume a valid session, revoke the chain on reuse, and validate CSRF with constant-time comparison.
- [ ] **Step 4: Run GREEN evidence.** Run focused API and tenancy resolver integration tests; append rotation/reuse/revocation and CSRF outputs to BE-009.
- [ ] **Step 5: Review and commit.** Search changed data paths for raw refresh values and inspect cookie flags; commit `feat: add refresh rotation and csrf boundary`.

### Task 9: BE-010 data-driven RBAC and authorization

**Files:**
- Create: `backend/tests/api/core/test_rbac.py`, `backend/tests/integration/migrations/test_rbac_schema.py`, `backend/migrations/versions/0006_rbac.py`, `backend/src/openlibrary/modules/core/application/authorization.py`, `backend/src/openlibrary/modules/core/infrastructure/rbac.py`.
- Modify: `backend/src/openlibrary/modules/core/api/principal.py`, `backend/src/openlibrary/modules/core/api/auth.py`, `contracts/openapi/v1.yaml`, `tasks/backend/BE-010.md`.

**Interfaces:**
- Produces `AuthorizationPort.require(principal: Principal, permission: str) -> None`, `RbacService.assign_role(user_id: UUID, role_id: UUID, actor: Principal) -> None`, and `RbacService.revoke_role(user_id: UUID, role_id: UUID, actor: Principal) -> None`.
- Produces `AuthorizationDenied`, mapped by the API to a stable non-leaking Problem Details response.

- [ ] **Step 1: Write failing RBAC tests.** Create two tenant roles/permissions with the migration identity, assign/revoke through the service, assert permission change takes effect without restart, and assert an unauthorized protected service returns the stable authorization failure without data. Add catalog assertions for RLS and composite keys on every RBAC table.

```python
def test_revocation_changes_effective_permission_without_deployment(rbac: RbacService) -> None:
    rbac.assign_role(USER_A, ROLE_MANAGE, ACTOR)
    assert authorizer.allows(PRINCIPAL_A, "role.manage")
    rbac.revoke_role(USER_A, ROLE_MANAGE, ACTOR)
    assert not authorizer.allows(PRINCIPAL_A, "role.manage")
```

- [ ] **Step 2: Run RED evidence.** Run `cd backend; python -m pytest tests/api/core/test_rbac.py tests/integration/migrations/test_rbac_schema.py -q`; record missing authorization-port failure in BE-010.
- [ ] **Step 3: Implement tenant RBAC persistence and service boundary.** Add RLS-protected roles, permissions, user_roles, and role_permissions with composite keys/FKs/indexes. Implement parameterized effective-permission lookup and application authorization port; assignment/revocation writes tenant-scoped audit events through the transaction writer. Use named permission strings only at service boundaries, never role-name branches.
- [ ] **Step 4: Run GREEN evidence.** Run focused API/schema tests and audit integration test, verifying authorization denial and immediate data-driven revocation; append output to BE-010.
- [ ] **Step 5: Review and commit.** Search the protected code for hard-coded role-name authorization, run `git diff --check`, and commit `feat: add data driven rbac authorization`.

## Final integration and completion gate

- [ ] Re-read every BE-002…BE-010 acceptance criterion against the implementation and task evidence; append only fresh command outputs and update each status to Completed only when its evidence is present.
- [ ] Start the full Compose stack from a clean validated configuration; run migrations with the migration identity and focused SQL Server catalog/role/RLS suites with the runtime identity.
- [ ] Run `cd backend; python -m pytest -q`, `python -m ruff format --check .`, `python -m ruff check .`, and `python -m mypy src`.
- [ ] Run `docker compose -f infra/docker-compose.yml config` and `python scripts/validate_openapi.py`; inspect CI workflow syntax and each blocking job.
- [ ] Run delegated Open Code Review on every changed reviewable file, resolve all critical/high findings, run a final whole-branch review, and attach its verdict to the final evidence summary.
- [ ] Commit final evidence/doc fixes, verify `git status --short` is empty, then use `finishing-a-development-branch` to present integration options rather than altering `main` automatically.
