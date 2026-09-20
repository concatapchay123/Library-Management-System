# Chiến lược kiểm thử OpenLibraryOS

## Test pyramid

### Unit

Không cần database hoặc Flask. Test domain entity, policy resolver, loan transitions, active loan limits, reservation ordering, money calculation và permission decisions.

### Integration

Chạy SQL Server và Redis thật trong test environment. Test repository, migration, transaction rollback, RLS predicates, `SESSION_CONTEXT`, connection pool reuse, Celery job idempotency và email adapter boundary.

### API

Chạy Flask app với test database. Test authentication, refresh rotation, CSRF, authorization matrix, validation, problem details, cursor pagination, request correlation và idempotency replay.

### End-to-end

Chọn các flow có giá trị cao: login → catalog search → loan request → approval → checkout → return; reservation allocation; public fine/payment; student/teacher policy.

### Frontend

Test route protection, auth refresh failure, typed API error rendering, catalog filtering, checkout/return critical screens và accessibility baseline.

## Mandatory security cases

1. Tenant A không đọc, sửa hoặc xóa row Tenant B.
2. Insert/update với tenant id giả bị SQL Server block.
3. Reused connection không giữ session context cũ.
4. User không có permission không gọi được protected endpoint.
5. Refresh token cũ bị reject sau rotation.
6. CSRF thiếu hoặc sai bị reject.
7. Checkout/return/payment retry cùng idempotency key không duplicate side effect.
8. Password/token/payment credential không xuất hiện trong response hoặc log.

## CI gates

- Backend formatting/lint/type check.
- Backend unit và API suites.
- SQL Server migration/integration suite.
- Frontend lint, type check, unit và production build.
- OpenAPI lint và breaking-change check.
- Docker Compose config validation.
- Dependency and secret scanning.

## Test data

Fixture luôn tạo ít nhất hai organization, user/role cho mỗi organization, copies dùng chung một book title và các trạng thái inventory khác nhau. Đây là điều kiện để mọi tenant test có ý nghĩa.

## Failure handling

Flaky test không được retry vô hạn để che lỗi. Test thất bại phải được phân loại code, environment hoặc test defect; bug production phải có regression test trước fix.
