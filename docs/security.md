# Security plan OpenLibraryOS

## Identity and sessions

- Access JWT chỉ chấp nhận `RS256`, có `kid`, `iss`, `aud`, `sub`, `organization_id`, `session_id`, `iat`, `nbf`, `exp` và token version. Verifier allow-list algorithm/issuer/audience; không chấp nhận `none` hoặc algorithm khác.
- Private signing key chỉ ở secret manager. Rotation tạo key mới, giữ public key cũ tới khi access token cuối cùng hết hạn và ghi audit event; runtime không tự tạo key.
- Login bắt buộc `organization_slug` để chọn tenant kiểm tra credential. Slug sai, tenant disabled và password sai trả cùng lỗi generic để không lộ account/tenant tồn tại.
- Login resolver chạy dummy Argon verification khi slug không tồn tại/disabled. Refresh token được resolve trước context duy nhất qua stored procedure hẹp nhận token hash; raw pre-context query vào tenant tables không được cấp cho runtime.

- Password hash dùng Argon2id với cost được benchmark trên deployment target.
- Access JWT ngắn hạn chỉ chứa `iss`, `aud`, `sub`, `organization_id`, `session_id`, `iat`, `nbf`, `exp`, token version và header `kid`; không chứa permission snapshot dài hoặc profile data.
- Refresh token chỉ lưu hash, rotation chain và revoke timestamp trong `core.refresh_sessions`.
- Refresh token nằm trong cookie `Secure`, `HttpOnly`, `SameSite=Strict`, path `/api/v1/auth`; plaintext không vào database, audit, log hay response JSON.
- `csrf_token` là cookie `Secure`, `SameSite=Strict` có thể đọc bởi SPA; refresh/logout bắt buộc header `X-CSRF-Token` khớp hash CSRF của session trước khi mutation.
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

Runtime SQL identity không là `db_owner` và không có DDL, `CONTROL`, `IMPERSONATE`, `ALTER ANY SECURITY POLICY` hoặc quyền thay đổi RLS predicate. Migration/platform identity tách biệt có các quyền đó theo deployment job; CI xác minh quyền và system catalog trước release.

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
- Limiter Redis fail-closed cho login, refresh, password change và payment webhook: backend limiter lỗi trả `503` Problem Details generic. Endpoint khác chỉ được fail-open khi deployment policy có edge limiter bù và metric `rate_limit_backend_unavailable`.
- Idempotency record có TTL 24 giờ, gắn với tenant/method/endpoint/canonical request hash, lưu resource reference hoặc representation allow-list đã mã hóa; không lưu token, raw card, raw webhook hoặc secret.

## Payment webhook và privacy

- Webhook xác thực signature trên raw body trước parse, kiểm tra replay timestamp tối đa 5 phút và deduplicate `(organization_id, provider, provider_event_id)`.
- Payment timeout để trạng thái `pending`; reconciliation job xác minh provider trước khi kết luận, và partial/refund có allocation record cùng audit trail.
- PII được phân loại, trả theo permission tối thiểu và không đưa vào log/audit nếu không cần. Profile/account deactive trước; anonymization/deletion tuân retention policy được tenant operator phê duyệt, legal hold và audit.
- Release production phải ghi policy owner, jurisdiction và thời hạn retention cho profile, audit, payment, log. Không có các giá trị đó thì deployment bị chặn. Loan, payment và audit history không hard-delete.

## Secrets and data handling

- Secret chỉ qua environment/secret manager; `.env.example` chỉ chứa tên biến và safe sample.
- Không log password, access token, refresh token, payment credential hoặc full PII.
- Payment adapter chỉ lưu provider reference, amount, currency và trạng thái; không lưu card data.
- Backup được encrypt, access controlled và kiểm tra restore định kỳ.

## Security verification

Mỗi release kiểm tra dependency audit, secret scan, authentication abuse, CSRF, RLS cross-tenant, authorization matrix, migration safety và OWASP-relevant API cases. Critical/high findings phải được xử lý trước release.
