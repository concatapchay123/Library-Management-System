# TASK-012 — Production deployment and release

## Task Information

- ID: TASK-012
- Name: Production profile, release and rollback
- Priority: P1 — release gate

## Objective

Make OpenLibraryOS deployable on a clean host with secure configuration, controlled migrations, observability, backups and a tested rollback path.

## Scope

Implement production Compose/Nginx configuration, deployment migration job, secret documentation, backup/restore scripts/runbooks, release checklist and CI release workflow.

## Files affected

- Modify: `infra/docker-compose.yml`, `infra/nginx/`, `.github/workflows/`
- Create: deployment runbooks and backup/restore operational scripts
- Modify: `docs/deployment.md`, `docs/security.md`, `docs/roadmap.md`
- Create: release checklist under `tasks/`

## Implementation steps

1. Write a deployment smoke test for clean host configuration validation.
2. Run it and verify missing production profile fails safely.
3. Add immutable image tags, non-default secrets and network restrictions.
4. Add one-time migration job with lock and readiness gate.
5. Add Nginx TLS/security headers, SPA fallback and API proxy configuration.
6. Add backup/restore and rollback runbooks with explicit evidence commands.
7. Execute clean-host deploy, migration, health, backup/restore and rollback rehearsal.

## Dependencies

TASK-011.

## Testing checklist

- [ ] Production config rejects missing required secrets.
- [ ] Database and Redis are not publicly exposed.
- [ ] Migration runs once and is observable.
- [ ] Readiness gate prevents traffic before dependencies are healthy.
- [ ] Backup restores into isolated environment.
- [ ] Previous application version starts after backward-compatible migration.
- [ ] TLS/security headers and SPA/API routing work.

## Acceptance criteria

- A clean host can deploy the documented version using the release runbook.
- Health, logs, metrics, backup and alert checks have recorded evidence.
- Rollback or forward-fix decision is explicit for every release migration.

## Reviewer checklist

- [ ] No production secret is committed.
- [ ] Migration identity is least-privilege and separate from runtime identity.
- [ ] Rollback instructions match actual migration compatibility.
- [ ] Backup retention and restore ownership are documented.
