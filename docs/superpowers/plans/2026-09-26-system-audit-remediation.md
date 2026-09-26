# Full System Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve 100% of P1, P2, and P3 findings documented in `docs/FULL_SYSTEM_AUDIT_2026-09-26.md`, bringing OpenLibraryOS to a robust, accessible, and release-ready state.

**Architecture:** Maintain modular monolith architecture across Python/Flask backend and React 18/TypeScript frontend. Cleanly separate concerns: backend mypy type safety and trusted proxy rate-limiting; frontend session authentication boundary without false client-side bypass; responsive App Shell and focus-trapped dialog primitives complying with WCAG and cognitive design invariants; tab-level lazy loading for domain workspaces; full frontend CI quality gates and OpenAPI contract drift detection.

**Tech Stack:** Python 3.12, Flask, Celery, mypy, pytest, ruff; React 18, TypeScript 5, Vite, Vitest, Testing Library; Nginx; GitHub Actions.

**Spec:** `docs/FULL_SYSTEM_AUDIT_2026-09-26.md`

## Global Constraints

- Backend must remain modular monolith with strict tenant isolation (`organization_id`).
- All persistent DB queries parameterized, no secrets in source code.
- Python code must pass `mypy src --strict` compliance without untyped decorators or `no-any-return` errors.
- No client-side bypass query strings (`?demo=1`) or fabricated operational status in production builds.
- Design invariants: 1-column forms, WCAG AA contrast (minimum 4.5:1), no pure black (#000000) or pure white (#FFFFFF), nested border radius formula ($R_{inner} = R_{outer} - P$), focus-trapped modals, responsive down to 375px without horizontal scrolling.
- All code changes must adhere to Test-Driven Development (Red-Green-Refactor) and full output enforcement without truncation or placeholders.

---

### Task 1: Fix P1-01 & P2-02 (Backend Mypy Typing & Rate Limiter IP Sanitization)

**Files:**
- Modify: `backend/src/openlibrary/modules/core/infrastructure/rate_limiter.py:100-165`
- Modify: `backend/src/openlibrary/worker.py:115-135`
- Modify: `infra/nginx/default.conf:75-92`
- Test: `backend/tests/unit/core/test_rate_limiter.py`

**Interfaces:**
- Consumes: Flask request headers (`X-Real-IP`, `X-Forwarded-For`, `request.remote_addr`), Celery `celery_app.task`.
- Produces: Type-safe `@rate_limit` returning Flask `Response`, sanitized client IP extraction resilient to header spoofing, type-annotated Celery background tasks passing `mypy src`.

- [ ] **Step 1: Write failing unit test for IP sanitization in rate limiter**

Add test in `backend/tests/unit/core/test_rate_limiter.py`:
```python
def test_rate_limiter_extracts_sanitized_client_ip_from_request() -> None:
    """Verifies that rate_limit decorator extracts X-Real-IP or rightmost forwarded IP, preventing spoofing."""
    from openlibrary.modules.core.infrastructure.rate_limiter import get_client_ip
    from unittest.mock import MagicMock

    # Case 1: X-Real-IP set by trusted edge reverse proxy
    req1 = MagicMock()
    req1.headers = {"X-Real-IP": "203.0.113.195", "X-Forwarded-For": "1.2.3.4, 203.0.113.195"}
    req1.remote_addr = "10.0.0.2"
    assert get_client_ip(req1) == "203.0.113.195"

    # Case 2: Multi-hop X-Forwarded-For without X-Real-IP takes the trusted rightmost client hop
    req2 = MagicMock()
    req2.headers = {"X-Forwarded-For": "198.51.100.1, 203.0.113.50"}
    req2.remote_addr = "10.0.0.2"
    assert get_client_ip(req2) == "203.0.113.50"

    # Case 3: No headers falls back to remote_addr
    req3 = MagicMock()
    req3.headers = {}
    req3.remote_addr = "192.168.1.100"
    assert get_client_ip(req3) == "192.168.1.100"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/core/test_rate_limiter.py::test_rate_limiter_extracts_sanitized_client_ip_from_request -v`
Expected: FAIL with `ImportError: cannot import name 'get_client_ip'`.

- [ ] **Step 3: Implement minimal code in `rate_limiter.py`, `worker.py`, and `default.conf`**

In `backend/src/openlibrary/modules/core/infrastructure/rate_limiter.py`:
Add `get_client_ip(req: Any) -> str`:
```python
def get_client_ip(req: Any) -> str:
    """Extract authoritative client IP, prioritizing X-Real-IP set by trusted reverse proxy."""
    real_ip = req.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    xff = req.headers.get("X-Forwarded-For")
    if xff:
        # Take rightmost IP (closest to trusted edge proxy) to prevent spoofing
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]

    return getattr(req, "remote_addr", None) or "127.0.0.1"
```
Update `wrapper` in `rate_limit`:
```python
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Response:
            limiter = limiter_provider() if limiter_provider else _default_limiter()
            if limiter is None:
                return cast(Response, make_response(fn(*args, **kwargs)))

            client_ip = get_client_ip(request)
            key = f"{key_prefix}:{client_ip}"
            ...
            result = fn(*args, **kwargs)
            response: Response = cast(Response, make_response(result))
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response
```
In `backend/src/openlibrary/worker.py`:
Properly type Celery task functions using typed task decorator:
```python
    task_decorator = cast(Any, celery_app.task)

    @task_decorator(name="openlibrary.dispatch_outbox")
    def dispatch_outbox(max_events: int = 50) -> int:
        ...

    @task_decorator(name="openlibrary.run_scheduled_circulation")
    def run_scheduled_circulation() -> dict[str, Any]:
        ...
```
In `infra/nginx/default.conf`:
Replace `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` with `proxy_set_header X-Forwarded-For $remote_addr;` at lines 76 and 90 to ensure edge proxy sanitizes incoming forwarded headers.

- [ ] **Step 4: Run backend tests and mypy to verify they pass**

Run:
```bash
python -m pytest backend/tests/unit/core/test_rate_limiter.py -v
python -m mypy src (inside backend directory)
```
Expected: All tests PASS and `Success: no issues found in 85 source files`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/openlibrary/modules/core/infrastructure/rate_limiter.py backend/src/openlibrary/worker.py infra/nginx/default.conf backend/tests/unit/core/test_rate_limiter.py
git commit -m "fix(backend): resolve mypy typing errors and sanitize rate-limiter client IP"
```

---

### Task 2: Fix P1-03 (Eliminate Client-Side Demo Query Bypass & Fabricated Operational Status)

**Files:**
- Modify: `frontend/src/main.tsx:1-16`
- Modify: `frontend/src/app/App.tsx:114-135`
- Modify: `frontend/src/features/circulation/CirculationDesk.tsx:88-98`
- Test: `frontend/tests/app/bootstrap.test.tsx`
- Test: `frontend/tests/features/circulation/circulation-desk.test.tsx`

**Interfaces:**
- Consumes: `AppProps`, `CirculationDeskProps`.
- Produces: Production frontend bootstrap without query parameter authentication bypass; honest operational status cues based on real diagnostic data.

- [ ] **Step 1: Write failing test verifying `?demo=1` does not authenticate user**

In `frontend/tests/app/bootstrap.test.tsx`, add test:
```typescript
it('does not grant authenticated operate session when ?demo=1 query string is in URL', () => {
  // Mock window.location.search with ?demo=1
  const originalLocation = window.location;
  delete (window as unknown as { location?: unknown }).location;
  window.location = { ...originalLocation, search: '?demo=1', hash: '' } as Location;

  render(<App autoRefreshOnMount={false} />);

  // Must show login form, NOT circulation desk
  expect(screen.getByRole('heading', { level: 2, name: /sign in to openlibraryos/i })).toBeInTheDocument();
  expect(screen.queryByTestId('circulation-desk')).not.toBeInTheDocument();

  window.location = originalLocation;
});
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `npm test -- tests/app/bootstrap.test.tsx`

- [ ] **Step 3: Implement minimal code changes**

In `frontend/src/main.tsx`:
Remove `const isDemo = ...` query parameter check.
Render `<App />` directly:
```typescript
import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './app/App';

const rootElement = document.getElementById('root');

if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
```
In `frontend/src/app/App.tsx`:
Only use `initialAuthenticated` when explicitly supplied via props (for test harness dependency injection):
```typescript
export function App({
  initialAuthenticated = false,
  autoRefreshOnMount,
}: AppProps = {}) {
  const shouldAutoRefresh = autoRefreshOnMount ?? !initialAuthenticated;
  const initialToken = initialAuthenticated ? 'in-memory-operate-session' : null;
  ...
```
In `frontend/src/features/circulation/CirculationDesk.tsx`:
Remove fake operational status banner (`Operational Status: Ready`) when there is no lookup error:
```tsx
      {/* Header and Operational Diagnostic Notice */}
      {lookupError && (
        <StatusMessage status="warning" title="Operational Status: Attention Required">
          A circulation lookup or operational request encountered an issue. Review the diagnostic details below.
        </StatusMessage>
      )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
npm test -- tests/app/bootstrap.test.tsx tests/features/circulation/circulation-desk.test.tsx
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/app/App.tsx frontend/src/features/circulation/CirculationDesk.tsx frontend/tests/app/bootstrap.test.tsx frontend/tests/features/circulation/circulation-desk.test.tsx
git commit -m "fix(frontend): remove demo query bypass and unevidenced operational status badge"
```

---

### Task 3: Fix P1-05 (Accessible Dialog Primitive with Focus Trap & Custom Modal Migration)

**Files:**
- Modify: `frontend/src/shared/components/Dialog.tsx`
- Modify: `frontend/src/features/catalog/CreateBookModal.tsx`
- Modify: `frontend/src/features/inbox/CreateReservationModal.tsx`
- Modify: `frontend/src/features/auth/ChangePasswordModal.tsx`
- Modify: `frontend/src/features/auth/UserProfileModal.tsx`
- Test: `frontend/tests/shared/dialog-focus-trap.test.tsx`
- Test: `frontend/tests/features/catalog/create-book.test.tsx`
- Test: `frontend/tests/features/inbox/create-reservation.test.tsx`
- Test: `frontend/tests/features/auth/change-password.test.tsx`
- Test: `frontend/tests/features/auth/user-profile.test.tsx`

**Interfaces:**
- Consumes: `DialogProps` (isOpen, onClose, title, description, children, triggerRef, maxWidth).
- Produces: Fully accessible modal with Tab and Shift+Tab focus trap, focus restoration on close, Escape key listener, backdrop dismissal, unified across all app modals.

- [ ] **Step 1: Write failing test for Dialog focus trap**

Create `frontend/tests/shared/dialog-focus-trap.test.tsx`:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React, { useRef } from 'react';
import { Dialog } from '../../src/shared/components/Dialog';
import { TokenProvider } from '../../src/shared/tokens';

describe('Dialog Focus Trap Primitive (P1-05)', () => {
  it('traps Tab navigation within the dialog focusable elements', () => {
    function TestComponent() {
      return (
        <TokenProvider>
          <button data-testid="outside-button">Outside</button>
          <Dialog isOpen={true} onClose={vi.fn()} title="Test Modal">
            <input data-testid="input-1" placeholder="First field" />
            <input data-testid="input-2" placeholder="Second field" />
            <button data-testid="submit-button">Submit</button>
          </Dialog>
        </TokenProvider>
      );
    }

    render(<TestComponent />);

    const input1 = screen.getByTestId('input-1');
    const input2 = screen.getByTestId('input-2');
    const submitBtn = screen.getByTestId('submit-button');
    const closeBtn = screen.getByRole('button', { name: /close dialog|đóng/i });

    // Focus starts inside dialog
    expect(document.activeElement).toBe(input1);

    // Tab from input1 -> input2
    fireEvent.keyDown(input1, { key: 'Tab' });
    input2.focus();

    // Tab from submitBtn -> closeBtn
    fireEvent.keyDown(submitBtn, { key: 'Tab' });
    closeBtn.focus();

    // Tab from closeBtn wraps around to input1
    fireEvent.keyDown(closeBtn, { key: 'Tab' });
    expect(document.activeElement).toBe(input1);

    // Shift+Tab from input1 wraps around to closeBtn
    fireEvent.keyDown(input1, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(closeBtn);
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm test -- tests/shared/dialog-focus-trap.test.tsx`
Expected: FAIL because `Dialog` does not intercept Tab/Shift+Tab wrapping.

- [ ] **Step 3: Implement focus trap in `Dialog.tsx` and refactor custom modals**

Update `frontend/src/shared/components/Dialog.tsx`:
- Add keydown handler for `Tab` / `Shift+Tab`:
```typescript
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' || event.code === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key === 'Tab' || event.code === 'Tab') {
        if (!dialogRef.current) return;
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) {
          event.preventDefault();
          return;
        }

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (event.shiftKey) {
          if (document.activeElement === firstElement || document.activeElement === dialogRef.current) {
            event.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            event.preventDefault();
            firstElement.focus();
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);
```
- Migrate `CreateBookModal.tsx`, `CreateReservationModal.tsx`, `ChangePasswordModal.tsx`, and `UserProfileModal.tsx` to wrap their contents in `<Dialog ...>` rather than custom `role="presentation"` and `role="dialog"` divs.

- [ ] **Step 4: Run all modal test suites to verify they pass**

Run:
```bash
npm test -- tests/shared/dialog-focus-trap.test.tsx tests/features/catalog/create-book.test.tsx tests/features/inbox/create-reservation.test.tsx tests/features/auth/change-password.test.tsx tests/features/auth/user-profile.test.tsx
```
Expected: All 5 test suites PASS with 0 failures.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/components/Dialog.tsx frontend/src/features/catalog/CreateBookModal.tsx frontend/src/features/inbox/CreateReservationModal.tsx frontend/src/features/auth/ChangePasswordModal.tsx frontend/src/features/auth/UserProfileModal.tsx frontend/tests/shared/dialog-focus-trap.test.tsx
git commit -m "fix(a11y): implement Dialog focus trap and unify all modals to accessible primitive"
```

---

### Task 4: Fix P1-04 & P2-06 (Responsive App Shell, Navigation Architecture & Drawer Account Integration)

**Files:**
- Modify: `frontend/src/app/navigation/navigationModel.ts`
- Modify: `frontend/src/app/shell/AppHeader.tsx`
- Modify: `frontend/src/app/shell/AppShell.tsx`
- Test: `frontend/tests/app/shell.test.tsx`
- Test: `frontend/tests/app/responsive-shell.test.tsx`

**Interfaces:**
- Consumes: `NavigationItem`, `AppShellProps`, `AppHeaderProps`.
- Produces: Fully responsive navigation header without horizontal scrollbar at desktop, compact mobile header (375px) with brand + menu button, and operator desk/profile/logout moved into the mobile drawer.

- [ ] **Step 1: Write failing responsive tests for 375px mobile and 1440px desktop**

Create `frontend/tests/app/responsive-shell.test.tsx`:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { AppHeader } from '../../src/app/shell/AppHeader';
import { TokenProvider } from '../../src/shared/tokens';

describe('AppHeader Responsive Layout & Information Architecture (P1-04, P2-06)', () => {
  it('renders clean desktop navigation without overflow-x auto styling', () => {
    render(
      <TokenProvider>
        <AppHeader activeNavigationId="circulation" />
      </TokenProvider>
    );

    const desktopNav = screen.getByRole('navigation', { name: /primary navigation/i });
    expect(desktopNav).toBeInTheDocument();
    // Must NOT have horizontal scroll styling
    expect(desktopNav.style.overflowX).not.toBe('auto');
  });

  it('renders mobile menu button and drawer containing both navigation and account actions', () => {
    render(
      <TokenProvider>
        <AppHeader activeNavigationId="circulation" operatorDeskName="Librarian Desk" />
      </TokenProvider>
    );

    const toggleBtn = screen.getByRole('button', { name: /toggle navigation menu/i });
    expect(toggleBtn).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- tests/app/responsive-shell.test.tsx`
Expected: FAIL because `desktopNav.style.overflowX` is `'auto'`.

- [ ] **Step 3: Implement responsive header and navigation refinement**

In `frontend/src/app/navigation/navigationModel.ts`:
Refine labels to be Vietnamese-first, concise, and clean:
- "Lưu thông" (Circulation)
- "Mục lục" (Catalog)
- "Kho sách" (Inventory)
- "Đặt trước" (Reservations)
- "Học đường" (Education & Borrowers)
- "Thư viện & Thẻ" (Public Library & Finance)
In `frontend/src/app/shell/AppHeader.tsx`:
- Desktop Nav:
  - Display `item.labelVi` concisely without redundant long subtitles.
  - Remove `overflowX: 'auto'` from `<nav>`.
  - Group into Core and Editions if desired, with clear focus and hover styling.
- Header Account Region on Mobile (`@media (max-width: 1024px)`):
  - Add CSS class `openlibrary-desktop-account` to hide the top-bar account region on mobile.
  - In `isMobileMenuOpen` slide-out drawer:
    - Display Drawer Header with Close button.
    - Display Navigation Items list.
    - Display Operator Desk Profile Section with operator desk name, profile button, change password button, and logout button.
    - Implement focus trap inside mobile drawer.
- Ensure document and header `scrollWidth <= viewport` at 375px.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- tests/app/responsive-shell.test.tsx tests/app/shell.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/navigation/navigationModel.ts frontend/src/app/shell/AppHeader.tsx frontend/src/app/shell/AppShell.tsx frontend/tests/app/responsive-shell.test.tsx frontend/tests/app/shell.test.tsx
git commit -m "fix(shell): make navigation header responsive and integrate account actions into mobile drawer"
```

---

### Task 5: Fix P2-01 (Differentiate Silent Refresh from Login Credential Failure)

**Files:**
- Modify: `frontend/src/features/auth/authApi.ts:40-60`
- Modify: `frontend/src/features/auth/SessionProvider.tsx:45-70`
- Modify: `frontend/src/features/auth/LoginForm.tsx:100-112`
- Test: `frontend/tests/features/auth/auth-flow.test.tsx`

**Interfaces:**
- Consumes: `apiClient.auth.refreshAccessToken()`, `SessionContext`.
- Produces: Clean initial anonymous state on app start without false credential error banner.

- [ ] **Step 1: Write failing test verifying anonymous initial visit does not render error alert**

In `frontend/tests/features/auth/auth-flow.test.tsx`:
```typescript
it('does not display credential error when silent refresh fails on initial mount', async () => {
  // Simulate 401 unauthorized / missing cookie on refresh
  vi.mocked(globalThis.fetch).mockRejectedValueOnce(new Error('Unauthorized'));

  render(
    <TokenProvider>
      <SessionProvider autoRefreshOnMount={true}>
        <ProtectedRoute fallback={<LoginForm />}>
          <div>Protected Content</div>
        </ProtectedRoute>
      </SessionProvider>
    </TokenProvider>
  );

  // Wait for initial silent refresh attempt to settle
  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 2, name: /sign in to openlibraryos/i })).toBeInTheDocument();
  });

  // Must NOT display "Authentication failed" alert!
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.queryByText(/authentication failed/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- tests/features/auth/auth-flow.test.tsx`
Expected: FAIL because `SessionProvider` catches the error and sets `error` to `AUTH_SAFE_ERROR_MESSAGE`.

- [ ] **Step 3: Implement clean silent refresh handling**

In `frontend/src/features/auth/SessionProvider.tsx`:
```typescript
  const refresh = useCallback(async (): Promise<boolean> => {
    setIsLoading(true);
    try {
      const response = await authApi.refreshToken();
      setAccessToken(response.access_token);
      setError(null);
      return true;
    } catch {
      setAccessToken(null);
      // Silent refresh failure is normal for anonymous visitors - do NOT set login credential error!
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);
```
In `frontend/src/features/auth/authApi.ts`:
Keep `refreshToken` error propagation clear:
```typescript
export async function refreshToken(): Promise<AccessTokenResponse> {
  const data = await apiClient.auth.refreshAccessToken();
  return data;
}
```

- [ ] **Step 4: Run auth flow tests to verify they pass**

Run: `npm test -- tests/features/auth/auth-flow.test.tsx`
Expected: All tests in suite PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/auth/SessionProvider.tsx frontend/src/features/auth/authApi.ts frontend/tests/features/auth/auth-flow.test.tsx
git commit -m "fix(auth): separate silent refresh from credential login errors"
```

---

### Task 6: Fix P2-03 (Lazy-load Workspace Data Per Tab)

**Files:**
- Modify: `frontend/src/features/public-library/PublicLibraryWorkspace.tsx:100-145`
- Modify: `frontend/src/features/education/EducationWorkspace.tsx:65-115`
- Test: `frontend/tests/features/public-library/public-library-workspace.test.tsx`
- Test: `frontend/tests/features/education/education-workspace.test.tsx`

**Interfaces:**
- Consumes: `apiClient.publicLibrary.*`, `apiClient.education.*`.
- Produces: Segmented tab-based fetching preventing eager monolithic Promise.all failures.

- [ ] **Step 1: Write test verifying only active tab resources are requested on mount**

In `frontend/tests/features/public-library/public-library-workspace.test.tsx`:
```typescript
it('only fetches memberships resources (members, plans, subscriptions) on initial mount, not fines/invoices/payments', async () => {
  const membersSpy = vi.spyOn(apiClient.publicLibrary.members, 'list').mockResolvedValue({ items: [], total: 0 });
  const plansSpy = vi.spyOn(apiClient.publicLibrary.plans, 'list').mockResolvedValue({ items: [] });
  const subsSpy = vi.spyOn(apiClient.publicLibrary.subscriptions, 'list').mockResolvedValue({ items: [], total: 0 });
  const finesSpy = vi.spyOn(apiClient.publicLibrary.fines, 'list').mockResolvedValue({ items: [], total: 0 });
  const invoicesSpy = vi.spyOn(apiClient.publicLibrary.invoices, 'list').mockResolvedValue({ items: [], total: 0 });
  const paymentsSpy = vi.spyOn(apiClient.publicLibrary.payments, 'list').mockResolvedValue({ items: [], total: 0 });

  render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-token">
        <PublicLibraryWorkspace />
      </SessionProvider>
    </TokenProvider>
  );

  await waitFor(() => {
    expect(membersSpy).toHaveBeenCalled();
    expect(plansSpy).toHaveBeenCalled();
    expect(subsSpy).toHaveBeenCalled();
  });

  // Inactive tab resources must NOT have been called on mount
  expect(finesSpy).not.toHaveBeenCalled();
  expect(invoicesSpy).not.toHaveBeenCalled();
  expect(paymentsSpy).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- tests/features/public-library/public-library-workspace.test.tsx`
Expected: FAIL because `finesSpy`, `invoicesSpy`, and `paymentsSpy` were called on mount.

- [ ] **Step 3: Implement tab-specific lazy loading**

In `frontend/src/features/public-library/PublicLibraryWorkspace.tsx`:
- Group state by tab:
  - When `activeTab === 'memberships'`, load members, plans, subscriptions if not loaded.
  - When `activeTab === 'fines'`, load fines if not loaded.
  - When `activeTab === 'invoices'`, load invoices if not loaded.
  - When `activeTab === 'payments'`, load payments if not loaded.
- Cache fetched tab data in state.
In `frontend/src/features/education/EducationWorkspace.tsx`:
- Group loading by active tab (`people`, `academic`, `policy`):
  - When `activeTab === 'people'`, load departments, students, teachers.
  - When `activeTab === 'academic'`, load semesters, classes.
  - When `activeTab === 'policy'`, load policies.

- [ ] **Step 4: Run workspace tests to verify they pass**

Run:
```bash
npm test -- tests/features/public-library/public-library-workspace.test.tsx tests/features/education/education-workspace.test.tsx
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/public-library/PublicLibraryWorkspace.tsx frontend/src/features/education/EducationWorkspace.tsx frontend/tests/features/public-library/public-library-workspace.test.tsx frontend/tests/features/education/education-workspace.test.tsx
git commit -m "perf(workspaces): lazy-load domain data per tab to isolate failures and reduce API latency"
```

---

### Task 7: Fix P2-04 & P1-02 (Frontend CI Quality Gate & OpenAPI Contract Parity Gate)

**Files:**
- Create: `frontend/tests/shared/openapi-contract-parity.test.ts`
- Modify: `.github/workflows/backend-quality.yml`
- Modify: `.github/workflows/README.md`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: `contracts/openapi/v1.yaml`, `frontend/src/shared/api/types.ts`, `frontend/src/shared/api/client.ts`.
- Produces: Automated contract verification test preventing frontend/OpenAPI drift; complete GitHub Actions CI job executing `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.

- [ ] **Step 1: Write OpenAPI contract parity test in frontend**

Create `frontend/tests/shared/openapi-contract-parity.test.ts`:
- Read `contracts/openapi/v1.yaml` (using `fs.readFileSync`).
- Parse paths in YAML.
- Check that all primary endpoints registered in `apiClient` (`auth`, `books`, `inventory`, `circulation`, `reservations`, `education`, `publicLibrary`, `health`) map to valid OpenAPI specification paths.

- [ ] **Step 2: Run test to verify it executes cleanly**

Run: `npm test -- tests/shared/openapi-contract-parity.test.ts`
Expected: PASS.

- [ ] **Step 3: Update `.github/workflows/backend-quality.yml` with frontend quality gate**

Add `frontend-quality` job to `.github/workflows/backend-quality.yml`:
```yaml
  frontend-quality:
    name: Frontend lint, typecheck, tests and build
    runs-on: ubuntu-24.04
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test -- --reporter=dot
      - run: npm run build
```
Update `.github/workflows/README.md` documenting the frontend quality gate.

- [ ] **Step 4: Run local frontend validation suite**

Run in `frontend/`:
```bash
npm run lint
npm run typecheck
npm test -- --reporter=dot
npm run build
```
Expected: All commands exit with code 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/shared/openapi-contract-parity.test.ts .github/workflows/backend-quality.yml .github/workflows/README.md
git commit -m "ci: add frontend quality gate job and openapi client contract parity test"
```

---

### Task 8: Fix P3-01, P3-02, P3-03 (Act Warnings, Visual Accent Borders & Whitespace Hygiene)

**Files:**
- Modify: `frontend/tests/features/auth/user-profile.test.tsx`
- Modify: `frontend/src/features/catalog/BookDetail.tsx:55-65`
- Modify: `frontend/src/features/inventory/StatusHistoryView.tsx:243-250`
- Clean whitespace in: `.github/ci/compose.env`, `.gitignore`, `PRODUCT.md`, `docs/superpowers/plans/2026-09-23-be-028-production-release.md`, `frontend/src/features/auth/authApi.ts`, `tasks/backend/BE-023.md`, `tasks/backend/BE-025.md`, `tasks/frontend/FE-007.md`.

**Interfaces:**
- Produces: Warning-free Vitest suite, harmonious token-based card borders, clean `git diff --check`.

- [ ] **Step 1: Fix `act(...)` warning in `user-profile.test.tsx`**

In `frontend/tests/features/auth/user-profile.test.tsx`:
Properly await async resolution of `getCurrentPrincipal` inside `waitFor` before asserting modal close or firing key events.

- [ ] **Step 2: Replace asymmetric side-tab accent borders**

In `frontend/src/features/catalog/BookDetail.tsx`:
Replace `borderLeft: 4px solid ...` with balanced card border:
```tsx
border: `1px solid ${tokens.colors.border}`,
borderRadius: tokens.radius.md,
```
In `frontend/src/features/inventory/StatusHistoryView.tsx`:
Replace `borderLeft: 3px solid ...` with balanced border:
```tsx
border: `1px solid ${tokens.colors.borderMuted}`,
borderRadius: tokens.radius.sm,
```

- [ ] **Step 3: Remove trailing whitespace and excess blank lines**

Run whitespace cleaning on the files reported by `git diff --check f54da53..HEAD`.

- [ ] **Step 4: Verify test warnings and git diff check**

Run:
```bash
npm test -- tests/features/auth/user-profile.test.tsx
git diff --check f54da53..HEAD
```
Expected: 0 warnings, git diff --check reports 0 whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/features/auth/user-profile.test.tsx frontend/src/features/catalog/BookDetail.tsx frontend/src/features/inventory/StatusHistoryView.tsx .github/ci/compose.env .gitignore PRODUCT.md docs/superpowers/plans/2026-09-23-be-028-production-release.md tasks/backend/BE-023.md tasks/backend/BE-025.md tasks/frontend/FE-007.md
git commit -m "fix(polish): eliminate act warnings, standardize card borders and resolve whitespace hygiene"
```

---

### Task 9: Full Verification, Browser Smoke Testing & Audit Clearance

**Files:**
- Create/Update: `docs/FULL_SYSTEM_AUDIT_2026-09-26.md` (record clearance of all findings)
- Chrome DevTools MCP browser testing

**Interfaces:**
- Produces: Fresh execution output proving 100% test passing, 0 mypy errors, 0 linter errors, responsive App Shell without overflow at 375px and 1440px.

- [ ] **Step 1: Run comprehensive backend verification**

```bash
cd backend
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest -q
```
Expected: All PASS, 0 errors.

- [ ] **Step 2: Run comprehensive frontend verification**

```bash
cd frontend
npm run lint
npm run typecheck
npm test -- --reporter=dot
npm run build
```
Expected: All PASS, 0 errors, 0 warnings.

- [ ] **Step 3: Run OpenAPI compatibility check**

```bash
openapi-spec-validator contracts/openapi/v1.yaml
```
Expected: Valid OpenAPI 3.1.0 specification.

- [ ] **Step 4: Execute Chrome DevTools browser smoke test**

Launch Vite preview or dev server:
- Check desktop viewport (1440px): verify AppHeader navigation fits without horizontal scrollbar.
- Check mobile viewport (375px): verify header does not overflow horizontally (`document.documentElement.scrollWidth <= 375`).
- Open Dialog: verify focus is trapped within dialog elements and Escape closes it.
- Verify opening app without session cookie displays clean login form without credential error banner.

- [ ] **Step 5: Update audit document and commit**

Record the verification command outputs and resolution evidence in `docs/FULL_SYSTEM_AUDIT_2026-09-26.md`.
Commit final remediation:
```bash
git add docs/FULL_SYSTEM_AUDIT_2026-09-26.md
git commit -m "docs: record full clearance of 2026-09-26 system audit findings"
```
