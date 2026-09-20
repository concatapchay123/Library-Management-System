# Security plan OpenLibraryOS

## Identity and sessions

- Password hash dùng Argon2id với cost được benchmark trên deployment target.
- Access JWT ngắn hạn, chỉ chứa `sub`, `organization_id`, `session_id`, issued-at, expiry và token version; không chứa permission snapshot dài.
- Refresh token chỉ lưu hash, rotation chain và revoke timestamp trong `core.refresh_sessions`.
- Refresh token nằm trong Secure HttpOnly cookie với SameSite policy phù hợp deployment.
- Refresh/logout yêu cầu CSRF token header và kiểm tra Origin/Referer khi có thể.
- Đăng nhập lỗi trả thông báo chung, không phân biệt email tồn tại.
- Đổi password revoke các refresh sessions khác và ghi audit event.

## Authorization

RBAC là dữ liệu tenant-scoped, gồm role, permission, role-permission và user-role. Controller chỉ chuyển principal tới application service; service kiểm tra permission và resource ownership. Không dùng tên role hard-code làm authorization rule.

Các operation platform-level như bootstrap tenant phải có privileged command path, secret riêng, explicit audit và không được route qua user request bình thường.

## Tenant isolation

Defense in depth gồm:

1. Principal xác định duy nhất organization.
2. Service không chấp nhận tenant id do client tự chọn.
3. SQLAlchemy session đặt `SESSION_CONTEXT` trong transaction.
4. SQL Server RLS filter/block predicates chặn đọc và ghi cross-tenant.
5. Tenant integration tests chạy trên SQL Server thật.
6. Audit ghi organization, actor, request id và entity.

Tenant middleware là code duy nhất được phép set session context; không expose generic setter cho request handler, worker payload hoặc client input. Khi context cleanup thất bại, connection bị invalidate thay vì quay lại pool.

Connection pool reset là security requirement. Nếu reset thất bại, connection phải bị invalidate thay vì quay lại pool.

## Input and transport

- Pydantic schema validate type, format, length và enum ở API boundary.
- ORM/parameterized SQL ngăn SQL injection; không hỗ trợ raw SQL từ request.
- CORS allow-list theo deployment config, không dùng wildcard cùng credentials.
- Nginx bật TLS, HSTS khi TLS đã ổn định, CSP, X-Content-Type-Options, Referrer-Policy và frame protection.
- Upload hoặc external URL feature chưa thuộc v1; không nhận file/URL nếu chưa có threat model.

## Abuse controls

- Redis-backed rate limit cho login, refresh, password change và public endpoints.
- Account lockout/risk response không được tạo denial-of-service dễ bị lạm dụng; dùng progressive delay và audit.
- Request body, page size, search length và cursor size có giới hạn.
- Idempotency record không lưu token hoặc raw card data.

## Secrets and data handling

- Secret chỉ qua environment/secret manager; `.env.example` chỉ chứa tên biến và safe sample.
- Không log password, access token, refresh token, payment credential hoặc full PII.
- Payment adapter chỉ lưu provider reference, amount, currency và trạng thái; không lưu card data.
- Backup được encrypt, access controlled và kiểm tra restore định kỳ.

## Security verification

Mỗi release kiểm tra dependency audit, secret scan, authentication abuse, CSRF, RLS cross-tenant, authorization matrix, migration safety và OWASP-relevant API cases. Critical/high findings phải được xử lý trước release.
