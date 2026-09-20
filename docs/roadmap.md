# Roadmap OpenLibraryOS

## Phase 0 — Architecture preparation

Deliverables: governance files, architecture/system/database/API/security/deployment/development/testing docs, task backlog và target folder structure.

Checkpoint: tài liệu không còn planning marker chưa giải quyết, các module boundary nhất quán, RLS/auth/data decisions được review.

## Phase 1 — Project foundation

Tạo Flask app factory, React/Vite package, Compose services, configuration, health endpoints, initial migration, CI skeleton và OpenAPI base.

Checkpoint: app starts, frontend builds, database migration succeeds, Compose config validates và CI xanh.

## Phase 2 — Authentication + RBAC

Tạo user/profile, Argon2id, login, JWT access, refresh rotation/revocation, role/permission management và audit login events.

Checkpoint: auth/API/security tests pass; revoked/rotated tokens không dùng lại được.

## Phase 3 — Organization + multi-tenancy

Tạo organization settings, tenant middleware, SQL Server RLS filter/block policies, tenant seed và cross-tenant tests.

Checkpoint: RLS chặn read/write/insert sai tenant và connection pool reset được chứng minh bằng integration test.

## Phase 4 — Book management

Tạo books, copies, barcode, location và inventory state history.

Checkpoint: book/copy/location API và state transition tests pass.

## Phase 5 — Borrowing system

Tạo request/approval/direct checkout/return/overdue/reservation queue, hold expiry và policy snapshot.

Checkpoint: end-to-end circulation workflow và concurrent checkout tests pass.

## Phase 6 — Education edition

Tạo student, teacher, department, class, course, semester và borrower policy resolver.

Checkpoint: student max 5/14 days và teacher max 20/90 days được cấu hình qua policy, không hard-code controller.

## Phase 7 — Public library edition

Tạo member, membership plan, subscription, fine, payment và invoice với idempotency.

Checkpoint: plan snapshot, fine calculation và payment retry tests pass.

## Phase 8 — Notification

Tạo in-app notification, Celery jobs, retry/backoff, email adapter và delivery status.

Checkpoint: notification jobs retry an toàn, dead-letter visibility có runbook.

## Phase 9 — Testing and hardening

Hoàn thiện integration/E2E, performance baseline, security scan, OpenAPI compatibility, observability và backup restore drill.

Checkpoint: CI toàn phần xanh, không còn critical/high security finding mở.

## Phase 10 — Deployment

Tạo production Compose profile, Nginx/TLS, secret strategy, migration job, backup/restore và rollback runbook.

Checkpoint: clean host deploy được, readiness/alerts hoạt động, restore drill và rollback rehearsal có evidence.
