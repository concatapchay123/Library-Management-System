# OpenLibraryOS Task Backlog

## Canonical structure

- tasks/backend contains backend-owned tasks, including OpenAPI, migrations, CI, Compose, Nginx and operational documentation.
- tasks/frontend contains frontend-owned tasks. Frontend begins only after BE-026 is complete.
- tasks/legacy contains the original TASK-001 through TASK-012 documents for historical traceability. Legacy documents are not active work items.

## Task contract

Every active task has exactly one owner and one independently reviewable outcome. It must state:

1. Direct completed dependencies.
2. Consumed and produced interfaces or source documents.
3. Explicit in-scope and out-of-scope boundaries.
4. A test-first sequence: failing test, expected failure, minimum implementation and focused verification.
5. Evidence checkpoint, acceptance criteria and reviewer checklist.

A task may not depend on an unnamed future activity, repeat another task by reference or leave implementation policy implicit. If a capability has a different owner, outcome or verification command, it is a separate task.

## Execution order

### Backend capability stream

BE-001 → BE-002 → BE-003 → BE-004 → BE-005 → BE-006

BE-004 + BE-005 + BE-006 → BE-007 → BE-008 → BE-009

BE-008 + BE-005 → BE-010 → BE-011 → BE-012 → BE-013 → BE-014

BE-005 → BE-015 → BE-016 → BE-017 → BE-018 → BE-019

BE-011 → BE-020 → BE-021

BE-011 → BE-022 → BE-023 → BE-024

BE-015 + BE-024 → BE-025 → BE-026

### Frontend stream

BE-026 → FE-001 → FE-002 → FE-003 → FE-004 → FE-005 → FE-006 → FE-007 → FE-008 → FE-009 → FE-010

### Full-system release gates

BE-026 + FE-010 → BE-027 → BE-028

## Active task index

### Backend

| ID | Outcome |
|---|---|
| [BE-001](backend/BE-001.md) | Backend package, app factory and health endpoints |
| [BE-002](backend/BE-002.md) | Backend runtime configuration and local Compose services |
| [BE-003](backend/BE-003.md) | SQL Server migration baseline and database identities |
| [BE-004](backend/BE-004.md) | Organization registry, RLS predicate and pre-login tenant resolver |
| [BE-005](backend/BE-005.md) | Audit and outbox transactional persistence |
| [BE-006](backend/BE-006.md) | OpenAPI base and backend CI quality gates |
| [BE-007](backend/BE-007.md) | Argon2id credential validation and login |
| [BE-008](backend/BE-008.md) | Access JWT verification and protected principal |
| [BE-009](backend/BE-009.md) | Refresh-session rotation, revoke and CSRF boundary |
| [BE-010](backend/BE-010.md) | Data-driven RBAC and authorization service |
| [BE-011](backend/BE-011.md) | Tenant middleware, pool cleanup, organization settings and RLS catalog enforcement |
| [BE-012](backend/BE-012.md) | Bibliographic book catalog |
| [BE-013](backend/BE-013.md) | Locations and individually tracked copies |
| [BE-014](backend/BE-014.md) | Copy status transition and append-only history |
| [BE-015](backend/BE-015.md) | Durable dispatcher, job records, lease, retry and deduplication |
| [BE-016](backend/BE-016.md) | Loan request, approval, checkout and return lifecycle |
| [BE-017](backend/BE-017.md) | Concurrent checkout locking and idempotency replay |
| [BE-018](backend/BE-018.md) | Reservation queue, hold expiry and allocation |
| [BE-019](backend/BE-019.md) | Overdue calculation and scheduled circulation jobs |
| [BE-020](backend/BE-020.md) | Education entities and tenant-scoped relations |
| [BE-021](backend/BE-021.md) | Education borrower-policy adapter and loan snapshots |
| [BE-022](backend/BE-022.md) | Public members, membership plans and subscription policy |
| [BE-023](backend/BE-023.md) | Fine calculation, invoices and immutable allocations |
| [BE-024](backend/BE-024.md) | Signed payment webhook, reconciliation and payment idempotency |
| [BE-025](backend/BE-025.md) | In-app notification persistence and read workflow |
| [BE-026](backend/BE-026.md) | Email delivery consumer, bounded retry and worker observability |
| [BE-027](backend/BE-027.md) | Full integration, security and release-evidence verification |
| [BE-028](backend/BE-028.md) | Production configuration, clean-host deploy, backup and rollback rehearsal |

### Frontend

| ID | Outcome |
|---|---|
| [FE-001](frontend/FE-001.md) | Frontend bootstrap, product UI context, tokens and test tooling |
| [FE-002](frontend/FE-002.md) | App shell, familiar navigation and accessible shared controls |
| [FE-003](frontend/FE-003.md) | Login, refresh session and protected-route behavior |
| [FE-004](frontend/FE-004.md) | Typed API client, Problem Details and common request states |
| [FE-005](frontend/FE-005.md) | Catalog search and book browsing |
| [FE-006](frontend/FE-006.md) | Inventory, locations, copies and status-management workspace |
| [FE-007](frontend/FE-007.md) | Circulation desk for request, approval, checkout and return |
| [FE-008](frontend/FE-008.md) | Reservation status and notification inbox |
| [FE-009](frontend/FE-009.md) | Education management and borrower-policy views |
| [FE-010](frontend/FE-010.md) | Public membership, fine, payment and invoice views |

## Legacy mapping

| Legacy task | Active replacement |
|---|---|
| [TASK-001](legacy/TASK-001.md) | Phase 0 documentation baseline; no active replacement |
| [TASK-002](legacy/TASK-002.md) | BE-001 through BE-006 and FE-001 |
| [TASK-003](legacy/TASK-003.md) | BE-007 through BE-010 |
| [TASK-004](legacy/TASK-004.md) | BE-004 and BE-011 |
| [TASK-005](legacy/TASK-005.md) | BE-012 through BE-014 and FE-005 through FE-006 |
| [TASK-006](legacy/TASK-006.md) | BE-015 through BE-019 and FE-007 through FE-008 |
| [TASK-007](legacy/TASK-007.md) | BE-020 through BE-021 and FE-009 |
| [TASK-008](legacy/TASK-008.md) | BE-022 through BE-024 and FE-010 |
| [TASK-009](legacy/TASK-009.md) | BE-025 through BE-026 and FE-008 |
| [TASK-010](legacy/TASK-010.md) | FE-001 through FE-010 |
| [TASK-011](legacy/TASK-011.md) | BE-027 |
| [TASK-012](legacy/TASK-012.md) | BE-028 |

## Completion evidence

A task is complete only when its focused test and task-specific evidence checkpoint have fresh command output. Its reviewer checklist must be resolved, and any OpenAPI, migration, RLS, authorization, audit/outbox or UI accessibility impact must be included in that evidence.
