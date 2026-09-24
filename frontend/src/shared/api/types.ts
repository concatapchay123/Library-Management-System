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
 * Bibliographic Book schema from OpenAPI #/components/schemas/Book
 */
export interface Book {
  book_id: string;
  title: string;
  isbn: string | null;
  authors: string[];
  published_year: number | null;
}

/**
 * Cursor-paginated Book page schema from OpenAPI #/components/schemas/BookPage
 */
export interface BookPage {
  items: Book[];
  next_cursor: string | null;
}

/**
 * Book creation / update schema from OpenAPI #/components/schemas/BookWrite
 */
export interface BookWrite {
  title: string;
  isbn?: string | null;
  authors: string[];
  published_year?: number | null;
}

/**
 * Supported query parameters for GET /books endpoint
 */
export interface CatalogSearchParams {
  limit?: number;
  cursor?: string | null;
  title?: string;
  isbn?: string;
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

/**
 * Physical or logical shelving location from OpenAPI #/components/schemas/Location
 */
export interface Location {
  location_id: string;
  name: string;
  code: string;
  parent_location_id: string | null;
  status: string;
}

/**
 * Location write payload from OpenAPI #/components/schemas/LocationWrite
 */
export interface LocationWrite {
  name: string;
  code: string;
  parent_location_id?: string | null;
  status?: string;
}

/**
 * Location list response from OpenAPI #/components/schemas/LocationPage
 */
export interface LocationPage {
  items: Location[];
}

/**
 * Valid physical copy statuses matching backend domain rules.
 */
export type CopyStatus =
  | 'available'
  | 'borrowed'
  | 'reserved'
  | 'lost'
  | 'damaged'
  | 'maintenance';

/**
 * Explicit permitted copy status transitions matching backend domain policy (BE-014).
 */
export const ALLOWED_STATUS_TRANSITIONS: Record<string, readonly CopyStatus[]> = {
  available: ['borrowed', 'reserved', 'maintenance', 'damaged', 'lost'],
  reserved: ['available', 'borrowed', 'maintenance', 'damaged', 'lost'],
  borrowed: ['available', 'maintenance', 'damaged', 'lost'],
  maintenance: ['available', 'damaged', 'lost'],
  damaged: ['available', 'maintenance', 'lost'],
  lost: ['available', 'maintenance', 'damaged'],
};

/**
 * Physical copy schema from OpenAPI #/components/schemas/BookCopy
 */
export interface BookCopy {
  copy_id: string;
  book_id: string;
  barcode: string;
  location_id: string;
  status: string;
  condition_code: string;
  acquired_at?: string;
}

/**
 * Physical copy list response from OpenAPI #/components/schemas/BookCopyPage
 */
export interface BookCopyPage {
  items: BookCopy[];
}

/**
 * Copy registration schema from OpenAPI #/components/schemas/BookCopyWrite
 */
export interface BookCopyWrite {
  barcode: string;
  location_id: string;
  condition_code?: string;
}

/**
 * Copy update schema from OpenAPI #/components/schemas/BookCopyUpdate
 */
export interface BookCopyUpdate {
  location_id?: string | null;
  condition_code?: string | null;
}

/**
 * Copy status transition payload from OpenAPI #/components/schemas/CopyStatusTransition
 */
export interface CopyStatusTransition {
  to_status: CopyStatus;
  reason: string;
}

/**
 * Append-only status transition record from OpenAPI #/components/schemas/CopyStatusHistoryRecord
 */
export interface CopyStatusHistoryRecord {
  history_id: string;
  copy_id: string;
  from_status: string;
  to_status: string;
  reason: string;
  actor_id: string;
  created_at: string;
}

/**
 * Status history page from OpenAPI #/components/schemas/CopyStatusHistoryPage
 */
export interface CopyStatusHistoryPage {
  items: CopyStatusHistoryRecord[];
}
