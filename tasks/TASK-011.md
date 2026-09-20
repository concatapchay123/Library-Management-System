# TASK-011 — Integration, security and performance hardening

## Task Information

- ID: TASK-011
- Name: Full verification and operational hardening
- Priority: P1 — release gate

## Objective

Prove the delivered system meets tenant, auth, workflow, compatibility, performance and operational requirements before deployment work starts.

## Scope

Complete test matrix, fixture quality, security scans, OpenAPI compatibility checks, structured logging, metrics, health checks, baseline performance and backup/restore rehearsal.

## Files affected

- Modify: `backend/tests/`, `frontend/tests/`, `.github/workflows/ci.yml`
- Modify: `docs/testing-strategy.md`, `docs/security.md`, `docs/deployment.md`
- Create: operational runbooks and performance test configuration

## Implementation steps

1. Run the full unit, API, integration and frontend suites.
2. Add missing two-tenant, concurrent checkout, token reuse and idempotency cases.
3. Run dependency audit, secret scan and OpenAPI breaking-change check.
4. Verify structured logs, request correlation, health endpoints and queue metrics.
5. Run a documented SQL Server backup/restore drill.
6. Measure baseline latency for catalog search and checkout; record environment and result.
7. Run delegated Open Code Review and fix critical/high findings.

## Dependencies

TASK-003 through TASK-010.

## Testing checklist

- [ ] Full CI suite passes from a clean checkout.
- [ ] Cross-tenant negative tests pass.
- [ ] RLS context reuse tests pass.
- [ ] No critical/high dependency or code-review finding remains.
- [ ] Restore drill produces a usable database and passes smoke tests.
- [ ] Performance baseline is recorded and reproducible.

## Acceptance criteria

- Security, compatibility and integration gates are automated or documented as release commands.
- Known limits and ceilings are recorded instead of silently ignored.
- All Phase 0–9 checkpoints have evidence.

## Reviewer checklist

- [ ] Verification commands are complete, not partial samples.
- [ ] Test fixtures do not accidentally bypass RLS.
- [ ] Performance result includes data volume and environment.
- [ ] Review coverage accounts for every changed file.
