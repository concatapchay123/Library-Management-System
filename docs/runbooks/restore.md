# OpenLibraryOS Disaster Recovery & Restore Runbook

## 1. Objectives and Service Level Contracts

This runbook defines the operational procedure for backup creation, encryption, retention, and quarterly isolated restore drills for OpenLibraryOS.

- **Recovery Point Objective (RPO)**: At most 15 minutes (guaranteed by continuous transaction log backups).
- **Recovery Time Objective (RTO)**: At most 4 hours (measured from incident declaration to verified production readiness).
- **Backup Retention Period**: At least 35 days (retained in immutable, encrypted storage).
- **Monthly Availability Target**: 99.5% uptime.
- **Contract Enforcement**: Governed by `infra/release/release_manifest.json` and monitored via ops metrics.

---

## 2. Backup Strategy and Schedule

| Backup Type | Frequency | Window | Encryption | Retention | Destination |
|---|---|---|---|---|---|
| **Full Backup** | Weekly | Sunday 02:00 UTC | AES-256 | >= 35 days | Cold Object Storage (Immutable WORM) |
| **Differential** | Daily | Mon–Sat 02:00 UTC | AES-256 | >= 35 days | Warm Object Storage |
| **Transaction Log**| Every 15 min | Continuous 24/7 | AES-256 | >= 35 days | Warm Object Storage |

### Key Management Invariant
The backup encryption certificate/key is strictly managed in an external Secret Manager/KMS. **Under no circumstances is the encryption key stored on the database server or alongside backup archives.**

---

## 3. SQL Server Backup Script (Automated Cron Job)

Executed by the database maintenance operator:

```sql
-- 1. Full Backup (Weekly)
BACKUP DATABASE [openlibrary]
TO DISK = N'/var/opt/mssql/backup/openlibrary_full_latest.bak'
WITH FORMAT, INIT, COMPRESSION,
     ENCRYPTION (ALGORITHM = AES_256, SERVER CERTIFICATE = [OpenLibraryBackupCert]),
     STATS = 10;

-- 2. Differential Backup (Daily)
BACKUP DATABASE [openlibrary]
TO DISK = N'/var/opt/mssql/backup/openlibrary_diff_latest.bak'
WITH DIFFERENTIAL, INIT, COMPRESSION,
     ENCRYPTION (ALGORITHM = AES_256, SERVER CERTIFICATE = [OpenLibraryBackupCert]),
     STATS = 10;

-- 3. Transaction Log Backup (Every 15 min)
DECLARE @logname NVARCHAR(256) = N'/var/opt/mssql/backup/log_' + REPLACE(CONVERT(VARCHAR(20), GETUTCDATE(), 120), ':', '-') + '.trn';
BACKUP LOG [openlibrary]
TO DISK = @logname
WITH INIT, COMPRESSION,
     ENCRYPTION (ALGORITHM = AES_256, SERVER CERTIFICATE = [OpenLibraryBackupCert]),
     STATS = 10;
```

---

## 4. Quarterly Isolated Restore Drill (Step-by-Step)

The restore drill must be executed in a dedicated, isolated sandbox environment completely detached from production networks.

### Step 1: Provision Isolated Sandbox Environment

Spin up an ephemeral, clean SQL Server container attached only to a private isolated bridge network:

```bash
docker run -d --name restore-drill-db \
  --network none \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_PID=Developer" \
  -e "MSSQL_SA_PASSWORD=${DRILL_SA_PASSWORD}" \
  -v "$(pwd)/infra/backup_drill:/var/opt/mssql/backup:ro" \
  mcr.microsoft.com/mssql/server:2022-CU14-ubuntu-22.04
```

### Step 2: Restore Full Database Backup with NORECOVERY

```sql
RESTORE DATABASE [openlibrary_restored]
FROM DISK = N'/var/opt/mssql/backup/openlibrary_full_latest.bak'
WITH NORECOVERY,
     MOVE N'openlibrary' TO N'/var/opt/mssql/data/openlibrary_drill.mdf',
     MOVE N'openlibrary_log' TO N'/var/opt/mssql/data/openlibrary_drill.ldf',
     REPLACE;
```

### Step 3: Restore Differential Backup with NORECOVERY

```sql
RESTORE DATABASE [openlibrary_restored]
FROM DISK = N'/var/opt/mssql/backup/openlibrary_diff_latest.bak'
WITH NORECOVERY;
```

### Step 4: Restore Transaction Logs Sequence with RECOVERY

Apply every transaction log up to the designated recovery target point-in-time:

```sql
-- Apply intermediate log archives
RESTORE LOG [openlibrary_restored]
FROM DISK = N'/var/opt/mssql/backup/log_2026-09-23-11-45-00.trn'
WITH NORECOVERY;

-- Apply final log archive with RECOVERY to bring database online
RESTORE LOG [openlibrary_restored]
FROM DISK = N'/var/opt/mssql/backup/log_2026-09-23-12-00-00.trn'
WITH RECOVERY;
```

### Step 5: Verify Database Usability & Integrity

Execute physical and logical database consistency checks:

```sql
-- Check database accessibility
SELECT DB_NAME() AS [DatabaseName], state_desc FROM sys.databases WHERE name = 'openlibrary_restored';

-- Execute deep DBCC consistency check
DBCC CHECKDB (N'openlibrary_restored') WITH NO_INFOMSGS, ALL_ERRORMSGS;
```

### Step 6: Verify Alembic Migration Version Match

Validate that the restored database schema revision exactly matches the released version (`head` = `0019_notifications`):

```bash
python -c "
from openlibrary.infrastructure.sqlserver.migrate import connect
with connect('${RESTORED_DB_URL}') as conn:
    version = conn.fetch_value('SELECT version_num FROM alembic_version')
    print('Restored database Alembic revision:', version)
    assert version == '0019_notifications', f'Revision mismatch: {version}'
"
```

### Step 7: Run RLS & Tenant Boundary Smoke Test

Run tenant isolation verification tests against the restored database to confirm all Row-Level Security policies and cross-tenant block predicates survived restoration without corruption:

```bash
python -m pytest backend/tests/integration/release/test_release_gate.py -k "rls_catalog" -q
```

### Step 8: Retention and Legal Hold Drill

Verify that entities under legal hold cannot be purged from the restored database, and confirm audit and financial records remain intact:

```bash
python -m pytest backend/tests/integration/release/test_release_gate.py -k "retention_policy_and_legal_hold" -q
```

---

## 5. Drill Completion Criteria and Sign-Off

The restore drill is considered **PASSED** if and only if:
1. `DBCC CHECKDB` returns 0 consistency or allocation errors.
2. Alembic migration version matches expected release revision (`0019_notifications`).
3. 100% of RLS security policies on all 36 tenant tables are active (`STATE = ON`).
4. Measured RTO from restore initiation to green smoke test is `< 4 hours` (Target: < 30 minutes in drills).
5. Data delta between the last applied transaction log and source is `< 15 minutes` (RPO verified).
6. Operational owner records the signed drill report in `docs/runbooks/dr_reports/`.
