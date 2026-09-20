# Roadmap OpenLibraryOS

The active backlog is indexed in [tasks/README.md](../tasks/README.md). Backend owns API contracts, database, migration, CI, Compose, Nginx and operational documentation. Frontend begins only after backend capability task BE-026 is complete.

## Phase 0 — Architecture preparation

Deliverables: governance files, architecture/system/database/API/security/deployment/development/testing docs, foundational decisions and target folder structure.

Checkpoint: documentation has no unresolved planning marker, module boundaries are consistent and RLS/auth/data decisions are reviewed.

Historical source: [TASK-001](../tasks/legacy/TASK-001.md).

## Phase 1 — Project foundation

Deliver a runnable Flask foundation, local service configuration, SQL Server migration identities, tenant registry/RLS predicate, audit/outbox primitives and backend contract/CI base.

Tasks: [BE-001](../tasks/backend/BE-001.md), [BE-002](../tasks/backend/BE-002.md), [BE-003](../tasks/backend/BE-003.md), [BE-004](../tasks/backend/BE-004.md), [BE-005](../tasks/backend/BE-005.md), [BE-006](../tasks/backend/BE-006.md).

Checkpoint: app starts, clean migration succeeds, missing tenant context fails closed, runtime identity lacks DDL/RLS-policy privileges and backend CI is green.

## Phase 2 — Authentication and RBAC

Deliver Argon2id login with organization_slug, JWT principal verification, secure refresh rotation and dynamic RBAC.

Tasks: [BE-007](../tasks/backend/BE-007.md), [BE-008](../tasks/backend/BE-008.md), [BE-009](../tasks/backend/BE-009.md), [BE-010](../tasks/backend/BE-010.md).

Checkpoint: login tenant is unambiguous, tokens cannot be reused after rotation, verifier pins algorithm/issuer/audience/key rotation and authorization has no hard-coded role names.

## Phase 3 — Organization and multi-tenancy

Deliver organization settings, request tenant context, RLS catalog enforcement and pool-cleanup proof.

Tasks: [BE-011](../tasks/backend/BE-011.md).

Checkpoint: RLS blocks cross-tenant read/write/insert, catalog rejects incomplete tenant tables, composite foreign keys protect tenant relations and pooled context cannot leak.

## Phase 4 — Book management

Deliver bibliographic catalog, locations, copies and copy-state history.

Tasks: [BE-012](../tasks/backend/BE-012.md), [BE-013](../tasks/backend/BE-013.md), [BE-014](../tasks/backend/BE-014.md).

Checkpoint: catalog/copy/location APIs, state transitions, history and tenant tests pass.

## Phase 5 — Borrowing system

Deliver durable async infrastructure, circulation lifecycle, concurrency/idempotency protection, reservations and overdue scheduling.

Tasks: [BE-015](../tasks/backend/BE-015.md), [BE-016](../tasks/backend/BE-016.md), [BE-017](../tasks/backend/BE-017.md), [BE-018](../tasks/backend/BE-018.md), [BE-019](../tasks/backend/BE-019.md).

Checkpoint: circulation end-to-end flow, concurrent checkout, reservation replay and audit/outbox/dispatcher recovery tests pass.

## Phase 6 — Education edition

Deliver education entities and an external borrower-policy adapter.

Tasks: [BE-020](../tasks/backend/BE-020.md), [BE-021](../tasks/backend/BE-021.md).

Checkpoint: student default 5 books/14 days and teacher default 20 books/90 days are configurable policy data and core does not import education implementation.

## Phase 7 — Public library edition

Deliver member/subscription policy, fines/invoices and secure payment reconciliation.

Tasks: [BE-022](../tasks/backend/BE-022.md), [BE-023](../tasks/backend/BE-023.md), [BE-024](../tasks/backend/BE-024.md).

Checkpoint: plan snapshot, fine calculation, signature/replay rejection, pending reconciliation, partial/refund allocation and payment retry tests pass.

## Phase 8 — Notification

Deliver in-app notifications and bounded, observable email delivery.

Tasks: [BE-025](../tasks/backend/BE-025.md), [BE-026](../tasks/backend/BE-026.md).

Checkpoint: notification replay is safe, failed jobs are visible and email failure does not roll back source transactions.

## Frontend delivery

After BE-026, deliver a minimal, understandable and accessible UI that consumes the completed contracts without reproducing business rules.

Tasks: [FE-001](../tasks/frontend/FE-001.md), [FE-002](../tasks/frontend/FE-002.md), [FE-003](../tasks/frontend/FE-003.md), [FE-004](../tasks/frontend/FE-004.md), [FE-005](../tasks/frontend/FE-005.md), [FE-006](../tasks/frontend/FE-006.md), [FE-007](../tasks/frontend/FE-007.md), [FE-008](../tasks/frontend/FE-008.md), [FE-009](../tasks/frontend/FE-009.md), [FE-010](../tasks/frontend/FE-010.md).

Checkpoint: all critical workflows have loading, empty and error states; keyboard interaction works; browser storage contains no access token; API types come from OpenAPI.

## Phase 9 — Testing and hardening

Run complete system verification after FE-010.

Task: [BE-027](../tasks/backend/BE-027.md).

Checkpoint: CI is green; no critical/high security finding is open; RLS, composite-FK, audit/outbox, webhook, key-rotation, retention, accessibility and performance checks have evidence.

## Phase 10 — Deployment

Deploy the verified system to a clean host and prove recoverability.

Task: [BE-028](../tasks/backend/BE-028.md).

Checkpoint: clean-host deploy works, readiness/alerts operate, RPO is at most 15 minutes, RTO is at most 4 hours, retention is at least 35 days or a stricter approved contract, and restore/rollback rehearsals have evidence.
