# FE-005 Implementation Plan — Catalog search and book browsing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable users to find and inspect bibliographic books through a simple, accessible, typed catalog experience with cursor continuation, robust error handling, and clear distinction from physical copy inventory.

**Architecture:**
- Extend the typed API client in `frontend/src/shared/api/` (`types.ts`, `apiClient.ts`, `index.ts`) with contract-compliant `Book`, `BookPage`, `CatalogSearchParams`, and `apiClient.books.list(...)` / `apiClient.books.getById(...)`.
- Implement feature components in `frontend/src/features/catalog/`:
  - `types.ts`: Catalog search parameters, state types, view state.
  - `BookDetail.tsx`: Accessible bibliographic detail view with copy/edition disclaimer and keyboard escape/close.
  - `CatalogSearch.tsx`: Single-column search form with actionable placeholder, single primary submit action, optional secondary filters, skeleton loading shimmer, empty state with guidance, recoverable RFC 7807 error rendering with retry, keyboard-accessible book cards, and cursor pagination preserving active filters.
  - `index.ts`: Public feature exports.
- Integrate into `frontend/src/app/App.tsx` and AppShell navigation, allowing seamless keyboard-friendly switching between Circulation and Catalog modes.

**Tech Stack:** React 18, TypeScript 5.7+, Vite 6, Vitest 3, React Testing Library, ESLint 9.

**Spec:** `tasks/frontend/FE-005.md`, `contracts/openapi/v1.yaml`, `PRODUCT.md`, `DESIGN.md`.

## Global Constraints

- Backend is modular monolith; frontend does not touch the database directly (`docs/architecture.md`).
- No pure black (`#000000`) or pure white (`#ffffff`); text contrast >= 4.5:1 (WCAG AA).
- All status cues must provide non-color cues (icon identifier and textual description).
- Spacing follows semantic progression: Label-to-Input 12px, Group-to-Group 24px, Form-to-Submit 32px+.
- Button whitespace ratio 2:1 ($Padding_X = 2 \times Padding_Y$), Title Case labels.
- Single visually primary action per screen region (Von Restorff Isolation).
- Form inputs follow 1-column layout; Actionable placeholder for search.
- Skeleton loading shimmer instead of raw spinner.
- Recoverable errors render Problem Details with retry action.
- Distinguish bibliographic records from physical copies in user language ("Bibliographic Record" vs physical copies/barcodes).
- Cursor continuation must strictly preserve active search filter parameters.
- Red-green-refactor: failing test must be recorded before code implementation.
- Full output enforcement: no placeholders, no omissions, complete runnable code.

---

### Task 1: Red Phase — Author failing catalog search test suite

**Files:**
- Create: `frontend/tests/features/catalog/catalog-search.test.tsx`

**Interfaces:**
- Consumes: `frontend/src/features/catalog`, `frontend/src/app/App.tsx`, `frontend/src/shared/tokens`
- Produces: Failing test suite verifying query submission, empty result state, cursor continuation with preserved filters, API error rendering with retry, bibliographic language distinction, and keyboard navigation.

- [ ] **Step 1: Write failing catalog search test**
  Author `frontend/tests/features/catalog/catalog-search.test.tsx` covering:
  1. Initial render: Jakob's search input convention with actionable placeholder, search button as primary action, bibliographic notice explaining difference from physical copies.
  2. Query submit & result rendering: Submitting search fetches books via typed API client and renders matching bibliographic books with title, authors, ISBN, publication year.
  3. Empty result state: Submitting query with no matches displays `EmptyState` explaining no matching bibliographic books found and offering filter reset.
  4. Cursor continuation: When `next_cursor` is present, pagination control is available. Clicking "Next Page" requests `/books` with the cursor AND preserves the existing filters (`title`, `isbn`).
  5. API error rendering: 400 Bad Request or 500 error renders `ProblemDetailsRenderer` with retry action that successfully re-fetches.
  6. Book detail view: Selecting a book displays detail panel/dialog with full metadata and bibliographic disclaimer, dismissible via keyboard (Escape / Close button).
  7. User language invariant: Clearly identifies items as bibliographic records, never promising physical copy availability beyond API data.
  8. Keyboard accessibility: Form submits on Enter; book results can be activated via keyboard; focus returns gracefully on modal dismiss.

- [ ] **Step 2: Run test to record failure (Red phase)**
  Run: `cd frontend; npm run test -- --run tests/features/catalog/catalog-search.test.tsx`
  Expected: FAIL because catalog components and routes are not yet implemented.

---

### Task 2: Green Phase — Implement Typed API Client Books Domain Module

**Files:**
- Modify: `frontend/src/shared/api/types.ts`
- Modify: `frontend/src/shared/api/apiClient.ts`
- Modify: `frontend/src/shared/api/index.ts`

**Interfaces:**
- Consumes: OpenAPI `/books` and `/books/{book_id}` contracts from `contracts/openapi/v1.yaml`
- Produces: `Book`, `BookPage`, `CatalogSearchParams`, and `apiClient.books.list(...)` / `apiClient.books.getById(...)`.

- [ ] **Step 1: Add types to `frontend/src/shared/api/types.ts`**
  Add `Book`, `BookPage`, `BookWrite`, and `CatalogSearchParams`.

- [ ] **Step 2: Add books domain module to `frontend/src/shared/api/apiClient.ts`**
  Add `books` object with `list(params, options)` (properly building query string for `title`, `isbn`, `limit`, `cursor`) and `getById(bookId, options)`.

- [ ] **Step 3: Export additions from `frontend/src/shared/api/index.ts`**

---

### Task 3: Green Phase — Implement Catalog Feature Components

**Files:**
- Create: `frontend/src/features/catalog/types.ts`
- Create: `frontend/src/features/catalog/BookDetail.tsx`
- Create: `frontend/src/features/catalog/CatalogSearch.tsx`
- Create: `frontend/src/features/catalog/index.ts`

**Interfaces:**
- Consumes: `apiClient`, `ProblemDetailsRenderer`, `EmptyState`, `LoadingSkeleton`, `Button`, `Input`, `Dialog`, tokens
- Produces: Reusable `CatalogSearch` component and `BookDetail` component.

- [ ] **Step 1: Create `frontend/src/features/catalog/types.ts`**
  Define catalog UI filter state, pagination state, and view model.

- [ ] **Step 2: Create `frontend/src/features/catalog/BookDetail.tsx`**
  Implement accessible book detail view with metadata and disclaimer.

- [ ] **Step 3: Create `frontend/src/features/catalog/CatalogSearch.tsx`**
  Implement the search screen with single primary action, 1-col layout, cursor pagination, and all state views.

- [ ] **Step 4: Create `frontend/src/features/catalog/index.ts`**
  Export `CatalogSearch`, `BookDetail`, and catalog types.

---

### Task 4: Green Phase — Integrate Catalog Route in App and Shell Navigation

**Files:**
- Modify: `frontend/src/app/App.tsx`

**Interfaces:**
- Consumes: `CatalogSearch`, `AppShell`, tokens
- Produces: Integrated desk where clicking "Catalog" navigates to the catalog screen and updates document landmarks.

- [ ] **Step 1: Update `frontend/src/app/App.tsx`**
  Support active tab switching between 'circulation' and 'catalog', dynamic page titles, and hash route change handling.

- [ ] **Step 2: Run focused catalog test suite**
  Run: `cd frontend; npm run test -- --run tests/features/catalog/catalog-search.test.tsx`
  Expected: PASS all catalog search tests.

---

### Task 5: Refactor & Verification Phase — Code Quality, Typecheck, Lint, Build & Evidence

**Files:**
- Modify: `tasks/frontend/FE-005.md`

- [ ] **Step 1: Run full test suite, typecheck, lint, build**
  Run: `cd frontend; npm run test; npm run typecheck; npm run lint; npm run build`
  Verify 0 errors and all tests green.

- [ ] **Step 2: Update `tasks/frontend/FE-005.md` with execution evidence**
  Document test output, evidence checkpoints, reviewer checklist, and mark status as Completed.
