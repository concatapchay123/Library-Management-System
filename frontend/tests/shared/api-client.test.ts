import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';

import {
  createApiClient,
  apiClient,
  ProblemDetailsError,
  normalizeProblemDetails,
  ProblemDetails,
} from '../../src/shared/api';
import {
  ProblemDetailsRenderer,
  LoadingSkeleton,
  EmptyState,
  RequestStateView,
} from '../../src/shared/components';
import { TokenProvider } from '../../src/shared/tokens';

describe('FE-004 — Typed API Client, Problem Details and Common Request States', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Typed Request Serialization and Client Behavior', () => {
    it('sets default JSON headers, credentials same-origin, and request correlation ID', async () => {
      const mockFetch = vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'server-req-001',
        }),
        json: async () => ({ status: 'pass' }),
      } as Response);

      const client = createApiClient({ baseUrl: '/api/v1' });
      const result = await client.request<{ status: string }>('/health/live', {
        method: 'GET',
      });

      expect(result).toEqual({ status: 'pass' });
      expect(mockFetch).toHaveBeenCalledTimes(1);

      const call = mockFetch.mock.calls[0];
      expect(call).toBeDefined();
      const [calledUrl, calledInit] = call!;
      expect(calledUrl).toBe('/api/v1/health/live');
      expect(calledInit?.credentials).toBe('same-origin');

      const headers = new Headers(calledInit?.headers);
      expect(headers.get('Content-Type')).toBe('application/json');
      expect(headers.get('Accept')).toContain('application/json');
      expect(headers.get('Accept')).toContain('application/problem+json');
      // Correlation ID must match RFC regex ^[A-Za-z0-9._-]{1,128}$
      const reqId = headers.get('X-Request-ID');
      expect(reqId).toBeTruthy();
      expect(reqId).toMatch(/^[A-Za-z0-9._-]{1,128}$/);
    });

    it('injects Bearer authorization token when session access token is present', async () => {
      const mockFetch = vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({
          user_id: 'user-123',
          organization_id: 'org-456',
          role: 'librarian',
        }),
      } as Response);

      const client = createApiClient({
        baseUrl: '/api/v1',
        getAccessToken: () => 'in-memory-bearer-token-abc',
      });

      await client.request('/auth/me', { method: 'GET' });

      const call = mockFetch.mock.calls[0];
      expect(call).toBeDefined();
      const [, calledInit] = call!;
      const headers = new Headers(calledInit?.headers);
      expect(headers.get('Authorization')).toBe('Bearer in-memory-bearer-token-abc');
    });

    it('attaches Idempotency-Key header when supplied for safe replay', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ checkout_id: 'chk-001' }),
      } as Response);

      const client = createApiClient({ baseUrl: '/api/v1' });
      await client.request('/circulation/checkout', {
        method: 'POST',
        body: JSON.stringify({ item_id: 'item-1' }),
        idempotencyKey: 'idemp-key-xyz-789',
      });

      const call = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(call).toBeDefined();
      const [, calledInit] = call!;
      const headers = new Headers(calledInit?.headers);
      expect(headers.get('Idempotency-Key')).toBe('idemp-key-xyz-789');
    });

    it('handles 204 No Content responses cleanly without JSON parsing errors', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
        text: async () => '',
      } as Response);

      const client = createApiClient({ baseUrl: '/api/v1' });
      const result = await client.request<void>('/auth/logout', { method: 'POST' });
      expect(result).toBeUndefined();
    });

    it('exposes typed OpenAPI operation helpers on default client singleton', async () => {
      const mockFetch = vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ status: 'healthy', version: '1.0.0' }),
      } as Response);

      const liveHealth = await apiClient.health.getLiveHealth();
      expect(liveHealth).toEqual({ status: 'healthy', version: '1.0.0' });
      const call = mockFetch.mock.calls[0];
      expect(call).toBeDefined();
      expect(call?.[0]).toBe('/api/v1/health/live');
    });
  });

  describe('RFC Problem Details Normalization & Security Sanitization', () => {
    it('normalizes valid RFC 7807 Problem Details into ProblemDetailsError with visible request_id', async () => {
      const mockProblemPayload: ProblemDetails = {
        type: 'https://openlibraryos.example/problems/not-found',
        title: 'Resource Not Found',
        status: 404,
        detail: 'The requested book copy was not found in the inventory.',
        instance: '/api/v1/catalog/books/isbn-999',
        request_id: 'req-corr-404-abc',
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 404,
        headers: new Headers({
          'Content-Type': 'application/problem+json',
          'X-Request-ID': 'req-corr-404-abc',
        }),
        json: async () => mockProblemPayload,
      } as Response);

      const client = createApiClient({ baseUrl: '/api/v1' });

      let thrownError: unknown = null;
      try {
        await client.request('/catalog/books/isbn-999', { method: 'GET' });
      } catch (err) {
        thrownError = err;
      }

      expect(thrownError).toBeInstanceOf(ProblemDetailsError);
      const error = thrownError as ProblemDetailsError;
      expect(error.status).toBe(404);
      expect(error.title).toBe('Resource Not Found');
      expect(error.detail).toBe('The requested book copy was not found in the inventory.');
      expect(error.instance).toBe('/api/v1/catalog/books/isbn-999');
      expect(error.requestId).toBe('req-corr-404-abc');
      expect(error.helpfulAction).toContain('Check the identifier or link');
      expect(error.isSafeToRetry).toBe(true); // GET is safe
    });

    it('sanitizes raw SQL, stack traces, and token data to protect security invariants', () => {
      // 1. Raw SQL query
      const sqlError = normalizeProblemDetails({
        type: 'https://openlibraryos.example/problems/internal-server-error',
        title: 'Database Query Failed',
        status: 500,
        detail: 'SELECT * FROM users WHERE organization_id = 42 failed with ODBC Driver 17',
        instance: '/api/v1/users',
        request_id: 'req-sql-001',
      });

      expect(sqlError.detail).not.toContain('SELECT');
      expect(sqlError.detail).not.toContain('organization_id');
      expect(sqlError.detail).not.toContain('ODBC');
      expect(sqlError.detail).toBe('A database error occurred. Please contact support with the request ID.');
      expect(sqlError.requestId).toBe('req-sql-001');

      // 2. Python traceback
      const traceError = normalizeProblemDetails({
        type: 'https://openlibraryos.example/problems/internal-server-error',
        title: 'Unhandled Exception',
        status: 500,
        detail: 'Traceback (most recent call last):\n  File "worker.py", line 42, in process\nValueError: null pointer',
        instance: '/api/v1/worker',
        request_id: 'req-trace-002',
      });

      expect(traceError.detail).not.toContain('Traceback');
      expect(traceError.detail).not.toContain('worker.py');
      expect(traceError.detail).toBe('An unexpected server error occurred. Please contact support with the request ID.');

      // 3. Sensitive token / credential leakage
      const tokenError = normalizeProblemDetails({
        type: 'https://openlibraryos.example/problems/unauthorized',
        title: 'Invalid Token',
        status: 401,
        detail: 'Token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 expired for secret_key=foobar',
        instance: '/api/v1/auth/me',
        request_id: 'req-token-003',
      });

      expect(tokenError.detail).not.toContain('eyJhbGci');
      expect(tokenError.detail).not.toContain('secret_key');
      expect(tokenError.detail).toBe('Authentication credentials are invalid or expired.');
    });

    it('differentiates safe GET requests from unsafe POST/PUT/DELETE mutations for retry control', () => {
      const getError = normalizeProblemDetails(
        {
          type: 'https://openlibraryos.example/problems/service-unavailable',
          title: 'Service Unavailable',
          status: 503,
          detail: 'Database connection pool exhausted.',
          instance: '/api/v1/catalog',
          request_id: 'req-503-get',
        },
        503,
        'req-503-get',
        'GET',
      );
      expect(getError.isSafeToRetry).toBe(true);

      const postError = normalizeProblemDetails(
        {
          type: 'https://openlibraryos.example/problems/service-unavailable',
          title: 'Service Unavailable',
          status: 503,
          detail: 'Transaction interrupted.',
          instance: '/api/v1/circulation/checkout',
          request_id: 'req-503-post',
        },
        503,
        'req-503-post',
        'POST',
      );
      // Mutating POST request is NOT marked safe to repeat blindly without idempotency guarantee
      expect(postError.isSafeToRetry).toBe(false);
    });

    it('preserves backend authorization and status code decisions without alteration', () => {
      const authError = normalizeProblemDetails(
        {
          type: 'https://openlibraryos.example/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'Authorization denied.',
          instance: '/api/v1/admin/settings',
          request_id: 'req-403-auth',
        },
        403,
        'req-403-auth',
        'GET',
      );

      expect(authError.status).toBe(403);
      expect(authError.title).toBe('Forbidden');
      expect(authError.helpfulAction).toContain('library administrator');
      // Authorization decision remains strictly 403
      expect(authError.problem.status).toBe(403);
    });
  });

  describe('Problem Details Renderer & Visible Support Request ID', () => {
    it('renders title, helpful action, and visible support request_id with copy option', () => {
      const problemError = new ProblemDetailsError({
        type: 'https://openlibraryos.example/problems/not-found',
        title: 'Book Copy Not Found',
        status: 404,
        detail: 'The requested copy identifier was not found in catalog circulation.',
        instance: '/api/v1/circulation/copies/12345',
        request_id: 'SUPPORT-REQ-12345-ABC',
        helpfulAction: 'Check the barcode or search the catalog by title.',
        isSafeToRetry: true,
      });

      render(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(ProblemDetailsRenderer, { error: problemError }),
        ),
      );

      // Verify title & detail
      expect(screen.getByText('Book Copy Not Found')).toBeInTheDocument();
      expect(
        screen.getByText('The requested copy identifier was not found in catalog circulation.'),
      ).toBeInTheDocument();

      // Verify helpful action
      expect(
        screen.getByText('Check the barcode or search the catalog by title.'),
      ).toBeInTheDocument();

      // Verify visible support request_id
      const supportReqIdContainer = screen.getByTestId('support-request-id');
      expect(supportReqIdContainer).toBeInTheDocument();
      expect(supportReqIdContainer).toHaveTextContent('SUPPORT-REQ-12345-ABC');

      // Verify non-color status cue (icon + text badge)
      expect(screen.getByTestId('status-icon-danger')).toBeInTheDocument();
      expect(screen.getByText('ERROR')).toBeInTheDocument();
    });

    it('provides copy button for the support request_id', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      const problemError = new ProblemDetailsError({
        type: 'https://openlibraryos.example/problems/internal-server-error',
        title: 'Server Error',
        status: 500,
        detail: 'A server error occurred.',
        instance: '/api/v1/health',
        request_id: 'REQ-COPY-TEST-999',
        helpfulAction: 'Contact library system support.',
        isSafeToRetry: true,
      });

      render(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(ProblemDetailsRenderer, { error: problemError }),
        ),
      );

      const copyBtn = screen.getByRole('button', { name: /copy request id|copy id/i });
      expect(copyBtn).toBeInTheDocument();

      await act(async () => {
        fireEvent.click(copyBtn);
      });
      expect(writeTextMock).toHaveBeenCalledWith('REQ-COPY-TEST-999');
    });
  });

  describe('Reusable Common Request States (Loading, Empty, Retry)', () => {
    it('renders accessible loading skeleton with aria-busy="true"', () => {
      render(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(LoadingSkeleton, { lines: 3, ariaLabel: 'Loading catalog books' }),
        ),
      );

      const skeletonRegion = screen.getByRole('status');
      expect(skeletonRegion).toBeInTheDocument();
      expect(skeletonRegion).toHaveAttribute('aria-busy', 'true');
      expect(skeletonRegion).toHaveAttribute('aria-label', 'Loading catalog books');

      // Skeleton bars exist
      const shimmerBars = screen.getAllByTestId('skeleton-shimmer-bar');
      expect(shimmerBars.length).toBe(3);
    });

    it('renders empty state stating what is absent and one next action permitted', () => {
      const handleAction = vi.fn();

      render(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(EmptyState, {
            title: 'No Books in Catalog',
            description: 'No book records have been added to this library collection yet.',
            action: {
              label: 'Add First Book',
              onAction: handleAction,
            },
          }),
        ),
      );

      expect(screen.getByText('No Books in Catalog')).toBeInTheDocument();
      expect(
        screen.getByText('No book records have been added to this library collection yet.'),
      ).toBeInTheDocument();

      const actionBtn = screen.getByRole('button', { name: 'Add First Book' });
      expect(actionBtn).toBeInTheDocument();
      expect(actionBtn).toHaveAttribute('data-variant', 'primary');

      fireEvent.click(actionBtn);
      expect(handleAction).toHaveBeenCalledTimes(1);
    });

    it('renders retry button in RequestStateView ONLY when request is safe to retry', () => {
      const onRetryMock = vi.fn();

      // 1. Safe request (e.g. GET failed)
      const safeError = new ProblemDetailsError({
        type: 'https://openlibraryos.example/problems/service-unavailable',
        title: 'Catalog Service Temporarily Offline',
        status: 503,
        detail: 'Catalog service is restarting.',
        instance: '/api/v1/catalog',
        request_id: 'REQ-SAFE-RETRY-1',
        helpfulAction: 'Please retry your request in a few moments.',
        isSafeToRetry: true,
      });

      const { rerender } = render(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(
            RequestStateView,
            {
              status: 'error',
              error: safeError,
              onRetry: onRetryMock,
              isSafeToRetry: true,
            },
            React.createElement('div', null, 'Catalog Content'),
          ),
        ),
      );

      const retryBtn = screen.getByRole('button', { name: /retry request|retry/i });
      expect(retryBtn).toBeInTheDocument();
      fireEvent.click(retryBtn);
      expect(onRetryMock).toHaveBeenCalledTimes(1);

      // 2. Unsafe request (e.g. mutating POST payment or checkout failed)
      const unsafeError = new ProblemDetailsError({
        type: 'https://openlibraryos.example/problems/conflict',
        title: 'Payment Processing Failed',
        status: 409,
        detail: 'Payment could not be completed.',
        instance: '/api/v1/payments',
        request_id: 'REQ-UNSAFE-RETRY-2',
        helpfulAction: 'Review transaction record before attempting payment again.',
        isSafeToRetry: false,
      });

      rerender(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(
            RequestStateView,
            {
              status: 'error',
              error: unsafeError,
              onRetry: onRetryMock,
              isSafeToRetry: false,
            },
            React.createElement('div', null, 'Catalog Content'),
          ),
        ),
      );

      // Retry button MUST NOT be displayed for unsafe repeating
      expect(screen.queryByRole('button', { name: /retry request|retry/i })).not.toBeInTheDocument();
      expect(
        screen.getByText(/cannot be automatically repeated|review before repeating/i),
      ).toBeInTheDocument();
    });

    it('renders children when RequestStateView status is success', () => {
      render(
        React.createElement(
          TokenProvider,
          null,
          React.createElement(
            RequestStateView,
            { status: 'success' },
            React.createElement('div', { 'data-testid': 'live-content' }, 'Active Circulation Table'),
          ),
        ),
      );

      expect(screen.getByTestId('live-content')).toBeInTheDocument();
      expect(screen.getByText('Active Circulation Table')).toBeInTheDocument();
    });
  });
});
