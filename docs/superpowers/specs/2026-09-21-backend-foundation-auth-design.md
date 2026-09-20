# Backend Foundation and Authentication Design

## Goal

Deliver BE-002 through BE-010 as one secure, testable backend foundation: validated runtime configuration; an operational SQL Server/Redis Compose stack; migrations and least-privilege database identities; tenant isolation; transactional audit/outbox persistence; a versioned API contract and CI gates; and authentication, sessions, CSRF, and data-driven RBAC.

## Scope and boundaries

This design implements only the acceptance criteria in `tasks/backend/BE-002.md` through `BE-010.md`. It retains the existing Flask app factory and the modular-monolith dependency direction from `docs/architecture.md`:

```text
Flask API adapters -> application services -> domain values/policies
                         |
                         v
                  infrastructure ports -> SQL Server / Redis
```

HTTP routes do input/output adaptation only. Authentication, refresh rotation, authorization, audit/outbox, and tenant decisions are application or infrastructure responsibilities. `organization_id` is never trusted from a protected request body, header, or route parameter; a verified JWT, login resolver, or refresh resolver is the only source of tenant context.

No business-resource endpoints, frontend work, password reset, worker delivery loops, or platform-control APIs are included.

## Runtime and local infrastructure

`AppSettings.from_environment` will parse one documented name for every setting and raise a configuration error before an application is created when required secret or connection values are missing. Defaults are limited to non-secret development-safe settings; there is no secret fallback. A names-only `.env.example` documents the contract.

`infra/docker-compose.yml` will define `database` (SQL Server), `redis`, `app`, `worker`, and `nginx`, using a shared internal network. SQL Server and Redis receive no host `ports` mapping. Each service has a health check, and consumers wait for required services to become healthy. The app runs only the Flask API; Nginx proxies API traffic and does not host SPA assets in this phase. Compose creates the migration and runtime database identities only through an explicit bootstrap/migration path, never from normal app startup.

## Database and migration design

Flask-Migrate/Alembic is the sole migration runner. A documented command runs migrations from a clean SQL Server database using the migration identity. Runtime connection settings are distinct from migration settings. A migration bootstrap creates schemas, dedicated migration/runtime principals or users, and explicit grants. The runtime identity is denied DDL, `CONTROL`, `IMPERSONATE`, ownership, and RLS-policy alteration; its catalog grants and negative DDL/RLS attempts are integration-tested against SQL Server.

Migrations create every table with `organization_id UNIQUEIDENTIFIER NOT NULL` where tenant-owned, composite tenant candidate keys and composite foreign keys, named indexes supporting real resolver/effective-permission queries, server UTC timestamps, and SQL Server RLS policies. The root `core.organizations` table is itself protected by a schema-bound tenant predicate that returns false for missing/invalid `SESSION_CONTEXT(N'organization_id')`. Each protected table has both filter and block predicates.

The only pre-context tenant lookups are narrowly granted `EXECUTE AS OWNER` procedures:

- `core.resolve_login_tenant` resolves the minimal organization/login data required for public login.
- `core.resolve_refresh_session` resolves the server-created tenant/session data required for refresh handling.

Runtime has procedure execution but no direct pre-context registry/session-table reads. Tests cover missing-context denial, cross-tenant filtering/blocking, resolver-only discovery, and catalog coverage of every protected table.

## Audit and outbox transaction contract

The infrastructure transaction boundary persists a protected mutation, an immutable `ops.audit_events` record, and a durable `ops.outbox_events` record in one SQL Server transaction. Rollback writes neither event. Payload creation uses an explicit allow-list/rejection guard so password material, refresh/access tokens, secrets, and raw payment data cannot reach either table. Audit rows are append-only through permissions and database protection. Outbox events carry an event type, payload version, idempotency key, correlation/request ID, and server-derived organization ID.

## API contract and quality gates

`contracts/openapi/v1.yaml` becomes the versioned machine-readable source for `/api/v1` health and authentication. It declares `X-Request-ID`, RFC 9457-compatible Problem Details responses with `request_id`, required `organization_slug` for login, protected principal output, and refresh/logout cookie/CSRF behavior. The API adapts all errors to a stable problem response without stack traces, SQL, passwords, or tokens.

The backend CI workflow has independent blocking jobs for formatting, lint, type checking, unit/API tests, SQL Server migration integration tests, OpenAPI validation/compatibility, and Compose configuration validation. The local commands documented in `backend/README.md` and task evidence are the commands CI invokes or their stricter equivalents; frontend checks do not substitute for backend gates.

## Authentication and protected principal

User/profile migrations enforce tenant-scoped email uniqueness and composite references, with RLS policies at creation. Passwords use Argon2id only. Login accepts `organization_slug`, resolves the tenant through the stored procedure, performs a dummy Argon2 verification for unknown or disabled tenants, and returns one uniform public failure for wrong slug, disabled tenant, or wrong password. Security success/failure actions are audited without credential content.

JWT issuance uses a configured private key and stable `kid`; verification pins RS256, issuer, audience, expiration, and known public key before creating the principal. The principal is deliberately small: user ID, organization ID, session ID, and authorization identifiers. It never embeds a profile dump, password material, or a permission list. Key rotation keeps old public keys for at least the maximum issued access-token lifetime. `GET /api/v1/auth/me` serializes only documented principal fields.

## Refresh, CSRF, and RBAC

Refresh tokens are cryptographically random opaque values. Only their hashes are stored, indexed for resolver lookup, and tied to a parent session chain. Refresh rotation consumes a token once; reuse revokes the chain; logout revokes the active chain. Neither raw refresh values nor hashes enter logs, API payloads, or audit/outbox data. Refresh/logout mutations require an HTTPS-only Secure HttpOnly cookie contract plus a validated CSRF value; missing or invalid CSRF is rejected.

RBAC migrations create RLS-protected tenant-scoped roles, permissions, user-role assignments, and role-permission assignments using composite tenant constraints. Application services request named permissions through one authorization port; they never branch on hard-coded role names. Assign/revoke operations are transactional and audit-recorded. An effective-permission query joins tenant-scoped relations, so a data change takes effect without deployment. API adapters return a stable authorization problem and do not disclose protected data.

## Test-first and evidence contract

For every BE task, the named test file is added first and run before production code exists for that behavior. The expected RED command/output is recorded in the task's Evidence checkpoint section. After the smallest implementation, the same focused test is rerun, then applicable SQL Server catalog/role tests, OpenAPI/Compose commands, and later the full backend suite. Evidence records the exact command, exit result, and concise output summary; it never contains credentials or tokens.

Each task is independently reviewed against its acceptance criteria after its focused verification. The final branch review covers all files changed for BE-002 through BE-010, with critical/high findings resolved before final verification.

## Non-negotiable security invariants

- Every persistent tenant-owned row has `organization_id`, tenant-aware constraints, and RLS filter/block protection.
- Protected requests derive tenant context only from verified authentication state.
- Runtime database identity is never a migration/owner identity and cannot modify schema or RLS policy.
- Authentication errors are uniform where required to prevent tenant/credential enumeration.
- Passwords, tokens, secrets, and raw payment data never persist in audit/outbox records, logs, or HTTP responses.
- Database integration tests use the Compose SQL Server service, never SQLite or another substitute.
