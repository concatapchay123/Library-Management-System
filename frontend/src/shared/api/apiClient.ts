import {
  ApiClientConfig,
  RequestOptions,
  HealthStatus,
  WorkerHealthStatus,
  LoginRequest,
  AccessTokenResponse,
  AccessPrincipal,
  OrganizationSettings,
} from './types';
import {
  generateRequestId,
  normalizeProblemDetails,
  ProblemDetailsError,
} from './problemDetails';

/**
 * Extracts CSRF token from document cookie when available in browser environments.
 */
function getCookieCsrfToken(): string | null {
  if (typeof document === 'undefined' || !document.cookie) {
    return null;
  }
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  const token = match?.[1];
  return token ? decodeURIComponent(token) : null;
}

/**
 * Creates an instance of the typed OpenAPI client.
 */
export function createApiClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? '/api/v1';

  async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const url = endpoint.startsWith('http') || endpoint.startsWith('/api/v1')
      ? endpoint
      : `${baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

    const method = (options.method || 'GET').toUpperCase();
    const requestId = options.requestId || generateRequestId();

    // Prepare standard headers
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json, application/problem+json',
      'X-Request-ID': requestId,
      ...options.headers,
    };

    // Bearer token resolution
    const token = options.token ?? config.getAccessToken?.();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // CSRF token resolution
    const csrfToken = options.csrfToken ?? config.getCsrfToken?.() ?? getCookieCsrfToken();
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }

    // Idempotency key for safe replay
    if (options.idempotencyKey) {
      headers['Idempotency-Key'] = options.idempotencyKey;
    }

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        method,
        headers,
        credentials: options.credentials || 'same-origin',
      });
    } catch (err) {
      const networkMessage = err instanceof Error ? err.message : 'Network request failed';
      throw normalizeProblemDetails(networkMessage, 0, requestId, method);
    }

    const serverRequestId = response.headers.get('X-Request-ID') || requestId;

    // Handle 204 No Content
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      if (!response.ok) {
        throw normalizeProblemDetails('Request failed', response.status, serverRequestId, method);
      }
      return undefined as unknown as T;
    }

    let responseBody: unknown = null;
    const contentType = response.headers.get('content-type') || '';

    try {
      if (contentType.includes('json')) {
        responseBody = await response.json();
      } else {
        responseBody = await response.text();
      }
    } catch {
      responseBody = null;
    }

    if (!response.ok) {
      throw normalizeProblemDetails(
        responseBody,
        response.status,
        serverRequestId,
        method,
      );
    }

    return responseBody as T;
  }

  // Common convenience HTTP methods
  function get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'GET' });
  }

  function post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: 'POST',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    });
  }

  function put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: 'PUT',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    });
  }

  function del<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'DELETE' });
  }

  // Typed OpenAPI contract domain modules
  const health = {
    getLiveHealth: (options?: RequestOptions) =>
      get<HealthStatus>('/health/live', options),
    getReadinessHealth: (options?: RequestOptions) =>
      get<HealthStatus>('/health/ready', options),
    getWorkerHealth: (options?: RequestOptions) =>
      get<WorkerHealthStatus>('/health/worker', options),
  };

  const auth = {
    login: (credentials: LoginRequest, options?: RequestOptions) =>
      post<AccessTokenResponse>('/auth/login', credentials, options),
    refreshAccessToken: (options?: RequestOptions) =>
      post<AccessTokenResponse>('/auth/refresh', undefined, options),
    logout: (token?: string | null, options?: RequestOptions) =>
      post<void>('/auth/logout', undefined, { ...options, token }),
    getCurrentPrincipal: (token?: string, options?: RequestOptions) =>
      get<AccessPrincipal>('/auth/me', { ...options, token }),
  };

  const organizations = {
    getSettings: (token?: string, options?: RequestOptions) =>
      get<OrganizationSettings>('/organizations/settings', { ...options, token }),
  };

  return {
    request,
    get,
    post,
    put,
    delete: del,
    health,
    auth,
    organizations,
  };
}

/**
 * Singleton API client instance with standard default configuration.
 */
export const apiClient = createApiClient();
export { ProblemDetailsError };
