# BE-022 Implementation Plan — Public members, membership plans and subscription policy

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manage public-library members, configurable plans and subscription validity as a borrowing-policy provider.

**Architecture:** Add `openlibrary.modules.public_library` containing domain entities, application service, policy adapter conforming to core's `BorrowingPolicyResolver` port, SQL Server infrastructure store with tenant isolation and RLS, and REST API adapters.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy 2.x, Alembic, MS SQL Server, pytest, OpenAPI 3.1.

**Spec:** `tasks/backend/BE-022.md`

## Global Constraints

- Backend remains a modular monolith; no circular imports or core module imports of public_library.
- All persistent data retains tenant boundary with `organization_id NOT NULL` and RLS predicates.
- Red-green-refactor discipline strictly enforced: write failing integration test first.
- RFC 7807 Problem Details for all API errors; explicit HTTP status codes.
- No money state or finance calculation in membership policy code.
- Loan policy snapshot is captured at checkout and remains immutable after plan updates.

---

### Task 1: Failing Integration Test (Test-First Red)

**Files:**
- Create: `backend/tests/integration/public_library/test_membership.py`

**Interfaces:**
- Consumes: `BorrowingPolicyResolver` from `core.application.loans`, `LoanService`, `PublicLibraryBorrowingPolicyAdapter`.
- Produces: Test suite validating subscription validity, plan selection, tenant isolation, loan checkout snapshot immutability, and zero public library imports in core.

- [ ] **Step 1: Write the failing integration test**
- [ ] **Step 2: Run pytest to record the expected ImportError / failure**

---

### Task 2: Domain Layer & Application Port

**Files:**
- Create: `backend/src/openlibrary/modules/public_library/__init__.py`
- Create: `backend/src/openlibrary/modules/public_library/domain.py`
- Create: `backend/src/openlibrary/modules/public_library/application.py`
- Test: `backend/tests/unit/public_library/test_public_library_domain.py`

**Interfaces:**
- Consumes: `core.application.access_tokens.Principal`, `core.application.authorization.AuthorizationPort`.
- Produces: `Member`, `MembershipPlan`, `Subscription`, `PublicLibraryStore`, `PublicLibraryService`, seed defaults.

- [ ] **Step 1: Implement domain entities, status constants, and exceptions**
- [ ] **Step 2: Implement store protocol and application service**
- [ ] **Step 3: Add unit tests for domain and application service**

---

### Task 3: Policy Adapter

**Files:**
- Create: `backend/src/openlibrary/modules/public_library/policy.py`

**Interfaces:**
- Consumes: `core.application.loans.BorrowingPolicy`, `BorrowingPolicyResolver`, `core.domain.loans.BorrowerNotEligibleError`.
- Produces: `PublicLibraryBorrowingPolicyAdapter`.

- [ ] **Step 1: Implement `PublicLibraryBorrowingPolicyAdapter`**
- [ ] **Step 2: Run integration tests to verify adapter logic passes in isolation**

---

### Task 4: Database Migration & Infrastructure Store

**Files:**
- Create: `backend/migrations/versions/0016_public_library_memberships.py`
- Create: `backend/src/openlibrary/modules/public_library/infrastructure.py`
- Create: `backend/tests/unit/migrations/test_public_library_migration.py`

**Interfaces:**
- Consumes: `SqlServerTenantContext` from `core.infrastructure.tenancy`.
- Produces: `SqlServerPublicLibraryStore` and Alembic migration `0016_public_library_memberships`.

- [ ] **Step 1: Implement Alembic migration with RLS predicates and composite tenant constraints**
- [ ] **Step 2: Implement `SqlServerPublicLibraryStore` with parameterized queries and seed method**
- [ ] **Step 3: Add migration structure test**

---

### Task 5: HTTP API Adapter & OpenAPI Contract

**Files:**
- Create: `backend/src/openlibrary/modules/public_library/api.py`
- Modify: `backend/src/openlibrary/app/config.py`
- Modify: `backend/src/openlibrary/app/factory.py`
- Modify: `backend/src/openlibrary/app/runtime.py`
- Modify: `contracts/openapi/v1.yaml`
- Test: `backend/tests/api/public_library/test_public_library_api.py`

**Interfaces:**
- Consumes: `PublicLibraryService`, `create_public_library_blueprint`.
- Produces: Public library REST endpoints with RFC 7807 error handling.

- [ ] **Step 1: Implement API blueprint and route handlers**
- [ ] **Step 2: Register blueprint in factory and runtime**
- [ ] **Step 3: Add OpenAPI spec paths and schemas in `v1.yaml`**
- [ ] **Step 4: Add API tests**

---

### Task 6: Full Verification & Evidence Checkpoint Recording

**Files:**
- Modify: `tasks/backend/BE-022.md`

- [ ] **Step 1: Run pytest across the entire test suite**
- [ ] **Step 2: Run ruff check, ruff format --check, mypy src**
- [ ] **Step 3: Run openapi_spec_validator and check_compatibility.py**
- [ ] **Step 4: Update `tasks/backend/BE-022.md` with status Completed, checkpoint evidence, and review notes**
