# Thiết kế REST API OpenLibraryOS

## Contract

API dùng OpenAPI versioned tại `contracts/openapi/v1.yaml` từ Phase 1. Markdown này mô tả semantics và permission; contract machine-readable phải khớp trước khi merge.

Base URL: `/api/v1`.

Headers:

- `Authorization: Bearer <access-token>` cho endpoint protected.
- `X-Request-ID` để correlation; server tạo nếu client không gửi. Client value chỉ được giữ khi khớp `[A-Za-z0-9._-]{1,128}`, nếu không server thay bằng UUID mới.
- `Idempotency-Key` cho checkout, return và payment.
- `Content-Type: application/json`.

## Authentication endpoints

Request login có shape sau; `organization_slug` chỉ hợp lệ tại public login và không được dùng làm tenant selector sau khi token đã được cấp:

```json
{
  "organization_slug": "library-campus-a",
  "email": "librarian@example.test",
  "password": "user-secret"
}
```

Slug không tồn tại, organization disabled và password sai phải trả cùng generic authentication Problem Details. Sau login, middleware chỉ lấy tenant từ JWT đã verify; client không được gửi `organization_id` hay slug ở protected route.

| Method | Endpoint | Permission | Mục đích |
|---|---|---|---|
| POST | `/auth/login` | Public | Resolve `organization_slug` và xác thực email/password. BE-007 chỉ trả trạng thái xác thực; BE-008 thêm access token và BE-009 thêm refresh cookie. |
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

## API vs SPA Surface Classification Matrix (FE/BE Parity Classification)

Theo kiến trúc và mục tiêu vận hành của hệ thống, các endpoint V1 được phân loại rõ ràng giữa luồng tương tác trực tiếp trên Single Page Application (SPA), luồng quản trị hồ sơ người dùng (Operator Profile), và các endpoint quản trị/headless API dành riêng cho tích hợp bên thứ ba, background automation, webhooks hoặc admin tooling:

| Module / Nhóm Resource | HTTP Method & Path | Phân loại Surface | Phạm vi và Kênh tương tác |
|---|---|---|---|
| **Authentication** | `POST /auth/login` | SPA Interactive Flow | Giao diện Đăng nhập chính (`LoginForm.tsx`), xác thực đa tenant |
| | `POST /auth/refresh` | SPA Background Flow | Phiên làm việc nền tự động refresh token (`App.tsx`, `SessionProvider.tsx`) |
| | `POST /auth/logout` | SPA Interactive Flow | Nút Đăng xuất trên `AppHeader.tsx`, thu hồi refresh token cookie |
| | `GET /auth/me` | SPA Interactive Flow | Khởi tạo thông tin người dùng và quyền hạn hiện tại |
| | `POST /auth/password/change` | Operator Profile Flow | Modal Đổi mật khẩu của thủ thư/nhân viên (`ChangePasswordModal.tsx`) |
| **Catalog & Works** | `GET /books` | SPA Interactive Flow | Tra cứu tìm kiếm tác phẩm/sách (`CatalogSearch.tsx`) |
| | `GET /books/{id}` | SPA Interactive Flow | Chi tiết tác phẩm và nạp ngữ cảnh vào kho (`InventoryWorkspace.tsx`) |
| | `POST /books` | Admin / API-Only Flow | Nạp danh mục thư mục hàng loạt từ hệ thống dữ liệu quốc gia/MARC21 |
| | `PATCH /books/{id}` | Admin / API-Only Flow | Cập nhật siêu dữ liệu tác phẩm thông qua quản trị viên hệ thống |
| | `GET /books/{id}/copies` | SPA Interactive Flow | Hiển thị danh sách bản sao vật lý trên kệ (`InventoryWorkspace.tsx`) |
| | `POST /books/{id}/copies` | SPA Interactive Flow | Biểu mẫu đăng ký bản sao vật lý mới (`CopyRegistrationForm.tsx`) |
| **Locations & Inventory** | `GET /locations` | SPA Interactive Flow | Nạp danh mục vị trí kệ sách (`InventoryWorkspace.tsx`) |
| | `POST /locations` | Admin / API-Only Flow | Thiết lập sơ đồ kệ/kho ban đầu qua công cụ quản trị chi nhánh |
| | `PATCH /locations/{id}` | Admin / API-Only Flow | Tái cơ cấu sơ đồ kho sách |
| | `PATCH /copies/{id}` | SPA Interactive Flow | Gán lại vị trí kệ và cập nhật tình trạng vật lý (`LocationAssignmentForm.tsx`) |
| | `POST /copies/{id}/status` | SPA Interactive Flow | Chuyển đổi trạng thái bản sao vật lý có server validation (`CopyStatusControls.tsx`) |
| | `GET /copies/{id}/history` | SPA Interactive Flow | Lịch sử vết trạng thái bản sao vật lý (`StatusHistoryView.tsx`) |
| **Circulation** | `POST /loans` | SPA Interactive Flow | Đăng ký yêu cầu mượn trực tiếp/trực tuyến (`LoanRequestPanel.tsx`) |
| | `POST /loans/checkout` | SPA Interactive Flow | Thủ thư cho mượn tại quầy trực tiếp (`DeskCheckoutPanel.tsx`) |
| | `GET /loans/{id}` | SPA Interactive Flow | Tra cứu hồ sơ mượn theo mã UUID (`CirculationDesk.tsx`) |
| | `POST /loans/{id}/approve` | SPA Interactive Flow | Phê duyệt yêu cầu mượn (`LoanLifecycleActions.tsx`) |
| | `POST /loans/{id}/checkout` | SPA Interactive Flow | Thực hiện checkout cho yêu cầu đã duyệt (`LoanLifecycleActions.tsx`) |
| | `POST /loans/{id}/return` | SPA Interactive Flow | Ghi nhận trả sách tại quầy lưu thông (`LoanLifecycleActions.tsx`) |
| **Reservations** | `GET /reservations` | SPA Interactive Flow | Hàng đợi đặt trước và tình trạng giữ sách (`ReservationInbox.tsx`) |
| | `POST /reservations` | SPA Interactive Flow | Đặt trước sách khi toàn bộ bản sao đang được mượn |
| | `POST /reservations/{id}/cancel` | SPA Interactive Flow | Người dùng hủy yêu cầu đặt trước (`ReservationStatusCard.tsx`) |
| | `POST /reservations/{id}/claim` | Admin / API-Only Flow | Tự động hóa giữ chỗ hoặc phân bổ theo lịch hẹn từ bot tự phục vụ |
| **Notifications** | `GET /notifications` | SPA Interactive Flow | Hộp thư thông báo nhạy cảm về thời gian (`ReservationInbox.tsx`) |
| | `POST /notifications/{id}/read` | SPA Interactive Flow | Đánh dấu đã đọc thông báo (`NotificationCard.tsx`) |
| **Education Extension** | `GET /education/students` | SPA Interactive Flow | Danh sách sinh viên và hạn mức (`EducationWorkspace.tsx`) |
| | `GET /education/teachers` | SPA Interactive Flow | Danh sách giảng viên và chính sách (`EducationWorkspace.tsx`) |
| | `GET /education/policies` | SPA Interactive Flow | Tra cứu chính sách mượn theo khối học viện |
| | `POST/PATCH /education/*` | Admin / SIS Integration | Tích hợp đồng bộ tự động từ hệ thống quản lý đào tạo trường học (SIS) |
| **Public Library Extension**| `GET /public-library/members` | SPA Interactive Flow | Quản lý độc giả công cộng (`MembershipsView.tsx`) |
| | `GET/POST /public-library/members` | SPA Interactive Flow | Đăng ký thẻ độc giả công cộng mới |
| | `GET /public-library/membership-plans` | SPA Interactive Flow | Xem danh sách các gói hội viên (`MembershipsView.tsx`) |
| | `POST /public-library/membership-plans` | SPA Interactive Flow | Tạo gói hội viên mới |
| | `PUT /public-library/membership-plans/{id}` | SPA Interactive Flow | Cập nhật gói hội viên (`MembershipsView.tsx`, FE-010) |
| | `GET /public-library/subscriptions` | SPA Interactive Flow | Theo dõi kỳ hạn thuê bao độc giả (`MembershipsView.tsx`) |
| | `GET /public-library/fines` | SPA Interactive Flow | Bảng kê phạt trễ hạn / hư hại (`FinesView.tsx`) |
| | `POST /public-library/fines/{id}/waive` | SPA Interactive Flow | Miễn giảm tiền phạt có ghi nhận lý do (`FinesView.tsx`) |
| | `GET /public-library/invoices` | SPA Interactive Flow | Bảng kê hóa đơn phát hành (`InvoicesView.tsx`) |
| | `POST /public-library/invoices/{id}/void` | SPA Interactive Flow | Hủy bỏ hóa đơn chưa quyết toán (`InvoicesView.tsx`) |
| | `POST /public-library/invoices` | Admin / Billing Batch | Phát hành hóa đơn định kỳ tự động hóa từ billing engine |
| | `PATCH /public-library/invoices/{id}` | Admin / API-Only Flow | Điều chỉnh hóa đơn tiền kỳ trước khi phát hành |
| | `GET /public-library/payments` | SPA Interactive Flow | Tra cứu nhật ký giao dịch thanh toán (`PaymentsView.tsx`) |
| | `POST /public-library/payments/{id}/reconcile` | SPA Interactive Flow | Đối soát giao dịch treo với cổng thanh toán (`PaymentsView.tsx`) |
| | `POST /public-library/payments/webhooks/{provider}` | Webhook Headless Flow | Tiếp nhận thông báo tức thời từ cổng thanh toán (MoMo/VNPAY/Stripe) |
| **Audit & Settings** | `GET /audit-events` | Admin / Audit Flow | Tra cứu vết kiểm toán tuân thủ dành cho kiểm toán viên |
| | `GET/PATCH /organizations/settings` | Admin / API-Only Flow | Cấu hình tham số tổ chức multi-tenant qua Admin portal |

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

`POST /auth/login` là contract mới của V1 trước khi public release; contract YAML phải đánh dấu `organization_slug` required. Mọi thay đổi về token claim, webhook verification, idempotency TTL hoặc retention representation là security-compatible change cần migration note và test matrix cập nhật.
