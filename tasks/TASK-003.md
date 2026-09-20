# TASK-003 — Authentication and RBAC

## Task Information

- ID: TASK-003
- Name: Authentication, sessions and dynamic RBAC
- Priority: P0 — security critical

## Objective

Implement one-account/one-organization authentication, Argon2id passwords, access JWT, refresh rotation/revocation, user sessions and data-driven RBAC.

## Scope

Implement `core.users`, `core.user_profiles`, `core.roles`, `core.permissions`, `core.user_roles`, `core.role_permissions` and `core.refresh_sessions`. Add auth API and audit events for security actions.

## Files affected

- Modify: `backend/src/openlibrary/modules/core/`
- Create: `backend/migrations/versions/`
- Create: `backend/tests/unit/auth/`, `backend/tests/api/auth/`, `backend/tests/integration/auth/`
- Modify: `contracts/openapi/v1.yaml`, `docs/api-design.md`, `docs/security.md`

## Implementation steps

1. Write failing tests for password verification, login success and invalid-login response.
2. Run them and verify the missing auth service causes expected failures.
3. Implement Argon2id password service and login use case.
4. Write failing rotation, reuse rejection and revoke tests.
5. Implement hashed refresh sessions with parent chain and revoke timestamps.
6. Write failing permission assignment and authorization matrix tests.
7. Implement role/permission repositories and service authorization port.
8. Add migration, API schemas, problem details and security audit events.
9. Run focused auth tests and full backend suite.

## Dependencies

TASK-002.

## Testing checklist

- [ ] Passwords are never stored or returned in plaintext.
- [ ] Access token expiry is enforced.
- [ ] Refresh rotation invalidates the used token.
- [ ] Reuse of a rotated token revokes the session chain.
- [ ] Logout revokes the active refresh session.
- [ ] Role/permission changes apply without code deployment.
- [ ] Invalid credentials do not reveal account existence.
- [ ] Auth mutations produce audit records.

## Acceptance criteria

- Auth endpoints match OpenAPI and return stable Problem Details.
- Browser refresh token is Secure HttpOnly and CSRF protected.
- Backend permission checks do not depend on hard-coded role names.
- Two organizations can use the same email address without collision.

## Reviewer checklist

- [ ] JWT payload contains no sensitive profile or permission dump.
- [ ] Refresh token plaintext never enters database or logs.
- [ ] Session lookup is tenant-scoped and indexed.
- [ ] Authorization failure is distinguishable from authentication failure without leaking data.
