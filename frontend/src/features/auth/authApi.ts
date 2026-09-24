import { AccessTokenResponse, LoginCredentials } from './types';

/**
 * Uniform safe authentication error message.
 *
 * CRITICAL SECURITY INVARIANT:
 * Authentication error responses MUST NEVER reveal whether an organization slug,
 * tenant, or user account exists in the database. Both wrong slug and wrong
 * password return this identical safe message.
 */
export const AUTH_SAFE_ERROR_MESSAGE =
  'Authentication failed. Please verify your organization slug, email, and password.';

/**
 * Extracts CSRF token from document cookies if present.
 */
export function getCsrfTokenFromCookie(): string | null {
  if (typeof document === 'undefined' || !document.cookie) {
    return null;
  }
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  const token = match?.[1];
  return token ? decodeURIComponent(token) : null;
}

/**
 * Authenticate in the named organization via the API contract.
 */
export async function login(credentials: LoginCredentials): Promise<AccessTokenResponse> {
  let response: Response;
  try {
    response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
      body: JSON.stringify({
        organization_slug: credentials.organization_slug,
        email: credentials.email,
        password: credentials.password,
      }),
    });
  } catch {
    throw new Error(AUTH_SAFE_ERROR_MESSAGE);
  }

  if (!response.ok) {
    throw new Error(AUTH_SAFE_ERROR_MESSAGE);
  }

  const data = (await response.json()) as AccessTokenResponse;
  return data;
}

/**
 * Rotate refresh session and issue a new access token using HttpOnly cookie.
 */
export async function refreshToken(): Promise<AccessTokenResponse> {
  const csrfToken = getCsrfTokenFromCookie();
  const headers: Record<string, string> = {};
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  let response: Response;
  try {
    response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers,
      credentials: 'same-origin',
    });
  } catch {
    throw new Error(AUTH_SAFE_ERROR_MESSAGE);
  }

  if (!response.ok) {
    throw new Error(AUTH_SAFE_ERROR_MESSAGE);
  }

  const data = (await response.json()) as AccessTokenResponse;
  return data;
}

/**
 * Revoke the current refresh session chain.
 */
export async function logout(accessToken?: string | null): Promise<void> {
  const csrfToken = getCsrfTokenFromCookie();
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  try {
    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      headers,
      credentials: 'same-origin',
    });
  } catch {
    // Revocation is best effort on client teardown
  }
}
