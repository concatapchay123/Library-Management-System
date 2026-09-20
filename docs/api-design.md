# Thiết kế REST API OpenLibraryOS

## Contract

API dùng OpenAPI versioned tại `contracts/openapi/v1.yaml` từ Phase 1. Markdown này mô tả semantics và permission; contract machine-readable phải khớp trước khi merge.

Base URL: `/api/v1`.

Headers:

- `Authorization: Bearer <access-token>` cho endpoint protected.
- `X-Request-ID` để correlation; server tạo nếu client không gửi.
- `Idempotency-Key` cho checkout, return và payment.
- `Content-Type: application/json`.

## Authentication endpoints

| Method | Endpoint | Permission | Mục đích |
|---|---|---|---|
| POST | `/auth/login` | Public | Xác thực email/password và cấp access token + refresh cookie. |
| POST | `/auth/refresh` | Refresh cookie + CSRF | Rotate refresh session và cấp access token mới. |
| POST | `/auth/logout` | Authenticated + CSRF | Revoke refresh session chain hiện tại. |
| GET | `/auth/me` | Authenticated | Trả principal, organization và permissions hiệu lực. |
| POST | `/auth/password/change` | Authenticated | Đổi password và revoke sessions khác. |

## Core endpoints

| Resource | Endpoints chính | Permission mẫu |
|---|---|---|
| Organizations | `GET/PATCH /organizations/me`, `GET/PATCH /organizations/settings` | `organization.read`, `organization.manage` |
| Users/RBAC | `GET/POST/PATCH /users`, `/roles`, `/permissions`, `/user-roles` | `user.manage`, `role.manage` |
| Books | `GET/POST/PATCH /books`, `GET/POST/PATCH /books/{book_id}/copies` | `catalog.read`, `catalog.manage` |
| Locations | `GET/POST/PATCH /locations` | `inventory.manage` |
| Inventory | `POST /copies/{copy_id}/status` | `inventory.manage` |
| Loans | `GET/POST /loans`, `POST /loans/{loan_id}/approve`, `POST /loans/{loan_id}/checkout`, `POST /loans/{loan_id}/return` | `circulation.request`, `circulation.approve`, `circulation.checkout`, `circulation.return` |
| Reservations | `GET/POST /reservations`, `POST /reservations/{id}/cancel` | `reservation.create`, `reservation.manage` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read` | `notification.read` |
| Audit | `GET /audit-events` | `audit.read` |

## Extension endpoints

Education dùng `/education/students`, `/education/teachers`, `/education/departments`, `/education/classes`, `/education/courses`, `/education/semesters` và `/education/policies`. Public library dùng `/public-library/members`, `/membership-plans`, `/subscriptions`, `/fines`, `/payments`, `/invoices`.

Extension endpoint không được expose nếu edition/module chưa được enable cho organization.

## Response rules

Resource response trả JSON object với field names ổn định, ISO-8601 UTC timestamps và UUID string. List response dùng:

```json
{
  "items": [],
  "next_cursor": "opaque-token-or-null"
}
```

Validation hoặc domain failure dùng RFC Problem Details:

```json
{
  "type": "https://openlibraryos.example/problems/loan-not-eligible",
  "title": "Loan request rejected",
  "status": 409,
  "detail": "The borrower has reached the active loan limit.",
  "instance": "/api/v1/loans",
  "request_id": "uuid",
  "errors": []
}
```

Không trả stack trace, SQL text, password state hoặc token trong response.

## Authorization rules

- Authentication middleware xác định user và organization.
- Endpoint permission là necessary nhưng không sufficient; service kiểm tra resource ownership và business policy.
- Client không được chọn tenant bằng body field.
- Librarian direct checkout dùng cùng service với self-service checkout.
- Audit read chỉ cho role có permission `audit.read`; audit response loại bỏ secret field.

## Pagination and filtering

List endpoints bắt buộc giới hạn page size server-side. Cursor encode sort key + stable id, không chứa raw tenant data. Sort/filter field được allow-list; không nối trực tiếp query string vào SQL.

## Compatibility

Breaking response/request changes tạo `/api/v2`. Additive fields phải optional trước, rồi mới trở thành required sau deprecation window. OpenAPI diff trong CI chặn breaking change nếu không có version bump và migration note.
