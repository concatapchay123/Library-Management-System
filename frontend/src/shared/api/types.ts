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

/**
 * Valid circulation loan statuses matching backend domain rules (BE-016).
 */
export type LoanStatus =
  | 'requested'
  | 'approved'
  | 'rejected'
  | 'checked_out'
  | 'returned'
  | 'cancelled'
  | 'overdue';

/**
 * Circulation Loan schema from OpenAPI #/components/schemas/Loan
 */
export interface Loan {
  loan_id: string;
  organization_id: string;
  copy_id: string;
  borrower_user_id: string;
  status: LoanStatus;
  loan_status?: string;
  request_status?: string;
  requested_at: string;
  approved_at?: string | null;
  checked_out_at?: string | null;
  due_at?: string | null;
  returned_at?: string | null;
  policy_snapshot?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * Paginated loans response from OpenAPI #/components/schemas/LoanPage
 */
export interface LoanPage {
  items: Loan[];
  next_cursor?: string | null;
}

/**
 * Self-service or staff loan request schema from OpenAPI #/components/schemas/LoanRequestWrite
 */
export interface LoanRequestWrite {
  copy_id: string;
  borrower_user_id?: string;
  duration_days?: number;
}

/**
 * Direct desk checkout schema from OpenAPI #/components/schemas/DeskCheckoutWrite
 */
export interface DeskCheckoutWrite {
  copy_id: string;
  borrower_user_id: string;
  duration_days?: number;
}

/**
 * Loan rejection schema from OpenAPI #/components/schemas/LoanRejectWrite
 */
export interface LoanRejectWrite {
  reason?: string;
}

/**
 * Loan checkout schema from OpenAPI #/components/schemas/LoanCheckoutWrite
 */
export interface LoanCheckoutWrite {
  duration_days?: number;
}

/**
 * Query parameters for GET /loans endpoint
 */
export interface LoanSearchParams {
  borrower_user_id?: string;
  copy_id?: string;
  status?: string;
}

/**
 * Valid reservation statuses matching backend domain rules (BE-018).
 */
export type ReservationStatus =
  | 'pending'
  | 'held'
  | 'fulfilled'
  | 'cancelled'
  | 'expired';

/**
 * Reservation schema from OpenAPI #/components/schemas/Reservation
 */
export interface Reservation {
  reservation_id: string;
  organization_id: string;
  book_id: string;
  requester_user_id: string;
  queue_position: number;
  status: ReservationStatus;
  copy_id?: string | null;
  hold_expires_at?: string | null;
  fulfilled_at?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  updated_at?: string;
}

/**
 * Paginated reservations response from OpenAPI #/components/schemas/ReservationPage
 */
export interface ReservationPage {
  items: Reservation[];
  total?: number;
}

/**
 * Reservation creation schema from OpenAPI #/components/schemas/ReservationCreateWrite
 */
export interface ReservationCreateWrite {
  book_id: string;
  copy_id?: string;
  requester_user_id?: string;
}

/**
 * Query parameters for GET /reservations endpoint
 */
export interface ReservationSearchParams {
  book_id?: string;
  requester_user_id?: string;
  status?: string;
}

/**
 * Valid notification statuses matching backend domain rules (BE-025).
 */
export type NotificationStatus = 'unread' | 'read';

/**
 * Valid notification delivery channels.
 */
export type NotificationChannel = 'in_app' | 'email';

/**
 * In-app Notification schema from OpenAPI #/components/schemas/Notification
 */
export interface Notification {
  notification_id: string;
  organization_id: string;
  user_id: string;
  channel: NotificationChannel | string;
  type: string;
  payload: Record<string, unknown>;
  status: NotificationStatus;
  read_at?: string | null;
  created_at: string;
}

/**
 * Paginated or listed in-app notifications response from OpenAPI #/components/schemas/NotificationListResponse
 */
export interface NotificationListResponse {
  items: Notification[];
  total: number;
}

/**
 * Query parameters for GET /notifications endpoint
 */
export interface NotificationSearchParams {
  status?: NotificationStatus;
  limit?: number;
}

/**
 * Education Department schema from OpenAPI #/components/schemas/Department
 */
export interface Department {
  department_id: string;
  organization_id: string;
  code: string;
  name: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DepartmentListResponse {
  items: Department[];
}

export interface DepartmentWrite {
  code: string;
  name: string;
  status?: string;
}

/**
 * Education Semester schema from OpenAPI #/components/schemas/Semester
 */
export interface Semester {
  semester_id: string;
  organization_id: string;
  name: string;
  starts_on: string;
  ends_on: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SemesterListResponse {
  items: Semester[];
}

export interface SemesterWrite {
  name: string;
  starts_on: string;
  ends_on: string;
  status?: string;
}

/**
 * Education Course schema from OpenAPI #/components/schemas/Course
 */
export interface Course {
  course_id: string;
  organization_id: string;
  code: string;
  name: string;
  department_id?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CourseListResponse {
  items: Course[];
}

export interface CourseWrite {
  code: string;
  name: string;
  department_id?: string | null;
  status?: string;
}

/**
 * Education Class schema from OpenAPI #/components/schemas/Class
 */
export interface Class {
  class_id: string;
  organization_id: string;
  code: string;
  name: string;
  semester_id: string;
  department_id?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ClassListResponse {
  items: Class[];
}

export interface ClassWrite {
  code: string;
  name: string;
  semester_id: string;
  department_id?: string | null;
  status?: string;
}

/**
 * Education Class Membership schema from OpenAPI #/components/schemas/ClassMembership
 */
export interface ClassMembership {
  membership_id: string;
  organization_id: string;
  class_id: string;
  student_id: string;
  joined_at?: string | null;
  left_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ClassMembershipListResponse {
  items: ClassMembership[];
}

export interface ClassMembershipWrite {
  student_id: string;
  joined_at?: string | null;
  left_at?: string | null;
}

/**
 * Education Student schema from OpenAPI #/components/schemas/Student
 */
export interface Student {
  student_id: string;
  organization_id: string;
  user_id: string;
  student_number: string;
  department_id?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface StudentListResponse {
  items: Student[];
}

export interface StudentWrite {
  user_id: string;
  student_number: string;
  department_id?: string | null;
  status?: string;
}

/**
 * Education Teacher schema from OpenAPI #/components/schemas/Teacher
 */
export interface Teacher {
  teacher_id: string;
  organization_id: string;
  user_id: string;
  employee_number: string;
  department_id?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TeacherListResponse {
  items: Teacher[];
}

export interface TeacherWrite {
  user_id: string;
  employee_number: string;
  department_id?: string | null;
  status?: string;
}

/**
 * Education Borrower Policy schema from OpenAPI #/components/schemas/BorrowerPolicy
 */
export interface BorrowerPolicy {
  policy_id: string;
  organization_id: string;
  borrower_type: 'student' | 'teacher' | string;
  max_active_loans: number;
  duration_days: number;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BorrowerPolicyListResponse {
  items: BorrowerPolicy[];
}

export interface BorrowerPolicyWrite {
  max_active_loans: number;
  duration_days: number;
  status?: string;
}
