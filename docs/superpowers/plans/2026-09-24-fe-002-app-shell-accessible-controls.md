# FE-002 Implementation Plan — App shell, familiar navigation and accessible shared controls

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an accessible, low-cognitive-overhead application shell with familiar navigation, semantic landmarks, and reusable accessible controls (Button, Input, StatusMessage, Dialog) for OpenLibraryOS.

**Architecture:**
- Shared UI primitives under `frontend/src/shared/components/` (`Button`, `Input`, `StatusMessage`, `Dialog`) consuming `frontend/src/shared/tokens/`.
- Navigation domain model under `frontend/src/app/navigation/navigationModel.ts` using product language with explicit separation from authorization logic.
- App shell layout under `frontend/src/app/shell/` (`AppShell`, `AppHeader`) adhering to semantic landmark ordering (`banner` -> `navigation` -> `main`), predictable keyboard focus flow, single visual primary action per region, and responsive collapse without hiding primary actions.
- Integration in `frontend/src/app/App.tsx` demonstrating the complete Operate-Mode experience offline without network requests.

**Tech Stack:** React 18, TypeScript 5.7+, Vite 6, Vitest 3, React Testing Library, ESLint 9.

**Spec:** `tasks/frontend/FE-002.md`, `PRODUCT.md`, `DESIGN.md`.

## Global Constraints

- Backend is modular monolith; frontend does not touch the database directly (`docs/architecture.md`).
- No pure black (`#000000`) or pure white (`#ffffff`); text contrast >= 4.5:1 (WCAG AA).
- All status cues must provide non-color cues (icon identifier and textual description).
- Spacing follows semantic progression: Label-to-Input 12px, Group-to-Group 24px, Form-to-Submit 32px+.
- Button whitespace ratio 2:1 ($Padding_X = 2 \times Padding_Y$), Title Case labels.
- Visible high-contrast keyboard focus indicators (`:focus-visible` / `tokens.focus.cssString`).
- Red-green-refactor: failing test must be recorded before code implementation.
- Full output enforcement: no placeholders, no omissions, complete runnable code.
- One screen region does not contain competing primary buttons.
- No authorization decision is inferred from navigation visibility.

---

### Task 1: Red Phase — Author failing shell and shared controls test suite

**Files:**
- Create: `frontend/tests/app/shell.test.tsx`

**Interfaces:**
- Consumes: `frontend/src/app/App.tsx`, `frontend/src/app/shell/AppShell.tsx`, `frontend/src/shared/components/index.ts`
- Produces: Comprehensive failing test suite checking landmark order, logo home link, keyboard navigation, dialog Escape dismissal, focus return, and accessible shared controls.

- [ ] **Step 1: Write failing shell test**
  Author `frontend/tests/app/shell.test.tsx` covering:
  - Semantic landmark order: `<header role="banner">` -> `<nav aria-label="Primary navigation">` -> `<main role="main">`.
  - Logo-to-home navigation link.
  - Primary navigation links using product language (Catalog, Circulation, Inventory, Members, Reservations) with `aria-current="page"` for active route.
  - Account area displaying user context ("Librarian Desk") without technical IDs.
  - Keyboard traversal: Tab progression from skip link to logo, to navigation, to main content and primary action.
  - Dialog modal accessibility: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-describedby`.
  - Dialog Escape key dismissal and return of focus to the trigger button.
  - Dialog Close button dismissal and return of focus to the trigger button.
  - Shared Button: 2:1 whitespace padding ratio, focus ring, title case, disabled state.
  - Shared Input: accessible label-for-id binding, programmatic `aria-describedby` for description and error message, `aria-invalid="true"` when error exists, `(Optional)` tag for optional inputs.
  - Shared StatusMessage: non-color cues with icon + label + message, `role="status"` or `role="alert"`.
  - Single visually primary action per screen region.
  - Responsive behavior: mobile menu toggle allows access to navigation on narrow screens.
  - Zero network fetch calls.

- [ ] **Step 2: Run test to record failure (Red phase)**
  Run: `cd frontend; npm run test -- --run tests/app/shell.test.tsx`
  Expected: FAIL because shell, navigation and shared controls are not yet created.

---

### Task 2: Green Phase — Implement Accessible Shared Controls

**Files:**
- Create: `frontend/src/shared/components/Button.tsx`
- Create: `frontend/src/shared/components/Input.tsx`
- Create: `frontend/src/shared/components/StatusMessage.tsx`
- Create: `frontend/src/shared/components/Dialog.tsx`
- Create: `frontend/src/shared/components/index.ts`

**Interfaces:**
- Produces:
  - `Button` component with variants (`primary`, `secondary`, `outline`, `ghost`, `danger`) and sizes (`sm`, `md`, `lg`)
  - `Input` component with label, description, error validation, and optional indicator
  - `StatusMessage` component with non-color cues (`success`, `warning`, `danger`, `info`)
  - `Dialog` component with accessible modal semantics, backdrop, Esc key listener, and focus restoration

- [ ] **Step 1: Implement Button.tsx**
  Implement accessible button with token-based 2:1 padding, focus ring, and variant colors.
- [ ] **Step 2: Implement Input.tsx**
  Implement accessible labeled input with vertical single-column layout, 12px label-to-input gap, `aria-describedby`, `aria-invalid`, and error messages.
- [ ] **Step 3: Implement StatusMessage.tsx**
  Implement accessible status container with icon, textual status label, and message content.
- [ ] **Step 4: Implement Dialog.tsx**
  Implement modal dialog with focus trapping / focus restoration to trigger on close, Esc key handling, and accessible ARIA attributes.
- [ ] **Step 5: Implement shared/components/index.ts**
  Export all shared controls.

---

### Task 3: Green Phase — Implement Navigation Model and App Shell

**Files:**
- Create: `frontend/src/app/navigation/navigationModel.ts`
- Create: `frontend/src/app/shell/AppHeader.tsx`
- Create: `frontend/src/app/shell/AppShell.tsx`
- Create: `frontend/src/app/shell/index.ts`

**Interfaces:**
- Produces:
  - `navigationItems` definition using product language
  - `AppHeader` component with logo, primary navigation, responsive toggle, and account area
  - `AppShell` layout component with skip link, header, main landmark, and page heading region

- [ ] **Step 1: Implement navigationModel.ts**
  Define navigation items with product language and document the invariant that navigation visibility is never an authorization boundary.
- [ ] **Step 2: Implement AppHeader.tsx**
  Build accessible banner landmark with logo-to-home, nav links, account area, and responsive mobile toggle.
- [ ] **Step 3: Implement AppShell.tsx**
  Build shell layout coordinating skip link, header, and main landmark with page heading.
- [ ] **Step 4: Implement shell/index.ts**
  Export shell components.

---

### Task 4: Green Phase — Integrate Shell and Shared Controls into App.tsx

**Files:**
- Modify: `frontend/src/app/App.tsx`

**Interfaces:**
- Consumes: `AppShell`, `Button`, `Input`, `StatusMessage`, `Dialog`, `TokenProvider`
- Produces: Updated root application showcasing full app shell, navigation, single primary action, and interactive accessible dialog.

- [ ] **Step 1: Update App.tsx**
  Replace standalone placeholder surface with `AppShell`, navigation active state, operating form with labeled inputs, status message, and dialog with focus restoration.

---

### Task 5: Verification & Quality Gates

**Files:**
- Modify: `tasks/frontend/FE-002.md`

- [ ] **Step 1: Run focused shell test suite**
  Run: `cd frontend; npm run test -- --run tests/app/shell.test.tsx`
  Verify: All shell tests pass.
- [ ] **Step 2: Run all frontend tests**
  Run: `cd frontend; npm run test`
  Verify: Both `bootstrap.test.tsx` and `shell.test.tsx` pass.
- [ ] **Step 3: Run typecheck, lint, and build**
  Run: `cd frontend; npm run typecheck`
  Run: `cd frontend; npm run lint`
  Run: `cd frontend; npm run build`
- [ ] **Step 4: Run system regression checks**
  Run backend test suite:
  `python -m pytest backend/tests/ -q`
  `python -m pytest backend/tests/integration/release/test_release_gate.py -k test_frontend_accessibility_and_release_contract_verification`
- [ ] **Step 5: Run delegated Open Code Review**
  Review all touched files for edge cases, a11y, strict typing, and style invariants.
- [ ] **Step 6: Update FE-002.md with completion evidence**
  Record command output and mark task Completed.
