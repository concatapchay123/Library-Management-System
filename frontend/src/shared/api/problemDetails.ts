import { ProblemDetails } from './types';

/**
 * Generates a compliant RFC correlation identifier.
 * Matches OpenAPI schema regex: ^[A-Za-z0-9._-]{1,128}$
 */
export function generateRequestId(): string {
  const timestamp = Date.now().toString(36);
  const randomPart = Math.random().toString(36).substring(2, 10);
  return `req-${timestamp}-${randomPart}`;
}

/**
 * Sanitizes raw error text to prevent leaking sensitive information:
 * - SQL queries and database error messages
 * - Python / Node stack traces and file paths
 * - Authentication tokens, JWT strings, and passwords
 *
 * CRITICAL ARCHITECTURAL & SECURITY INVARIANT:
 * User-facing errors must remain concise and NEVER expose internal database structure,
 * stack traces, or credentials to client interfaces.
 */
export function sanitizeErrorMessage(message: string): string {
  if (!message || typeof message !== 'string') {
    return 'An unexpected error occurred.';
  }

  // 1. Detect SQL syntax, database errors, and driver traces
  const sqlPattern =
    /(?:SELECT\s+.*?\s+FROM|INSERT\s+INTO|UPDATE\s+.*?\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|ODBC\s+Driver|pyodbc|OperationalError|ProgrammingError|sqlalchemy|sqlite3|database\s+error)/i;
  if (sqlPattern.test(message)) {
    return 'A database error occurred. Please contact support with the request ID.';
  }

  // 2. Detect stack traces and internal runtime exceptions
  const stackPattern =
    /(?:Traceback\s+\(most recent call last\)|File\s+["'].*?["'],\s+line\s+\d+|NullPointerException|at\s+[\w$.]+\s+\(|Error:\s+.*?\n\s+at)/i;
  if (stackPattern.test(message)) {
    return 'An unexpected server error occurred. Please contact support with the request ID.';
  }

  // 3. Detect sensitive credentials, token strings, and secret keys
  const tokenPattern =
    /(?:eyJ[A-Za-z0-9_-]{10,}|bearer\s+[A-Za-z0-9._-]+|password\s*[:=]\s*\S+|token\s*[:=]\s*\S+|secret[_a-z]*\s*[:=]\s*\S+)/i;
  if (tokenPattern.test(message)) {
    return 'Authentication credentials are invalid or expired.';
  }

  return message.trim();
}

/**
 * Derives a concise, helpful user action based on the HTTP status code.
 */
export function deriveHelpfulAction(status: number): string {
  switch (status) {
    case 400:
      return 'Please check your input and try again.';
    case 401:
      return 'Please sign in again to continue.';
    case 403:
      return 'You do not have permission to access this resource. Contact your library administrator.';
    case 404:
      return 'The requested resource could not be found. Check the identifier or link.';
    case 409:
      return 'A conflict occurred with the current state of this resource. Refresh and try again.';
    case 422:
      return 'One or more fields failed validation. Please correct the highlighted errors.';
    case 500:
      return 'An internal server error occurred. Please contact support with the request ID.';
    case 503:
      return 'A required service is temporarily unavailable. Please retry shortly.';
    default:
      return status >= 500
        ? 'A server error occurred. Please retry shortly or contact support.'
        : 'An error occurred while processing your request. Please review and try again.';
  }
}

/**
 * Determines whether an HTTP method is safe to retry automatically or via user button.
 * Safe methods: GET, HEAD, OPTIONS.
 * Mutating methods (POST, PUT, DELETE, PATCH) are NOT safe to retry blindly.
 */
export function isMethodSafeToRetry(method?: string): boolean {
  if (!method) return true; // Default to safe if not specified
  const upper = method.toUpperCase();
  return upper === 'GET' || upper === 'HEAD' || upper === 'OPTIONS';
}

/**
 * Typed error class wrapping normalized RFC Problem Details.
 */
export class ProblemDetailsError extends Error {
  public override readonly name = 'ProblemDetailsError';
  public readonly problem: ProblemDetails;
  public readonly requestId: string;
  public readonly status: number;
  public readonly title: string;
  public readonly detail: string;
  public readonly instance: string;
  public readonly helpfulAction: string;
  public readonly isSafeToRetry: boolean;
  public readonly errors?: Array<Record<string, unknown>>;

  constructor(params: {
    type: string;
    title: string;
    status: number;
    detail: string;
    instance: string;
    request_id: string;
    helpfulAction?: string;
    isSafeToRetry?: boolean;
    errors?: Array<Record<string, unknown>>;
  }) {
    super(params.detail);
    this.status = params.status;
    this.title = params.title;
    this.detail = params.detail;
    this.instance = params.instance;
    this.requestId = params.request_id;
    this.helpfulAction = params.helpfulAction || deriveHelpfulAction(params.status);
    this.isSafeToRetry = params.isSafeToRetry ?? true;
    this.errors = params.errors;

    this.problem = {
      type: params.type,
      title: params.title,
      status: params.status,
      detail: params.detail,
      instance: params.instance,
      request_id: params.request_id,
      errors: params.errors,
    };

    // Maintain proper prototype chain for instanceof checks
    Object.setPrototypeOf(this, ProblemDetailsError.prototype);
  }
}

/**
 * Normalizes any error response or payload into a safe, structured ProblemDetailsError.
 */
export function normalizeProblemDetails(
  raw: unknown,
  fallbackStatus = 500,
  defaultRequestId?: string,
  method?: string,
): ProblemDetailsError {
  const safeToRetry = isMethodSafeToRetry(method);
  const requestId =
    typeof raw === 'object' && raw !== null && 'request_id' in raw && typeof (raw as Record<string, unknown>).request_id === 'string'
      ? ((raw as Record<string, unknown>).request_id as string)
      : defaultRequestId || generateRequestId();

  if (typeof raw === 'object' && raw !== null) {
    const obj = raw as Record<string, unknown>;
    const status = typeof obj.status === 'number' ? obj.status : fallbackStatus;
    const rawTitle = typeof obj.title === 'string' ? obj.title : 'Request Failed';
    const rawDetail = typeof obj.detail === 'string' ? obj.detail : rawTitle;
    const instance = typeof obj.instance === 'string' ? obj.instance : '';
    const type = typeof obj.type === 'string' ? obj.type : `https://openlibraryos.example/problems/${status}`;
    const errors = Array.isArray(obj.errors) ? (obj.errors as Array<Record<string, unknown>>) : undefined;

    const sanitizedTitle = sanitizeErrorMessage(rawTitle);
    const sanitizedDetail = sanitizeErrorMessage(rawDetail);

    return new ProblemDetailsError({
      type,
      title: sanitizedTitle,
      status,
      detail: sanitizedDetail,
      instance,
      request_id: requestId,
      helpfulAction: deriveHelpfulAction(status),
      isSafeToRetry: safeToRetry,
      errors,
    });
  }

  // Handle string or unknown payloads
  const rawString = typeof raw === 'string' ? raw : 'An unexpected error occurred.';
  const sanitized = sanitizeErrorMessage(rawString);

  return new ProblemDetailsError({
    type: `https://openlibraryos.example/problems/${fallbackStatus}`,
    title: fallbackStatus >= 500 ? 'Server Error' : 'Request Error',
    status: fallbackStatus,
    detail: sanitized,
    instance: '',
    request_id: requestId,
    helpfulAction: deriveHelpfulAction(fallbackStatus),
    isSafeToRetry: safeToRetry,
  });
}
