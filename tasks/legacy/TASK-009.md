# TASK-009 — Notifications, workers and audit

## Task Information

- ID: TASK-009
- Name: Notifications, Celery jobs and audit pipeline
- Priority: P2

## Objective

Provide reliable in-app notifications and retryable email delivery on top of the generic audit/outbox/job infrastructure delivered by TASK-006.

## Scope

Implement `core.notifications`, notification-specific Celery handlers, email port and notification templates for loan, reservation, overdue and payment events. Reuse `ops.audit_events`, `ops.outbox_events`, `ops.job_records` and generic dispatcher from TASK-002/TASK-006.

## Files affected

- Modify: `backend/src/openlibrary/modules/core/` and `backend/src/openlibrary/shared/`
- Modify: `backend/src/openlibrary/ops/` generic dispatcher registrations
- Create: notification/job/audit migrations and tests
- Modify: `infra/docker-compose.yml`, `docs/system-design.md`, `docs/deployment.md`

## Implementation steps

1. Write failing tests for notification status transitions and delivery consumer replay.
2. Run tests and confirm missing adapters fail for expected reasons.
3. Implement in-app notification repository and read/unread API.
4. Implement notification handler using generic job record, retry/backoff, deduplication and dead-letter visibility.
5. Implement email adapter interface and a development sink; production provider remains configuration-driven.
6. Add worker health/readiness and queue metrics.

## Dependencies

TASK-006, TASK-008.

## Testing checklist

- [ ] Audit payload excludes secrets/tokens/passwords/payment credentials.
- [ ] Notification retry is idempotent.
- [ ] Email provider failure does not roll back loan/payment transaction.
- [ ] Job attempts and last error are visible.
- [ ] Worker reconnect and graceful shutdown work.

## Acceptance criteria

- In-app notification appears for loan/reservation/overdue/payment events.
- Email jobs retry with bounded exponential backoff.
- Failed jobs are visible and operationally actionable.
- Audit is append-only and queryable by authorized users.

## Reviewer checklist

- [ ] No unbounded retry loop exists.
- [ ] Tasks do not perform cross-tenant work without explicit context.
- [ ] Job payloads are versioned and safe to replay.
- [ ] Audit writes cannot be silently dropped on successful mutations.
- [ ] Notification handlers reuse generic dispatcher semantics instead of creating a second job/outbox protocol.
