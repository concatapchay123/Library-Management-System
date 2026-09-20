# TASK-004 — Organization and SQL Server tenant isolation

## Task Information

- ID: TASK-004
- Name: Organization management and enforced tenant isolation
- Priority: P0 — security critical

## Objective

Implement organization settings, tenant context propagation and SQL Server Row-Level Security so cross-tenant reads and writes fail at the database boundary.

## Scope

Implement organization settings, tenant middleware, RLS catalog enforcement and tenant-aware seed data. `core.organizations` plus the shared predicate already exist from TASK-002; tenant tables created by TASK-003 are already protected in their own migration. Add two-tenant integration fixtures.

## Files affected

- Modify: `backend/src/openlibrary/modules/core/` and `backend/src/openlibrary/shared/`
- Create: `backend/migrations/versions/*_tenant_rls.py`
- Create: `backend/tests/integration/tenancy/`
- Modify: `docs/database-design.md`, `docs/security.md`, `docs/deployment.md`

## Implementation steps

1. Write failing SQL Server integration tests for cross-tenant SELECT, UPDATE, DELETE and INSERT, plus a catalog test for a deliberately policy-free tenant-table fixture.
2. Run the policy-free fixture and confirm catalog enforcement fails for the expected missing-predicate reason; run cross-tenant cases with missing context and confirm fail-closed behavior.
3. Implement tenant context middleware and transaction-scoped `SESSION_CONTEXT` setup.
4. Add system-catalog enforcement that verifies every tenant-owned table has RLS filter/block policies and that every tenant relation uses composite foreign keys.
5. Add connection reset/invalidation logic when context cleanup fails.
6. Add organization bootstrap command with explicit privileged role and audit event.
7. Run connection-pool reuse tests with Tenant A followed by Tenant B.

## Dependencies

TASK-003.

## Testing checklist

- [ ] Tenant A cannot read Tenant B rows.
- [ ] Tenant A cannot update or delete Tenant B rows.
- [ ] Wrong-tenant insert is blocked.
- [ ] Missing tenant context fails closed.
- [ ] Pooled connection context is reset between requests.
- [ ] Organization bootstrap cannot be called through ordinary user API.
- [ ] Every created tenant table has non-null `organization_id` and foreign key.
- [ ] Tenant-owned relation fails migration review when it omits the composite `(organization_id, id)` foreign key.

## Acceptance criteria

- RLS enforcement remains effective even if an application query omits a tenant predicate.
- Service authorization and RLS both execute for protected mutations.
- Tenant integration suite runs on SQL Server, not a substitute database.

## Reviewer checklist

- [ ] No privileged database credential is embedded in application config.
- [ ] RLS policies cover both filter and block predicates.
- [ ] Context cleanup failure invalidates the connection.
- [ ] Bootstrap and cross-tenant denial are audited without leaking data.
