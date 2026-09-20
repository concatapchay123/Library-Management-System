# TASK-008 — Public library edition

## Task Information

- ID: TASK-008
- Name: Membership, fines, payments and invoices
- Priority: P2

## Objective

Add public-library membership and money workflows while keeping core circulation independent from subscription implementation.

## Scope

Implement members, membership plans, subscriptions, fines, payments, payment allocations, invoices and invoice lines. Example seed plans: Basic 5 books/30 days and Premium 20 books/90 days. Payment includes provider webhook verification, reconciliation and partial/refund state transitions; it does not introduce a general accounting ledger.

## Files affected

- Create: `backend/src/openlibrary/modules/public_library/`
- Create: public-library migrations and tests
- Modify: `contracts/openapi/v1.yaml`, `docs/database-design.md`, `docs/security.md`
- Modify: `docs/deployment.md` for payment adapter secrets

## Implementation steps

1. Write failing tests for plan snapshot, subscription validity and money calculation.
2. Run tests and confirm missing public-library policy fails as expected.
3. Implement plan/subscription policy adapter for circulation.
4. Implement fine assessment, payment state machine and immutable partial-payment/refund allocation.
5. Write failing webhook tests for invalid signature, stale replay timestamp, duplicate provider event and pending-payment reconciliation; implement signature verification on raw body, provider event deduplication and outbox reconciliation.
6. Add idempotent provider reference handling and invoice immutability after issue.
7. Add tenant-scoped migrations, composite foreign keys, API schemas and audit events.
8. Test provider retry, duplicate webhook/reference, failed payment, partial payment and refund paths.

## Dependencies

TASK-006.

## Testing checklist

- [ ] Basic and Premium plan defaults are seed data and tenant-scoped.
- [ ] Subscription validity controls policy selection.
- [ ] Fine amounts use `decimal(19,4)` and explicit currency.
- [ ] Payment retry does not duplicate settlement.
- [ ] Invoice lines and totals are immutable after issue.
- [ ] Provider credentials/card data are never persisted.
- [ ] Webhook signature and replay timestamp are verified before payload parsing or mutation.
- [ ] Payment timeout remains pending until reconciliation; duplicate provider event cannot settle twice.
- [ ] Partial payment and refund allocation totals cannot exceed the related payment/fine under documented state rules.

## Acceptance criteria

- Member can subscribe, borrow under plan limits, receive a fine and record an idempotent payment.
- Payment and invoice transitions are auditable and tenant-isolated.
- Public library implementation does not leak into core controllers or entities.

## Reviewer checklist

- [ ] Money calculations avoid floating point.
- [ ] Payment adapter has explicit timeout/retry behavior.
- [ ] Duplicate provider callbacks are safe.
- [ ] Sensitive payment data is excluded from logs and audit JSON.
- [ ] Webhook raw body, signature secret and provider credential are never stored in idempotency, audit or job payloads.
