/**
 * Typed API Contract & Client Type Definitions for OpenLibraryOS.
 *
 * Derived directly from contracts/openapi/v1.yaml.
 * Breaking changes require a new API major version.
 */

/**
 * Standard RFC 7807 / RFC 9457 Problem Details Object.
 * Required fields match the OpenAPI schema: type, title, status, detail, instance, request_id.
 */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  request_id: string;
  errors?: Array<Record<string, unknown>>;
}

/**
 * Health Status schema from OpenAPI #/components/schemas/HealthStatus
 */
export interface HealthStatus {
  status: string;
  version?: string;
  uptime_seconds?: number;
  [key: string]: unknown;
}

/**
 * Worker Health Status schema from OpenAPI #/components/schemas/WorkerHealthStatus
 */
export interface WorkerHealthStatus {
  status: string;
  worker_health?: string;
  queue_depths?: Record<string, number>;
  dead_letter_visibility?: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Login Request schema from OpenAPI #/components/schemas/LoginRequest
 */
export interface LoginRequest {
  organization_slug: string;
  email: string;
  password: string;
}

/**
 * Access Token response schema from OpenAPI #/components/schemas/AccessToken
 */
export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * Access Principal schema from OpenAPI #/components/schemas/AccessPrincipal
 */
export interface AccessPrincipal {
  user_id: string;
  organization_id: string;
  role: string;
  permissions?: string[];
  [key: string]: unknown;
}

/**
 * Organization Settings schema from OpenAPI #/components/schemas/OrganizationSettings
 */
export interface OrganizationSettings {
  organization_id: string;
  slug: string;
  name: string;
  [key: string]: unknown;
}

/**
 * Supported HTTP methods for typed client calls.
 */
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';

/**
 * Options for client requests.
 */
export interface RequestOptions extends Omit<RequestInit, 'headers'> {
  headers?: Record<string, string>;
  requestId?: string;
  idempotencyKey?: string;
  csrfToken?: string;
  token?: string | null;
  isSafeToRetry?: boolean;
}

/**
 * Configuration options when instantiating the API client.
 */
export interface ApiClientConfig {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
  getCsrfToken?: () => string | null | undefined;
}
