import { AccessTokenResponse, LoginCredentials } from './types';
import { apiClient } from '../../shared/api';

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
 * Authenticate in the named organization via the typed API client.
 * Uses centralized apiClient.auth.login rather than assembling endpoint strings.
 */
export async function login(credentials: LoginCredentials): Promise<AccessTokenResponse> {
  try {
    const data = await apiClient.auth.login({
      organization_slug: credentials.organization_slug,
      email: credentials.email,
      password: credentials.password,
    });
    return data;
  } catch {
    throw new Error(AUTH_SAFE_ERROR_MESSAGE);
  }
}

/**
 * Rotate refresh session and issue a new access token using HttpOnly cookie.
 * Uses centralized apiClient.auth.refreshAccessToken rather than assembling endpoint strings.
 */
export async function refreshToken(): Promise<AccessTokenResponse> {
  try {
    const data = await apiClient.auth.refreshAccessToken();
    return data;
  } catch {
    throw new Error(AUTH_SAFE_ERROR_MESSAGE);
  }
}

/**
 * Revoke the current refresh session chain.
 * Uses centralized apiClient.auth.logout rather than assembling endpoint strings.
 */
export async function logout(accessToken?: string | null): Promise<void> {
  try {
    await apiClient.auth.logout(accessToken);
  } catch {
    // Revocation is best effort on client teardown
  }
}
