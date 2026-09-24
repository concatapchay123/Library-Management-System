# FE-009 Education Management and Borrower-Policy Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a comprehensive and accessible education management workspace for library staff to manage student, teacher, and academic relationship records and review configured borrower loan policy values in plain language.

**Architecture:** Implement typed OpenAPI adapters for education endpoints (`/api/v1/education`), feature-oriented React components in `src/features/education` with Miller's-Law-compliant grouped forms, server error binding for date validation errors, explanatory edition-unavailable state handling (RFC 7807 Problem Details), and clean shell routing via `App.tsx` and `navigationModel.ts`.

**Tech Stack:** React 18, TypeScript (strict mode), Vite, Vitest, Testing Library, Design Tokens (`src/shared/tokens`), RFC 7807 Problem Details.

**Spec:** `tasks/frontend/FE-009.md`

## Global Constraints

- Backend endpoints consume `BE-020` (education entities) and `BE-021` (borrower policy resolver).
- Visual distinction between students and teachers without visual noise or excessive decorative elements.
- Forms with more than 5 fields must use named logical sections (`<fieldset>`, `<legend>`, section headers).
- Borrower policies are presented as read-only server configurations in plain language; client-side eligibility calculation is strictly prohibited.
- Academic date validation errors (`invalid-semester-dates`, `invalid-membership-dates`) must be attached directly to their relevant inputs.
- Edition-disabled API responses (HTTP 403 `edition-unavailable`) render an explanatory unavailable view without leaking tenant identifiers or backend configuration details.
- Adhere strictly to UI/UX cognitive invariants: Jakob's Law (clear conventions), Hick's Law (single primary action per section), Law of Proximity (semantic spacing), Miller's Law (chunked inputs), Von Restorff Effect (isolated accent CTA), WCAG AA contrast (>= 4.5:1), and nested border radius formula.
- Zero `// TODO` or placeholder comments; full output enforcement.

---

### Task 1: Typed API Client & Contract Definitions

**Files:**
- Modify: `frontend/src/shared/api/types.ts`
- Modify: `frontend/src/shared/api/apiClient.ts`
- Test: `frontend/tests/shared/api-client.test.ts`

**Interfaces:**
- Consumes: OpenAPI `/api/v1/education` endpoints.
- Produces: `Department`, `Semester`, `Course`, `Class`, `Student`, `Teacher`, `ClassMembership`, `BorrowerPolicy` types and `apiClient.education` API methods.

- [ ] **Step 1: Write failing test in `frontend/tests/shared/api-client.test.ts` for education endpoints**
Add test cases verifying `apiClient.education` methods (`departments.list`, `semesters.create`, `students.list`, `teachers.list`, `classes.createMembership`, `policies.list`, etc.).

- [ ] **Step 2: Run test to verify it fails**
Run: `npm run test -- --run tests/shared/api-client.test.ts`
Expected: FAIL due to missing `education` property on `apiClient`.

- [ ] **Step 3: Update `frontend/src/shared/api/types.ts` and `frontend/src/shared/api/apiClient.ts`**
Add all education interfaces, request/response models, and typed client endpoints.

- [ ] **Step 4: Run test to verify it passes**
Run: `npm run test -- --run tests/shared/api-client.test.ts`
Expected: PASS.

---

### Task 2: Test-First RED Spec for Education Workspace

**Files:**
- Create: `frontend/tests/features/education/education-workspace.test.tsx`

**Interfaces:**
- Consumes: `<EducationWorkspace />` component and mock responses.
- Produces: Exhaustive integration test suite validating:
  1. Grouped form rendering with semantic fieldsets and legends for forms with >5 fields.
  2. Visual distinction between student and teacher records without visual noise.
  3. Plain-language borrower policy description (server configuration, no client-side entitlement math).
  4. Edition-unavailable state (HTTP 403) with clear explanatory copy and safe return path without leaking tenant details.
  5. Academic date validation errors attached directly to date inputs.
  6. Successful creation workflows for student/teacher records, semesters, and class memberships.

- [ ] **Step 1: Write the failing test suite**
Create `frontend/tests/features/education/education-workspace.test.tsx` testing the above scenarios.

- [ ] **Step 2: Run test to verify it fails**
Run: `npm run test -- --run tests/features/education/education-workspace.test.tsx`
Expected: FAIL with module not found or missing exports.

---

### Task 3: Education Feature Subcomponents & Types

**Files:**
- Create: `frontend/src/features/education/types.ts`
- Create: `frontend/src/features/education/PeopleManager.tsx`
- Create: `frontend/src/features/education/AcademicRecordsManager.tsx`
- Create: `frontend/src/features/education/BorrowerPolicyView.tsx`
- Create: `frontend/src/features/education/EditionUnavailableState.tsx`

**Interfaces:**
- Consumes: API types and shared components (`Button`, `Input`, `Select`, `LoadingSkeleton`, `StatusMessage`, `ProblemDetailsRenderer`).
- Produces:
  - `PeopleManager`: List & grouped registration form for student/teacher profiles with clear role distinction.
  - `AcademicRecordsManager`: Semester and class management with inline date error binding.
  - `BorrowerPolicyView`: Server policy cards explaining limits and checkout effects in plain language.
  - `EditionUnavailableState`: Accessible message card when education edition is disabled for the tenant.

- [ ] **Step 1: Implement `frontend/src/features/education/types.ts`**
Define view tabs, form state interfaces, and validation structures.

- [ ] **Step 2: Implement `frontend/src/features/education/EditionUnavailableState.tsx`**
Display explanatory message with zero tenant leak and clear action to return to catalog/circulation.

- [ ] **Step 3: Implement `frontend/src/features/education/BorrowerPolicyView.tsx`**
Render student and teacher policies from backend with plain-language explanations.

- [ ] **Step 4: Implement `frontend/src/features/education/PeopleManager.tsx`**
Render distinct student/teacher items and grouped 3-section form (>5 fields: Identity & Role, Institutional Identifiers, Academic Affiliation & Status).

- [ ] **Step 5: Implement `frontend/src/features/education/AcademicRecordsManager.tsx`**
Render semesters, classes, memberships, and attach date validation errors directly to date inputs upon server error.

---

### Task 4: Education Workspace Container & Barrel Export

**Files:**
- Create: `frontend/src/features/education/EducationWorkspace.tsx`
- Create: `frontend/src/features/education/index.ts`

**Interfaces:**
- Consumes: Subcomponents and API client.
- Produces: Unified `EducationWorkspace` component handling tab switching, loading states, error states, and edition-unavailable interception.

- [ ] **Step 1: Implement `EducationWorkspace.tsx`**
Tab navigation between "People & Profiles", "Academic Records", and "Borrower Policies", data fetching, and edition-unavailable interception.

- [ ] **Step 2: Implement `index.ts`**
Export all public components and types.

- [ ] **Step 3: Run focused tests to verify GREEN**
Run: `npm run test -- --run tests/features/education/education-workspace.test.tsx`
Expected: PASS all tests in the education workspace suite.

---

### Task 5: App Shell Routing & Navigation Integration

**Files:**
- Modify: `frontend/src/app/navigation/navigationModel.ts`
- Modify: `frontend/src/app/App.tsx`
- Test: `frontend/tests/app/shell.test.tsx`
- Test: `frontend/tests/app/bootstrap.test.tsx`

**Interfaces:**
- Consumes: `<EducationWorkspace />` in `App.tsx`.
- Produces: Navigable routes for `#/education` and `#/members`.

- [ ] **Step 1: Update `navigationModel.ts` and `App.tsx`**
Integrate `education` into navigation model and `App.tsx` tab state, keeping backwards compatibility for `members`.

- [ ] **Step 2: Run all app shell and bootstrap tests**
Run: `npm run test -- --run tests/app/`
Expected: PASS.

---

### Task 6: Full Verification, OCR Review, and Evidence Checkpoint

**Files:**
- Modify: `tasks/frontend/FE-009.md` (record evidence and checkpoints)
- Modify: `skill-observations/checkpoints.log`

- [ ] **Step 1: Run comprehensive frontend test suite**
Run: `npm run test`
Expected: All tests pass (100% green).

- [ ] **Step 2: Run typecheck and linting**
Run: `npm run typecheck` and `npm run lint` and `npm run build`
Expected: 0 errors, clean production bundle.

- [ ] **Step 3: Run Open Code Review (OCR)**
Run `ocr delegate preview` and inspect all modified files.

- [ ] **Step 4: Update `tasks/frontend/FE-009.md`**
Record RED/GREEN commands, evidence checkpoint, reviewer checklist, and mark Status as Completed.
