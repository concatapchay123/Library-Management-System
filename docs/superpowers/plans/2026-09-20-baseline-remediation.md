# Baseline Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Phase 0 blueprint internally consistent, security-complete and executable as a sequence of implementation tasks.

**Architecture:** Establish one authoritative set of decisions for tenant discovery, platform control, database roles, RLS, audit/outbox and data lifecycle. Existing design documents keep their specialist detail and link to those decisions; task dependencies are reordered so no required protection or operational primitive arrives after its consumer.

**Tech Stack:** Markdown documentation, planned Flask/SQLAlchemy 2.x application, SQL Server RLS, Redis/Celery and React/TypeScript.

**Spec:** `docs/foundational-decisions.md`

## Global Constraints

- Phase 0 remains documentation-only: do not add application code, runtime configuration, migrations or generated contracts.
- Tenant-owned data always has `organization_id NOT NULL`; explicitly documented control-plane tables are the only exception.
- API never trusts a client-supplied tenant id for authorization.
- Runtime and migration database identities are distinct and least-privilege.
- Mutations requiring audit or asynchronous work use one database transaction with audit and outbox records.
- Preserve the modular-monolith boundary and do not introduce microservices.

---

### Task 1: Record foundational architecture decisions

**Files:**
- Create: `docs/foundational-decisions.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Produces: the authoritative terms `tenant-discovery`, `platform control plane`, `runtime identity`, `migration identity`, `audit event`, and `outbox event` for all later documentation and tasks.

- [ ] **Step 1: Define tenant discovery and platform control.**
  Specify the required `organization_slug` login input, authenticated-JWT tenant derivation, and out-of-band platform control plane.

- [ ] **Step 2: Define database isolation mechanics.**
  Specify least-privilege identities, fail-closed RLS context handling, composite tenant foreign keys, and migration-policy verification.

- [ ] **Step 3: Define transactional event delivery and data lifecycle.**
  Specify append-only audit records, durable outbox events, consumer idempotency, expiry/retention, PII minimization and deletion/anonymization boundaries.

- [ ] **Step 4: Verify document discoverability.**
  Run: `rg -n "Foundational decisions|foundational-decisions" docs README.md`
  Expected: the new decision source is linked by the documentation index and architecture document.

### Task 2: Align authentication, API and security contracts

**Files:**
- Modify: `docs/api-design.md`
- Modify: `docs/security.md`
- Modify: `DESIGN.md`
- Modify: `RULES.md`

**Interfaces:**
- Consumes: `organization_slug`, platform control plane and token requirements from `docs/foundational-decisions.md`.
- Produces: unambiguous public authentication, JWT, webhook, request-correlation and privacy requirements.

- [ ] **Step 1: Make tenant selection explicit only at the login boundary.**
  Describe the login request shape and uniform authentication failure response; prohibit tenant selection after authentication.

- [ ] **Step 2: Complete security edge contracts.**
  Add JWT issuer/audience/algorithm/key-rotation rules, Redis rate-limit outage policy, request-id validation, signed webhook replay protection and idempotency-record data minimization.

- [ ] **Step 3: Add PII and platform-operation boundaries.**
  Document data classification, retention/anonymization, and a non-user-facing platform control plane.

- [ ] **Step 4: Verify contractual terms.**
  Run: `rg -n "organization_slug|issuer|audience|key rotation|webhook|retention|X-Request-ID" docs DESIGN.md RULES.md`
  Expected: every term appears in its governing documentation.

### Task 3: Make data model and asynchronous design enforceable

**Files:**
- Modify: `docs/database-design.md`
- Modify: `docs/system-design.md`
- Modify: `docs/testing-strategy.md`

**Interfaces:**
- Consumes: tenant and outbox definitions from `docs/foundational-decisions.md`.
- Produces: migration requirements for composite keys/RLS and test cases for atomic audit/outbox dispatch.

- [ ] **Step 1: Define tenant relationship constraints.**
  Require a `(organization_id, id)` unique key on tenant parents and composite foreign keys on tenant children; enumerate exceptions explicitly.

- [ ] **Step 2: Define audit/outbox tables and dispatcher semantics.**
  Add immutable audit records and durable outbox events with delivery lease, retry, payload version and idempotency key.

- [ ] **Step 3: Define money and scheduled-worker boundaries.**
  Specify payment lifecycle, signed webhooks, reconciliation and the way reservation/payment jobs inherit server-created tenant context.

- [ ] **Step 4: Verify coverage.**
  Run: `rg -n "composite foreign key|outbox|dispatcher|webhook|reconciliation" docs`
  Expected: database, system design and testing documents cover each implementation boundary.

### Task 4: Reorder task backlog and operational release gates

**Files:**
- Modify: `tasks/TASK-002.md`
- Modify: `tasks/TASK-003.md`
- Modify: `tasks/TASK-004.md`
- Modify: `tasks/TASK-006.md`
- Modify: `tasks/TASK-008.md`
- Modify: `tasks/TASK-009.md`
- Modify: `tasks/TASK-011.md`
- Modify: `tasks/TASK-012.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/deployment.md`

**Interfaces:**
- Consumes: all foundational decisions.
- Produces: an implementable order where audit/RLS/outbox exist before a task requires them, and measurable release objectives.

- [ ] **Step 1: Move foundational control-plane, audit and RLS prerequisites earlier.**
  Make project foundation establish schema/bootstrap contracts; make authentication migrations create RLS protection with their tenant tables.

- [ ] **Step 2: Move generic outbox/job support before circulation and payment consumers.**
  Make circulation own its required generic dispatcher, while notification work remains focused on notification/email behavior.

- [ ] **Step 3: Add payment security/reconciliation and privacy tests.**
  Add failing-test-first requirements for signature validation, replay rejection, pending-payment resolution, partial/refund rules and retained-data checks.

- [ ] **Step 4: Make operations measurable.**
  Add production RPO/RTO, backup retention, restore cadence/ownership and alert thresholds to the release gate.

- [ ] **Step 5: Verify dependency and terminology consistency.**
  Run: `rg -n "Dependencies|audit|outbox|RLS|RPO|RTO|webhook" tasks docs/roadmap.md docs/deployment.md`
  Expected: no task requires an audit, RLS or job primitive scheduled only in a later dependency.

### Task 5: Review and verify the documentation change

**Files:**
- Review: every changed Markdown file

- [ ] **Step 1: Run link/reference and placeholder scans.**
  Run: `rg -n -i "T[O]DO|T[B]D|implement[[:space:]]later|fill[[:space:]]in[[:space:]]details" docs tasks DESIGN.md RULES.md`
  Expected: no newly introduced planning placeholders.

- [ ] **Step 2: Inspect the complete diff.**
  Run: `git diff --check; git diff --stat; git diff -- docs tasks DESIGN.md RULES.md`
  Expected: no whitespace errors and every changed document supports a stated remediation.

- [ ] **Step 3: Run delegated Open Code Review.**
  Run: `ocr delegate preview --format json`, then resolve the rule set and review every returned Markdown file.
  Expected: all reviewable changed files are accounted for; no critical or high finding remains.

## Plan Self-Review

- Coverage: Tasks 1–4 cover tenant discovery, RLS/database identities, audit/outbox ordering, composite constraints, payment hardening, privacy, and operational goals.
- Placeholders: the plan contains no unresolved planning marker, deferred implementation marker, or unspecified testing command.
- Consistency: all task terminology is defined by `docs/foundational-decisions.md` before it is consumed by dependent documents.
