# TASK-006 — Borrowing and reservations

## Task Information

- ID: TASK-006
- Name: Circulation lifecycle and reservation queue
- Priority: P1 — core business

## Objective

Implement request/approval/direct checkout/return/overdue and reservation workflows with transaction-safe copy locking and policy snapshots.

## Scope

Implement `core.loans`, `core.reservations`, due date policy port, idempotency handling, copy/loan audit events, `ops.job_records` and the generic outbox dispatcher required by reservation/overdue processing. Self-service requests require approval; librarian desk checkout may approve and checkout in one operation.

## Files affected

- Modify: `backend/src/openlibrary/modules/core/`
- Create: `backend/src/openlibrary/ops/` generic outbox dispatcher and job-record adapters
- Create: circulation migrations, domain tests, API tests and concurrency integration tests
- Modify: `contracts/openapi/v1.yaml`, `docs/system-design.md`, `docs/api-design.md`

## Implementation steps

1. Write failing tests for loan state transitions and policy limit rejection.
2. Run them and verify transitions fail before service implementation.
3. Implement request, approve, checkout and return use cases.
4. Add policy snapshot fields and active-loan constraints.
5. Write failing concurrent checkout test for one copy.
6. Implement SQL transaction locking and idempotency record handling with 24-hour safe-record expiry.
7. Write failing tests for atomic audit/outbox writes, dispatcher crash/reclaim, duplicate consumer delivery and pre-context worker claim; implement `ops.claim_outbox_event`, `ops.job_records`, bounded-retry dispatcher, dead-letter state and consumer deduplication.
8. Implement reservation queue, claim, hold expiry and cancellation through durable outbox events.
9. Add overdue calculation and background job contract without coupling to email.

## Dependencies

TASK-005.

## Testing checklist

- [ ] Self-service loan request requires approval.
- [ ] Desk checkout uses the same checkout service and can approve directly.
- [ ] One copy cannot have two active loans under concurrent checkout.
- [ ] Due date uses policy snapshot at checkout.
- [ ] Return updates loan and copy atomically.
- [ ] Reservation queue ordering is deterministic.
- [ ] Expired hold advances to the next reservation.
- [ ] Replayed idempotency key returns original result without duplicate side effect.
- [ ] Return/reservation mutation writes audit and outbox event atomically.
- [ ] Dispatcher replay after a lease expiry cannot skip or duplicate reservation allocation.

## Acceptance criteria

- Complete circulation flow passes with two organizations and multiple copies.
- Invalid status transitions and over-limit borrowers return documented errors.
- All mutations create audit events in the same transaction.

## Reviewer checklist

- [ ] No race-prone check-then-insert exists for active checkout.
- [ ] Reservation allocation cannot skip or duplicate queue entries.
- [ ] Payment is not coupled into core loan return.
- [ ] Idempotency request hash prevents key reuse with different payload.
- [ ] Outbox payload is versioned, tenant context comes from server-created record, and retry/dead-letter behavior is bounded and observable.
