# OpenLibraryOS Rollback and Forward-Fix Rehearsal Runbook

## 1. Principles and Strategy

In production, rollbacks must prioritize system stability and zero data loss. The rollback strategy is divided into three distinct operational scenarios:

1. **Application-Only Rollback**:
   - Used when schema changes are backward-compatible, but the application code exhibits regressions or critical bugs.
   - Simply revert the container image tag to the previously verified immutable tag.
2. **Reversible Schema Rollback (Pre-Ingestion Window)**:
   - Used when a migration is newly applied during a maintenance window and no business data has been written yet.
   - Only permitted for migrations designated as `"action": "rollback"` in the release manifest.
3. **Forward-Fix Migration (Post-Ingestion & Destructive Changes)**:
   - Mandated for migrations designated as `"action": "forward-fix"`.
   - Once tenant records, loans, fines, payments, or users are written, dropping tables or columns causes catastrophic data loss.
   - Destructive rollback is strictly prohibited. An expedited forward-fix migration must be prepared, reviewed, and deployed.

---

## 2. Migration Rollback vs Forward-Fix Decision Matrix

The following decision matrix covers all 19 Alembic migrations in OpenLibraryOS (source of truth: `infra/release/release_manifest.json`):

| Migration Revision | Name | Decision | Technical Rationale |
|---|---|---|---|
| `0001_database_identities` | Initial Schemas & Guards | **Rollback** | Reversible: drops empty schemas and initial guard predicates in reverse order. |
| `0002_organizations_rls` | Tenant Root & RLS Engine | **Forward-Fix** | Non-reversible once tenants exist: dropping `core.organizations` destroys tenant master keys and root identities. |
| `0003_audit_outbox` | Audit & Outbox Tables | **Forward-Fix** | Destructive: audit and outbox logs are immutable regulatory records; hard-delete/drop prohibited by retention contract. |
| `0004_users_profiles` | Users & Profiles | **Forward-Fix** | Destructive: dropping `core.users` or `core.user_profiles` causes permanent loss of user credentials and tenant member profiles. |
| `0005_refresh_sessions` | Refresh Token Storage | **Rollback** | Reversible: refresh sessions are ephemeral; dropping table invalidates active sessions cleanly without data corruption. |
| `0006_rbac` | Roles, Permissions & Grants | **Forward-Fix** | Destructive: dropping access control matrix destroys tenant authorizations and custom roles. |
| `0007_tenant_context_catalog` | Security Context Catalog | **Rollback** | Reversible: drops catalog verification functions and stored procedures cleanly without affecting table data. |
| `0008_books` | Bibliographic Catalog | **Forward-Fix** | Destructive: dropping `core.books` causes irreversible bibliographic loss; forward-fix migration required once books are cataloged. |
| `0009_locations_and_book_copies`| Physical Inventory & Branches | **Forward-Fix** | Destructive: physical copy barcodes, accession numbers, and library branch locations cannot be recovered if dropped. |
| `0010_copy_status_history` | Copy Transition History | **Forward-Fix** | Destructive: historical copy transition logs are mandatory audit evidence under asset governance. |
| `0011_outbox_claim_jobs` | Outbox Claim Functions | **Rollback** | Reversible: drops claim procedure and job records without altering base outbox event table. |
| `0012_loans` | Circulation & Loans | **Forward-Fix** | Destructive: active checkout records and historical loan ledgers are subject to statutory financial/asset retention. |
| `0013_idempotency_keys` | API Idempotency Store | **Rollback** | Reversible: idempotency records have 24-hour TTL; dropping table safely forces fresh idempotency evaluations. |
| `0014_reservations` | Patron Hold Queues | **Forward-Fix** | Destructive: patron queue positions, hold priorities, and reservation states cannot be discarded. |
| `0015_education_entities` | Academic Rosters & Courses | **Forward-Fix** | Destructive: school departments, academic classes, reading lists, and student rosters must not be deleted. |
| `0016_public_library_memberships`| Patron Cards & Subscriptions | **Forward-Fix** | Destructive: patron library cards, active membership subscriptions, and plan assignments must be preserved. |
| `0017_public_library_fines_invoices`| Ledger Fines & Invoices | **Forward-Fix** | Destructive: financial accounting invoices and overdue penalty ledgers are strictly governed by financial regulations. |
| `0018_public_library_payment_webhooks`| Payment Ledger & Allocations | **Forward-Fix** | Destructive: payment provider webhook transactions and fee allocations are financial source-of-truth records. |
| `0019_notifications` | User Inbox & Notifications | **Rollback** | Reversible: notifications represent delivered transient messages; table can be dropped and recreated if uncommitted. |

---

## 3. Operational Procedures

### Scenario A: Application Rollback (Image Switch)

When reverting code regressions without changing the database schema:

```bash
# 1. Update APP_IMAGE in production.env to previous release tag (e.g. 1.0.0 -> 0.9.9)
sed -i 's/APP_IMAGE=openlibrary\/backend:1.0.0/APP_IMAGE=openlibrary\/backend:0.9.9/' production.env

# 2. Pull the target previous image
docker compose -f infra/docker-compose.yml --env-file production.env pull app worker

# 3. Gracefully recreate app and worker containers
docker compose -f infra/docker-compose.yml --env-file production.env up -d --no-deps app worker

# 4. Confirm healthcheck readiness
docker compose -f infra/docker-compose.yml --env-file production.env ps app worker
curl -sk https://localhost/api/v1/health/live
curl -sk https://localhost/api/v1/health/ready
```

### Scenario B: Migration Rollback (Reversible Only)

To roll back a reversible migration (`0019_notifications`) before live traffic:

```bash
# 1. Temporarily drain external traffic via Nginx maintenance mode or stop edge
docker compose -f infra/docker-compose.yml --env-file production.env stop nginx app worker

# 2. Run Alembic downgrade one revision using migration identity
docker compose -f infra/docker-compose.yml --profile migration --env-file production.env run --rm migration \
  python -m alembic downgrade -1

# 3. Confirm target revision
docker compose -f infra/docker-compose.yml --profile migration --env-file production.env run --rm migration \
  python -m alembic current

# 4. Verify runtime identity restrictions
docker compose -f infra/docker-compose.yml --profile migration --env-file production.env run --rm migration \
  python scripts/run_migrations.py --verify-only

# 5. Restart application and edge services
docker compose -f infra/docker-compose.yml --env-file production.env up -d app worker nginx
```

### Scenario C: Forward-Fix Migration Procedure

When an issue occurs on a non-reversible migration:

```bash
# 1. Create a forward-fix migration in backend/migrations/versions (e.g., 0020_forward_fix_issue.py)
# 2. Test the forward fix in isolated integration environment:
python -m pytest backend/tests/integration/migrations/ -q

# 3. Deploy the forward-fix image and run the migration job:
docker compose -f infra/docker-compose.yml --profile production-migration --env-file production.env run --rm migration

# 4. Restart runtime containers and verify health:
docker compose -f infra/docker-compose.yml --env-file production.env up -d app worker
curl -sk https://localhost/api/v1/health/ready
```

---

## 4. Rollback Rehearsal Evidence and Validation

During release rehearsal testing:
- **Application Image Reversion**: Verified container pull and restart without service interruption or state loss.
- **Downgrade Safety Check**: Verified that attempted downgrades on destructive tables (`core.books`, `core.loans`, `ops.audit_events`) are rejected by policy, enforcing forward-fix compliance.
- **Alembic History Verification**: Confirmed `alembic current` accurately reflects database status at all times.
