# FE-001 Implementation Plan — Frontend bootstrap, product UI context, tokens and test tooling

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the React/TypeScript workspace, durable product UI context in `PRODUCT.md`, foundational accessible design tokens, root application bootstrap, and deterministic frontend test/type/lint/build tooling.

**Architecture:**
- Frontend monorepo package under `frontend/` powered by Vite, React 18, TypeScript (strict mode), Vitest, React Testing Library, and ESLint 9.
- Durable product UI context in root `PRODUCT.md` derived strictly from `DESIGN.md`, defining audience personas, Operate-mode operating constraints, minimum-comprehension UI invariants, and V1 boundaries.
- Foundational design token system under `frontend/src/shared/tokens/` providing semantic spacing scale, contrast-compliant colors (no pure black/white), non-color status cues, visible focus indicator, typography, nested border-radius calculation, and a React `TokenProvider` that injects CSS custom properties.
- Offline-first bootstrap: root `<App />` mounts cleanly with zero network dependencies.

**Tech Stack:** React 18, TypeScript 5.7+, Vite 6, Vitest 3, React Testing Library, ESLint 9, Node.js 24+.

**Spec:** `tasks/frontend/FE-001.md`, `DESIGN.md`, `docs/architecture.md`.

## Global Constraints

- Backend is modular monolith; frontend does not touch the database directly (`docs/architecture.md`).
- Target frontend directory structure adheres to `docs/architecture.md` (`src/app/`, `src/features/`, `src/shared/`, `tests/`).
- No pure black (`#000000`) or pure white (`#ffffff`); text contrast >= 4.5:1 (WCAG AA).
- All status cues must provide non-color cues (icon and textual description).
- Spacing follows semantic progression: Label-to-Input 12px, Group-to-Group 24px, Form-to-Submit 32px+.
- Button white-space ratio 2:1 ($Padding_X = 2 \times Padding_Y$), Title Case labels.
- Visible high-contrast keyboard focus indicators (`:focus-visible`).
- Red-green-refactor: failing test must be recorded before code implementation.
- Full output enforcement: no placeholders, no omissions, complete runnable code.

---

### Task 1: Record Operate-mode product UI brief in PRODUCT.md

**Files:**
- Create: `PRODUCT.md`

**Interfaces:**
- Consumes: `DESIGN.md`, `docs/architecture.md`
- Produces: `PRODUCT.md` containing audience personas, editions, Operate-mode definition, minimum-comprehension UI rule, and strict V1 boundaries.

- [x] **Step 1: Write PRODUCT.md**
  Derive solely from `DESIGN.md` without inventing features:
  - Users: Platform administrator, Organization administrator, Librarian, Student/teacher (Education), Member (Public Library), Contributor/operator.
  - Editions: Core Platform, Education Edition, Public Library Edition.
  - Operate-Mode: Low-tech, high-efficiency, calm, predictable environment for repetitive desk circulation, cataloging, inventory.
  - Minimum-comprehension UI rule: Zero-training clarity, Jakob's convention-first, 1 primary action per region, semantic Gestalt spacing, 7±2 chunking, Von Restorff focal isolation, non-color status cues, no pure black/white.
  - V1 boundaries: No microservices, no mobile app, no recommendation engine, no full accounting, no managed SaaS control plane.

- [x] **Step 2: Verify PRODUCT.md against acceptance criteria**
  Check that it matches `DESIGN.md` verbatim on personas and scope boundaries.

---

### Task 2: Red Phase — Author failing bootstrap test and record missing workspace failure

**Files:**
- Create: `frontend/tests/app/bootstrap.test.tsx`

**Interfaces:**
- Consumes: `frontend/src/app/App.tsx`, `frontend/src/shared/tokens/index.ts`
- Produces: Failing test suite capturing missing workspace/modules.

- [x] **Step 1: Write failing bootstrap test**
  Write `frontend/tests/app/bootstrap.test.tsx` verifying:
  - App renders without throwing and without making any network fetch requests.
  - TokenProvider provides spacing tokens with semantic properties (`labelToInput: '12px'`, `groupToGroup: '24px'`, `formToSubmit: '32px'`).
  - Color tokens avoid pure `#000000` and pure `#ffffff`, meet contrast standards.
  - Status cues provide non-color cues (`icon`, `label`).
  - Keyboard focus token provides visible outline style.
  - Nested border radius formula $R_{inner} = \max(0, R_{outer} - Padding)$ works as expected.
  - Button padding maintains 2:1 ratio ($px = 2 \times py$).

- [x] **Step 2: Execute command to record failure (Red phase)**
  Run: `cd frontend; npm run test -- --run tests/app/bootstrap.test.tsx`
  Verify: Command fails due to missing package.json / missing workspace scripts.
  Record the exact command failure in task notes.

---

### Task 3: Green Phase — Initialize React/TypeScript workspace and dependencies

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/eslint.config.js`
- Create: `frontend/index.html`
- Create: `frontend/tests/setup.ts`

**Interfaces:**
- Produces: Runnable npm scripts: `npm run test`, `npm run typecheck`, `npm run lint`, `npm run build`, `npm run dev`.

- [x] **Step 1: Create package.json and configuration files**
  Configure dependencies: React 18, React DOM 18, TypeScript 5.7+, Vite 6, Vitest 3, Testing Library, ESLint 9.
  Define strict npm scripts: `test`, `typecheck`, `lint`, `build`.

- [x] **Step 2: Run npm install**
  Execute: `cd frontend; npm install`
  Verify clean lockfile and exit code 0.

---

### Task 4: Green Phase — Implement Design Tokens and TokenProvider

**Files:**
- Create: `frontend/src/shared/tokens/types.ts`
- Create: `frontend/src/shared/tokens/tokens.ts`
- Create: `frontend/src/shared/tokens/TokenContext.tsx`
- Create: `frontend/src/shared/tokens/index.ts`

**Interfaces:**
- Produces:
  - `ThemeTokens` interface
  - `tokens` object (spacing, colors, typography, focus, radius, buttonSpacing)
  - `calcNestedRadius(outerRadiusPx: number, paddingPx: number): number`
  - `TokenProvider` component
  - `useTokens(): ThemeTokens` hook

- [x] **Step 1: Write token types and constants**
  Implement `frontend/src/shared/tokens/types.ts` and `frontend/src/shared/tokens/tokens.ts`.
  Ensure zero business rules, zero API endpoint strings, pure styling tokens.

- [x] **Step 2: Write TokenContext and TokenProvider**
  Implement `frontend/src/shared/tokens/TokenContext.tsx` with CSS variable injection into container.

- [x] **Step 3: Export token public API**
  Export all types and members in `frontend/src/shared/tokens/index.ts`.

---

### Task 5: Green Phase — Implement Root Application Bootstrap

**Files:**
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/main.tsx`
- Modify: `frontend/README.md`

**Interfaces:**
- Produces: `<App />` root component displaying Operate-mode status and token integration without network calls.

- [x] **Step 1: Implement App.tsx and main.tsx**
  Implement `<App />` with accessible landmarks (`<main>`, `<header>`, `<h1>`), using `useTokens()` and `<TokenProvider>`.

- [x] **Step 2: Update frontend/README.md**
  Document the workspace, structure, and deterministic test/typecheck/lint/build commands.

---

### Task 6: Verification & Quality Gates

**Files:**
- Modify: `tasks/frontend/FE-001.md`

- [x] **Step 1: Run focused bootstrap test**
  Run: `cd frontend; npm run test -- --run tests/app/bootstrap.test.tsx`
  Verify: All tests pass.

- [x] **Step 2: Run full typecheck, lint, and build**
  Run: `cd frontend; npm run typecheck`
  Run: `cd frontend; npm run lint`
  Run: `cd frontend; npm run build`
  Verify: Zero errors, exit code 0.

- [x] **Step 3: Run backend test suite to verify no regressions**
  Run: `python -m pytest backend/tests/ -q`

- [x] **Step 4: Run delegated Open Code Review**
  Review all touched files for accessibility, memory leaks, strict typing, and style compliance.

- [x] **Step 5: Record evidence and update FE-001.md**
  Update `tasks/frontend/FE-001.md` status to Completed with evidence log.
