# TASK-008 — Public library edition

## Task Information

- ID: TASK-008
- Name: Membership, fines, payments and invoices
- Priority: P2

## Objective

Add public-library membership and money workflows while keeping core circulation independent from subscription implementation.

## Scope

Implement members, membership plans, subscriptions, fines, payments, invoices and invoice lines. Example seed plans: Basic 5 books/30 days and Premium 20 books/90 days.

## Files affected

- Create: `backend/src/openlibrary/modules/public_library/`
- Create: public-library migrations and tests
- Modify: `contracts/openapi/v1.yaml`, `docs/database-design.md`, `docs/security.md`
- Modify: `docs/deployment.md` for payment adapter secrets

## Implementation steps

1. Write failing tests for plan snapshot, subscription validity and money calculation.
2. Run tests and confirm missing public-library policy fails as expected.
3. Implement plan/subscription policy adapter for circulation.
4. Implement fine assessment and payment state machine.
5. Add idempotent provider reference handling and invoice immutability after issue.
6. Add tenant-scoped migrations, API schemas and audit events.
7. Test provider retry, duplicate webhook/reference and failed payment paths.

## Dependencies

TASK-006.

## Testing checklist

- [ ] Basic and Premium plan defaults are seed data and tenant-scoped.
- [ ] Subscription validity controls policy selection.
- [ ] Fine amounts use `decimal(19,4)` and explicit currency.
- [ ] Payment retry does not duplicate settlement.
- [ ] Invoice lines and totals are immutable after issue.
- [ ] Provider credentials/card data are never persisted.

## Acceptance criteria

- Member can subscribe, borrow under plan limits, receive a fine and record an idempotent payment.
- Payment and invoice transitions are auditable and tenant-isolated.
- Public library implementation does not leak into core controllers or entities.

## Reviewer checklist

- [ ] Money calculations avoid floating point.
- [ ] Payment adapter has explicit timeout/retry behavior.
- [ ] Duplicate provider callbacks are safe.
- [ ] Sensitive payment data is excluded from logs and audit JSON.
