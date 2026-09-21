# BE-005 Audit and Outbox Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a protected mutation, immutable audit event, and durable outbox event in the same SQL Server transaction.

**Architecture:** A SQL Server migration extends the existing tenant security policy with two `ops` tables and creates tenant-first indexes. The infrastructure transaction writer obtains `organization_id` from SQL Server `SESSION_CONTEXT`, validates JSON event payloads before writing, and uses a new transaction or savepoint around a caller-provided mutation plus the audit and outbox inserts.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, Alembic, SQL Server, pytest.

**Spec:** `tasks/backend/BE-005.md`

## Global Constraints

- Reuse `core.tenant_access_predicate` and require the runtime SQL principal's session context for tenant ownership.
- Audit rows remain append-only: the runtime principal receives insert permission but explicit update and delete denials.
- Event payloads reject secret, token, password, PAN, CVV, card-number, and raw-payment keys before any database write.
- No worker claim, delivery, retry, email, or notification implementation is added.
- Every behavior change follows red-green-refactor and records command output in `tasks/backend/BE-005.md`.

---

### Task 1: Specify the failing SQL Server contract

**Files:**
- Create: `backend/tests/integration/ops/test_audit_outbox.py`

**Interfaces:**
- Consumes: `bootstrap_database_identities`, `run_migrations`, `set_tenant_context`, and a runtime SQLAlchemy `Connection`.
- Produces: integration coverage for table/RLS catalog shape, atomic commit and rollback, append-only audit rows, and sensitive-payload rejection.

- [ ] **Step 1: Write the failing test**

```python
def test_audit_and_outbox_tables_are_tenant_protected(
    seeded_database_urls: dict[str, str],
) -> None:
    assert _table_names(seeded_database_urls["DATABASE_BOOTSTRAP_URL"]) >= {
        "ops.audit_events",
        "ops.outbox_events",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/ops/test_audit_outbox.py -q`

Expected: FAIL because the migrated database has neither required `ops` table.

### Task 2: Add tenant-scoped persistence schema

**Files:**
- Create: `backend/migrations/versions/0003_audit_outbox.py`
- Modify: `docs/database-design.md`

**Interfaces:**
- Consumes: `core.tenant_access_predicate` and `core.organization_tenant_policy` from revision `0002_organizations_rls`.
- Produces: `ops.audit_events` and `ops.outbox_events` with RLS, `SESSION_CONTEXT`-derived organization inserts, JSON checks, foreign keys, tenant-first indexes, and runtime audit immutability.

- [ ] **Step 1: Write minimal migration**

```python
revision = "0003_audit_outbox"
down_revision = "0002_organizations_rls"

op.execute(
    "ALTER SECURITY POLICY core.organization_tenant_policy "
    "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
    "ON ops.audit_events"
)
```

- [ ] **Step 2: Run the table/RLS integration test**

Run: `python -m pytest tests/integration/ops/test_audit_outbox.py -q`

Expected: table catalog assertions pass; transaction-writer assertions remain red until Task 3.

### Task 3: Implement the audited transaction port

**Files:**
- Create: `backend/src/openlibrary/modules/ops/application/persistence.py`
- Create: `backend/src/openlibrary/modules/ops/infrastructure/sqlserver.py`

**Interfaces:**
- Consumes: a SQLAlchemy `Connection`, `AuditEvent`, `OutboxEvent`, and `Callable[[Connection], T]` mutation.
- Produces: `SqlServerAuditedTransaction.run(connection, mutation, audit_event, outbox_events) -> T`.

- [ ] **Step 1: Implement the public contract**

```python
@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: str
    entity_type: str
    entity_id: UUID
    payload: Mapping[str, object]
    correlation_id: UUID

class AuditedTransaction(Protocol):
    def run(
        self,
        connection: Connection,
        mutation: Callable[[Connection], T],
        audit_event: AuditEvent,
        outbox_events: Sequence[OutboxEvent],
    ) -> T: ...
```

- [ ] **Step 2: Implement the smallest SQL Server writer**

```python
transaction = connection.begin_nested() if connection.in_transaction() else connection.begin()
with transaction:
    result = mutation(connection)
    self._insert_audit(connection, audit_event)
    for event in outbox_events:
        self._insert_outbox(connection, event)
return result
```

- [ ] **Step 3: Run focused integration coverage**

Run: `python -m pytest tests/integration/ops/test_audit_outbox.py -q`

Expected: PASS against SQL Server; commit creates all records and a constraint-triggered rollback preserves none.

### Task 4: Verify and record evidence

**Files:**
- Modify: `tasks/backend/BE-005.md`

- [ ] **Step 1: Run focused and complete backend checks**

Run: `python -m pytest tests/integration/ops/test_audit_outbox.py -q; python -m pytest -q; python -m ruff check .; python -m mypy src`

Expected: focused SQL Server coverage, full suite, Ruff, and mypy all exit `0`.

- [ ] **Step 2: Run delegated review**

Run: `ocr delegate preview --format json --background "BE-005 audit/outbox transactional persistence"`

Expected: every reviewable file is classified, reviewed, and any critical/high finding is fixed before completion.

- [ ] **Step 3: Record evidence**

Append the actual RED, GREEN, final-verification, and review outputs to `tasks/backend/BE-005.md` without claiming checks that did not run.
