import {
  ApiClientConfig,
  RequestOptions,
  HealthStatus,
  WorkerHealthStatus,
  LoginRequest,
  AccessTokenResponse,
  AccessPrincipal,
  OrganizationSettings,
  Book,
  BookPage,
  CatalogSearchParams,
  Location,
  LocationPage,
  LocationWrite,
  BookCopy,
  BookCopyPage,
  BookCopyWrite,
  BookCopyUpdate,
  CopyStatusTransition,
  CopyStatusHistoryPage,
  Loan,
  LoanPage,
  LoanRequestWrite,
  DeskCheckoutWrite,
  LoanRejectWrite,
  LoanCheckoutWrite,
  LoanSearchParams,
  Reservation,
  ReservationPage,
  ReservationCreateWrite,
  ReservationSearchParams,
  Notification,
  NotificationListResponse,
  NotificationSearchParams,
  Department,
  DepartmentListResponse,
  DepartmentWrite,
  Semester,
  SemesterListResponse,
  SemesterWrite,
  Course,
  CourseListResponse,
  CourseWrite,
  Class,
  ClassListResponse,
  ClassWrite,
  ClassMembership,
  ClassMembershipListResponse,
  ClassMembershipWrite,
  Student,
  StudentListResponse,
  StudentWrite,
  Teacher,
  TeacherListResponse,
  TeacherWrite,
  BorrowerPolicy,
  BorrowerPolicyListResponse,
  BorrowerPolicyWrite,
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

  function patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: 'PATCH',
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

  const books = {
    list: (params?: CatalogSearchParams, options?: RequestOptions) => {
      const query = new URLSearchParams();
      if (params?.limit !== undefined && params.limit !== null) {
        query.set('limit', String(params.limit));
      }
      if (params?.cursor) {
        query.set('cursor', params.cursor);
      }
      if (params?.title) {
        query.set('title', params.title);
      }
      if (params?.isbn) {
        query.set('isbn', params.isbn);
      }
      const queryString = query.toString();
      const endpoint = queryString ? `/books?${queryString}` : '/books';
      return get<BookPage>(endpoint, options);
    },
    getById: (bookId: string, options?: RequestOptions) =>
      get<Book>(`/books/${encodeURIComponent(bookId)}`, options),
  };

  const locations = {
    list: (options?: RequestOptions) =>
      get<LocationPage>('/locations', options),
    getById: (locationId: string, options?: RequestOptions) =>
      get<Location>(`/locations/${encodeURIComponent(locationId)}`, options),
    create: (data: LocationWrite, options?: RequestOptions) =>
      post<Location>('/locations', data, options),
    update: (locationId: string, data: LocationWrite, options?: RequestOptions) =>
      patch<Location>(`/locations/${encodeURIComponent(locationId)}`, data, options),
  };

  const copies = {
    listForBook: (bookId: string, options?: RequestOptions) =>
      get<BookCopyPage>(`/books/${encodeURIComponent(bookId)}/copies`, options),
    getById: (copyId: string, options?: RequestOptions) =>
      get<BookCopy>(`/copies/${encodeURIComponent(copyId)}`, options),
    createForBook: (bookId: string, data: BookCopyWrite, options?: RequestOptions) =>
      post<BookCopy>(`/books/${encodeURIComponent(bookId)}/copies`, data, options),
    update: (copyId: string, data: BookCopyUpdate, options?: RequestOptions) =>
      patch<BookCopy>(`/copies/${encodeURIComponent(copyId)}`, data, options),
    transitionStatus: (copyId: string, transition: CopyStatusTransition, options?: RequestOptions) =>
      post<BookCopy>(`/copies/${encodeURIComponent(copyId)}/status`, transition, options),
    getHistory: (copyId: string, options?: RequestOptions) =>
      get<CopyStatusHistoryPage>(`/copies/${encodeURIComponent(copyId)}/history`, options),
  };

  const loans = {
    list: (params?: LoanSearchParams, options?: RequestOptions) => {
      const query = new URLSearchParams();
      if (params?.borrower_user_id) {
        query.set('borrower_user_id', params.borrower_user_id);
      }
      if (params?.copy_id) {
        query.set('copy_id', params.copy_id);
      }
      if (params?.status) {
        query.set('status', params.status);
      }
      const queryString = query.toString();
      const endpoint = queryString ? `/loans?${queryString}` : '/loans';
      return get<LoanPage>(endpoint, options);
    },
    getById: (loanId: string, options?: RequestOptions) =>
      get<Loan>(`/loans/${encodeURIComponent(loanId)}`, options),
    request: (data: LoanRequestWrite, options?: RequestOptions) =>
      post<Loan>('/loans', data, options),
    deskCheckout: (data: DeskCheckoutWrite, options?: RequestOptions) =>
      post<Loan>('/loans/desk-checkout', data, options),
    approve: (loanId: string, options?: RequestOptions) =>
      post<Loan>(`/loans/${encodeURIComponent(loanId)}/approve`, undefined, options),
    reject: (loanId: string, data?: LoanRejectWrite, options?: RequestOptions) =>
      post<Loan>(`/loans/${encodeURIComponent(loanId)}/reject`, data, options),
    checkout: (loanId: string, data?: LoanCheckoutWrite, options?: RequestOptions) =>
      post<Loan>(`/loans/${encodeURIComponent(loanId)}/checkout`, data, options),
    return: (loanId: string, options?: RequestOptions) =>
      post<Loan>(`/loans/${encodeURIComponent(loanId)}/return`, undefined, options),
  };

  const reservations = {
    list: (params?: ReservationSearchParams, options?: RequestOptions) => {
      const query = new URLSearchParams();
      if (params?.book_id) {
        query.set('book_id', params.book_id);
      }
      if (params?.requester_user_id) {
        query.set('requester_user_id', params.requester_user_id);
      }
      if (params?.status) {
        query.set('status', params.status);
      }
      const queryString = query.toString();
      const endpoint = queryString ? `/reservations?${queryString}` : '/reservations';
      return get<ReservationPage>(endpoint, options);
    },
    getById: (reservationId: string, options?: RequestOptions) =>
      get<Reservation>(`/reservations/${encodeURIComponent(reservationId)}`, options),
    create: (data: ReservationCreateWrite, options?: RequestOptions) =>
      post<Reservation>('/reservations', data, options),
    cancel: (reservationId: string, options?: RequestOptions) =>
      post<Reservation>(`/reservations/${encodeURIComponent(reservationId)}/cancel`, undefined, options),
    claim: (reservationId: string, options?: RequestOptions) =>
      post<Reservation>(`/reservations/${encodeURIComponent(reservationId)}/claim`, undefined, options),
  };

  const notifications = {
    list: (params?: NotificationSearchParams, options?: RequestOptions) => {
      const query = new URLSearchParams();
      if (params?.status) {
        query.set('status', params.status);
      }
      if (params?.limit !== undefined && params.limit !== null) {
        query.set('limit', String(params.limit));
      }
      const queryString = query.toString();
      const endpoint = queryString ? `/notifications?${queryString}` : '/notifications';
      return get<NotificationListResponse>(endpoint, options);
    },
    markRead: (notificationId: string, options?: RequestOptions) =>
      post<Notification>(`/notifications/${encodeURIComponent(notificationId)}/read`, undefined, options),
  };

  const education = {
    departments: {
      list: (options?: RequestOptions) =>
        get<DepartmentListResponse>('/education/departments', options),
      getById: (departmentId: string, options?: RequestOptions) =>
        get<Department>(`/education/departments/${encodeURIComponent(departmentId)}`, options),
      create: (data: DepartmentWrite, options?: RequestOptions) =>
        post<Department>('/education/departments', data, options),
    },
    semesters: {
      list: (options?: RequestOptions) =>
        get<SemesterListResponse>('/education/semesters', options),
      getById: (semesterId: string, options?: RequestOptions) =>
        get<Semester>(`/education/semesters/${encodeURIComponent(semesterId)}`, options),
      create: (data: SemesterWrite, options?: RequestOptions) =>
        post<Semester>('/education/semesters', data, options),
    },
    courses: {
      list: (options?: RequestOptions) =>
        get<CourseListResponse>('/education/courses', options),
      getById: (courseId: string, options?: RequestOptions) =>
        get<Course>(`/education/courses/${encodeURIComponent(courseId)}`, options),
      create: (data: CourseWrite, options?: RequestOptions) =>
        post<Course>('/education/courses', data, options),
    },
    classes: {
      list: (options?: RequestOptions) =>
        get<ClassListResponse>('/education/classes', options),
      getById: (classId: string, options?: RequestOptions) =>
        get<Class>(`/education/classes/${encodeURIComponent(classId)}`, options),
      create: (data: ClassWrite, options?: RequestOptions) =>
        post<Class>('/education/classes', data, options),
      listMemberships: (classId: string, options?: RequestOptions) =>
        get<ClassMembershipListResponse>(`/education/classes/${encodeURIComponent(classId)}/memberships`, options),
      createMembership: (classId: string, data: ClassMembershipWrite, options?: RequestOptions) =>
        post<ClassMembership>(`/education/classes/${encodeURIComponent(classId)}/memberships`, data, options),
    },
    students: {
      list: (options?: RequestOptions) =>
        get<StudentListResponse>('/education/students', options),
      getById: (studentId: string, options?: RequestOptions) =>
        get<Student>(`/education/students/${encodeURIComponent(studentId)}`, options),
      create: (data: StudentWrite, options?: RequestOptions) =>
        post<Student>('/education/students', data, options),
    },
    teachers: {
      list: (options?: RequestOptions) =>
        get<TeacherListResponse>('/education/teachers', options),
      getById: (teacherId: string, options?: RequestOptions) =>
        get<Teacher>(`/education/teachers/${encodeURIComponent(teacherId)}`, options),
      create: (data: TeacherWrite, options?: RequestOptions) =>
        post<Teacher>('/education/teachers', data, options),
    },
    policies: {
      list: (options?: RequestOptions) =>
        get<BorrowerPolicyListResponse>('/education/borrower-policies', options),
      getByType: (borrowerType: string, options?: RequestOptions) =>
        get<BorrowerPolicy>(`/education/borrower-policies/${encodeURIComponent(borrowerType)}`, options),
      set: (borrowerType: string, data: BorrowerPolicyWrite, options?: RequestOptions) =>
        put<BorrowerPolicy>(`/education/borrower-policies/${encodeURIComponent(borrowerType)}`, data, options),
    },
  };

  return {
    request,
    get,
    post,
    put,
    patch,
    delete: del,
    health,
    auth,
    organizations,
    books,
    locations,
    copies,
    loans,
    reservations,
    notifications,
    education,
  };
}

/**
 * Singleton API client instance with standard default configuration.
 */
export const apiClient = createApiClient();
export { ProblemDetailsError };
