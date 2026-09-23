# BE-028 Implementation Plan — Production configuration, clean-host deploy, backup and rollback rehearsal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the verified OpenLibraryOS product to a clean host using secure runtime configuration, immutable image tags, one-time migration job with distinct identities, Nginx TLS and security headers, and prove backup/restore and rollback behavior.

**Architecture:** 
- Docker Compose production profile with immutable images, private database/Redis, readiness-gated services.
- Migration job with migration-only database identity (`openlibrary_migrator`) and runtime restriction verification.
- Nginx configuration with TLS, security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy), SPA fallback (`try_files`), and API reverse proxy.
- Release manifest with owner, jurisdiction, and retention periods (RPO <= 15 min, RTO <= 4 hours, retention >= 35 days).
- Operational runbooks for release, restore, and rollback rehearsal.

**Tech Stack:** Docker Compose, Nginx, Python 3.12, MS SQL Server 2022, Redis 7.4, PowerShell.

**Spec:** `tasks/backend/BE-028.md` & `tasks/legacy/TASK-012.md`.

## Test-First Sequence

1. **Step 1:** Add `infra/tests/test_production_release.ps1` and supporting Python verifier `infra/tests/verify_production_release.py`.
2. **Step 2:** Run `powershell -ExecutionPolicy Bypass -File infra/tests/test_production_release.ps1` and record the missing production profile and configuration failure (Red phase).
3. **Step 3:** Implement production configuration in `infra/docker-compose.yml`, `infra/nginx/default.conf`, `infra/release/release_manifest.json`, operational scripts, and runbooks.
4. **Step 4:** Run `powershell -ExecutionPolicy Bypass -File infra/tests/test_production_release.ps1` and verify all gates pass (Green phase).
5. **Step 5:** Perform clean-host deploy, backup/restore, and rollback rehearsal execution and record evidence in `tasks/backend/BE-028.md`.

## Deliverables

- `infra/tests/test_production_release.ps1` & `infra/tests/verify_production_release.py`
- `infra/docker-compose.yml` (production profile, immutable images, network restrictions, migration job)
- `infra/nginx/default.conf` & self-signed cert for testing (TLS, security headers, SPA fallback, API proxy)
- `infra/release/release_manifest.json` (owner, jurisdiction, retention, RPO <= 15m, RTO <= 4h, retention >= 35d, migration rollback decisions)
- `docs/runbooks/release.md` (Release runbook for clean-host deployment)
- `docs/runbooks/restore.md` (Restore runbook with RPO/RTO/retention proof)
- `docs/runbooks/rollback.md` (Rollback runbook with migration compatibility decisions)
- `infra/scripts/manage_dr.py` (Disaster recovery, backup, restore, and rollback rehearsal script)
- `tasks/backend/BE-028.md` (Completed evidence checkpoint and status update)
