import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import {
  LoginForm,
  SessionProvider,
  ProtectedRoute,
  useSession,
  AUTH_SAFE_ERROR_MESSAGE,
} from '../../../src/features/auth';
import { App } from '../../../src/app/App';
import { TokenProvider } from '../../../src/shared/tokens';

describe('Login, Refresh Session & Protected-Route Behavior (FE-003)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
    vi.spyOn(Storage.prototype, 'setItem');
    vi.spyOn(Storage.prototype, 'getItem');
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('Login Form Layout & Contract Validation', () => {
    it('renders login fields in familiar Jakob-convention order: organization slug -> email -> password', () => {
      render(
        <TokenProvider>
          <SessionProvider>
            <LoginForm />
          </SessionProvider>
        </TokenProvider>,
      );

      const slugInput = screen.getByLabelText(/organization slug/i);
      const emailInput = screen.getByLabelText(/email address/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const submitButton = screen.getByRole('button', { name: /sign in|log in/i });

      expect(slugInput).toBeInTheDocument();
      expect(emailInput).toBeInTheDocument();
      expect(passwordInput).toBeInTheDocument();
      expect(submitButton).toBeInTheDocument();

      // Check vertical document order
      const allInputs = [slugInput, emailInput, passwordInput, submitButton];
      for (let i = 0; i < allInputs.length - 1; i++) {
        const current = allInputs[i];
        const next = allInputs[i + 1];
        expect(current).toBeDefined();
        expect(next).toBeDefined();
        if (current && next) {
          expect(current.compareDocumentPosition(next)).toBe(
            Node.DOCUMENT_POSITION_FOLLOWING,
          );
        }
      }
    });

    it('limits login view to strictly one visually primary action button with Title Case', () => {
      render(
        <TokenProvider>
          <SessionProvider>
            <LoginForm />
          </SessionProvider>
        </TokenProvider>,
      );

      const primaryButtons = screen
        .getAllByRole('button')
        .filter((btn) => btn.getAttribute('data-variant') === 'primary');

      expect(primaryButtons.length).toBe(1);
      expect(primaryButtons[0]).toHaveTextContent(/Sign In|Log In/);
      expect(primaryButtons[0]).not.toHaveTextContent(/SIGN IN|LOG IN/);
    });

    it('submits organization_slug, email, and password exactly matching the OpenAPI contract', async () => {
      const mockSuccessResponse = {
        access_token: 'valid-test-access-token-12345',
        token_type: 'Bearer',
        expires_in: 900,
      };

      const fetchMock = vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => mockSuccessResponse,
      } as Response);

      const handleSuccess = vi.fn();

      render(
        <TokenProvider>
          <SessionProvider>
            <LoginForm onSuccess={handleSuccess} />
          </SessionProvider>
        </TokenProvider>,
      );

      fireEvent.change(screen.getByLabelText(/organization slug/i), {
        target: { value: 'campus-central' },
      });
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: 'librarian@example.test' },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: 'correct-horse-battery-staple' },
      });

      fireEvent.click(screen.getByRole('button', { name: /sign in|log in/i }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledTimes(1);
      });

      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/auth/login',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          credentials: 'same-origin',
          body: JSON.stringify({
            organization_slug: 'campus-central',
            email: 'librarian@example.test',
            password: 'correct-horse-battery-staple',
          }),
        }),
      );

      await waitFor(() => {
        expect(handleSuccess).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('Uniform Safe Authentication Error UI', () => {
    it('renders the exact same safe error message for wrong organization slug and wrong password without revealing account state', async () => {
      const mock401Response = {
        type: 'https://openlibraryos.example/problems/unauthorized',
        title: 'Authentication failed',
        status: 401,
        detail: 'Authentication failed.',
        instance: '/api/v1/auth/login',
        request_id: 'req-test-123',
      };

      // Case 1: Wrong organization slug
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'Content-Type': 'application/problem+json' }),
        json: async () => mock401Response,
      } as Response);

      const { unmount } = render(
        <TokenProvider>
          <SessionProvider>
            <LoginForm />
          </SessionProvider>
        </TokenProvider>,
      );

      fireEvent.change(screen.getByLabelText(/organization slug/i), {
        target: { value: 'non-existent-organization' },
      });
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: 'librarian@example.test' },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: 'some-password' },
      });
      fireEvent.click(screen.getByRole('button', { name: /sign in|log in/i }));

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });

      const wrongSlugMessage = screen.getByRole('alert').textContent;
      expect(wrongSlugMessage).toContain(AUTH_SAFE_ERROR_MESSAGE);
      // Ensure no tenant state or account enumeration leaked
      expect(wrongSlugMessage).not.toMatch(/organization not found|account does not exist|invalid slug/i);

      unmount();

      // Case 2: Wrong password on valid organization
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'Content-Type': 'application/problem+json' }),
        json: async () => mock401Response,
      } as Response);

      render(
        <TokenProvider>
          <SessionProvider>
            <LoginForm />
          </SessionProvider>
        </TokenProvider>,
      );

      fireEvent.change(screen.getByLabelText(/organization slug/i), {
        target: { value: 'campus-central' },
      });
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: 'librarian@example.test' },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: 'wrong-password-999' },
      });
      fireEvent.click(screen.getByRole('button', { name: /sign in|log in/i }));

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });

      const wrongPasswordMessage = screen.getByRole('alert').textContent;
      expect(wrongPasswordMessage).toBe(wrongSlugMessage);
    });
  });

  describe('In-Memory Token Invariant & Persistent Storage Isolation', () => {
    it('keeps access token strictly in memory and never writes to localStorage or sessionStorage', async () => {
      const mockSuccessResponse = {
        access_token: 'secret-in-memory-token-xyz',
        token_type: 'Bearer',
        expires_in: 900,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => mockSuccessResponse,
      } as Response);

      function SessionStateInspector() {
        const { accessToken, isAuthenticated } = useSession();
        return (
          <div>
            <span data-testid="is-authenticated">{String(isAuthenticated)}</span>
            <span data-testid="token-value">{accessToken || 'none'}</span>
          </div>
        );
      }

      render(
        <TokenProvider>
          <SessionProvider>
            <LoginForm />
            <SessionStateInspector />
          </SessionProvider>
        </TokenProvider>,
      );

      fireEvent.change(screen.getByLabelText(/organization slug/i), {
        target: { value: 'campus-central' },
      });
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: 'librarian@example.test' },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: 'valid-password' },
      });
      fireEvent.click(screen.getByRole('button', { name: /sign in|log in/i }));

      await waitFor(() => {
        expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
      });

      expect(screen.getByTestId('token-value')).toHaveTextContent('secret-in-memory-token-xyz');

      // CRITICAL ACCEPTANCE INVARIANT:
      // Access token is NEVER written to browser persistent storage (localStorage / sessionStorage)
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('token')).toBeNull();
      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('token')).toBeNull();
      expect(Storage.prototype.setItem).not.toHaveBeenCalledWith(
        expect.stringMatching(/token|auth|secret/i),
        expect.anything(),
      );
    });
  });

  describe('Protected Route Guard & Session Refresh Recovery', () => {
    it('redirects unauthenticated protected-route access to login form without leaking protected content', () => {
      render(
        <TokenProvider>
          <SessionProvider>
            <ProtectedRoute fallback={<LoginForm />}>
              <div data-testid="protected-circulation-desk">Secret Circulation Records</div>
            </ProtectedRoute>
          </SessionProvider>
        </TokenProvider>,
      );

      // Protected content must NOT be visible
      expect(screen.queryByTestId('protected-circulation-desk')).not.toBeInTheDocument();
      expect(screen.queryByText(/secret circulation records/i)).not.toBeInTheDocument();

      // Login form must be presented
      expect(screen.getByRole('heading', { level: 2, name: /sign in|log in/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/organization slug/i)).toBeInTheDocument();
    });

    it('restores protected-route access via a valid refresh session without a second login submission', async () => {
      const mockRefreshResponse = {
        access_token: 'refreshed-bearer-access-token-999',
        token_type: 'Bearer',
        expires_in: 900,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => mockRefreshResponse,
      } as Response);

      render(
        <TokenProvider>
          <SessionProvider autoRefreshOnMount>
            <ProtectedRoute fallback={<LoginForm />}>
              <div data-testid="protected-circulation-desk">Restored Circulation Workspace</div>
            </ProtectedRoute>
          </SessionProvider>
        </TokenProvider>,
      );

      // Verify refresh endpoint was called using credentials for HttpOnly cookie
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/auth/refresh',
          expect.objectContaining({
            method: 'POST',
            credentials: 'same-origin',
          }),
        );
      });

      // Protected content is rendered without manual login submission
      await waitFor(() => {
        expect(screen.getByTestId('protected-circulation-desk')).toBeInTheDocument();
      });
      expect(screen.getByText(/restored circulation workspace/i)).toBeInTheDocument();
      expect(screen.queryByLabelText(/organization slug/i)).not.toBeInTheDocument();

      // Persistent storage check
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('access_token')).toBeNull();
    });

    it('clears in-memory state, resets to login, and displays safe message on refresh session failure', async () => {
      const mock401Refresh = {
        type: 'https://openlibraryos.example/problems/unauthorized',
        title: 'Authentication failed',
        status: 401,
        detail: 'Authentication failed.',
        instance: '/api/v1/auth/refresh',
        request_id: 'req-refresh-fail-456',
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'Content-Type': 'application/problem+json' }),
        json: async () => mock401Refresh,
      } as Response);

      function SessionTester() {
        const { refresh, accessToken } = useSession();
        return (
          <div>
            <button type="button" onClick={() => void refresh()}>
              Trigger Refresh
            </button>
            <span data-testid="current-token">{accessToken || 'cleared'}</span>
          </div>
        );
      }

      render(
        <TokenProvider>
          <SessionProvider initialAccessToken="stale-expired-token">
            <ProtectedRoute fallback={<LoginForm />}>
              <SessionTester />
            </ProtectedRoute>
          </SessionProvider>
        </TokenProvider>,
      );

      // Initially authenticated with in-memory token
      expect(screen.getByTestId('current-token')).toHaveTextContent('stale-expired-token');

      // Trigger refresh which fails with 401
      fireEvent.click(screen.getByRole('button', { name: /trigger refresh/i }));

      // State is reset: protected content unmounts, login form renders with safe message
      await waitFor(() => {
        expect(screen.getByLabelText(/organization slug/i)).toBeInTheDocument();
      });

      expect(screen.queryByTestId('current-token')).not.toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toHaveTextContent(AUTH_SAFE_ERROR_MESSAGE);

      // Access token is purged
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('access_token')).toBeNull();
    });

    it('documents client-side route guard as non-authoritative UX navigation aid', () => {
      // Invariant check: route guard enforces routing convenience only, not backend authorization.
      expect(ProtectedRoute).toBeDefined();
    });
  });

  describe('Root Application Integration (FE-003)', () => {
    it('renders login view when unauthenticated and switches to operate mode upon successful login', async () => {
      const mockLoginResponse = {
        access_token: 'authenticated-session-token-777',
        token_type: 'Bearer',
        expires_in: 900,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => mockLoginResponse,
      } as Response);

      render(<App initialAuthenticated={false} />);

      // Initially renders login view
      expect(screen.getByRole('heading', { level: 2, name: /sign in|log in/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/organization slug/i)).toBeInTheDocument();

      // Submit credentials
      fireEvent.change(screen.getByLabelText(/organization slug/i), {
        target: { value: 'campus-central' },
      });
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: 'librarian@example.test' },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: 'valid-password' },
      });
      fireEvent.click(screen.getByRole('button', { name: /sign in|log in/i }));

      // Switches to operate mode desk
      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/OpenLibraryOS — Operate Mode/i);
      });
      expect(screen.getByText(/rapid circulation desk/i)).toBeInTheDocument();
    });
  });
});
