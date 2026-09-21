# Thiết kế hệ thống OpenLibraryOS

## Runtime topology

```text
Client browser
    │ HTTPS
    ▼
Nginx
    ├── React static assets
    └── Flask API
            ├── SQL Server
            ├── Redis
            └── Celery worker ──► Email provider
```

Docker Compose local/self-hosted chạy các service `app`, `worker`, `database`, `redis` và `nginx`. Production có thể thay từng container bằng scheduler/orchestrator tương thích, nhưng không thay đổi application contracts.

## Application services

Các use case chính:

- `AuthenticateUser`, `RefreshSession`, `RevokeSession`.
- `CreateOrganization`, `InviteUser`, `AssignRole`.
- `CreateBook`, `RegisterBookCopy`, `ChangeCopyStatus`.
- `RequestLoan`, `ApproveLoan`, `CheckoutCopy`, `ReturnCopy`.
- `PlaceReservation`, `AllocateReservation`, `ExpireReservationHold`.
- `CreateEducationBorrowerPolicy`, `CreateMembershipPlan`, `RecordPayment`.
- `CreateNotification`, `ProcessNotificationJob`, `WriteAuditEvent`.

Mỗi use case có input command rõ ràng, trả result hoặc domain error, và được test mà không cần Flask.

## Borrowing flow

### Self-service

1. Borrower gửi loan request cho một book.
2. Service kiểm tra active loan count, policy limit, copy availability và existing reservation.
3. Request ở trạng thái `requested`.
4. Librarian hoặc policy engine approve/reject.
5. Khi copy được giao, service khóa copy và loan row trong cùng transaction rồi chuyển sang `checked_out`.

### Desk checkout

Librarian có permission `circulation.checkout` tạo loan đã `approved`, kiểm tra barcode/copy status và chuyển trực tiếp sang `checked_out`. Cả hai flow đều đi qua cùng `CheckoutCopy` service.

### Return

Return khóa loan và copy, ghi `returned_at`, tính overdue/fine theo policy snapshot, cập nhật copy status và phát event cho reservation allocator. Không có background race nào được phép tạo hai active loans cho cùng copy.

## Reservation allocation

Reservation queue được partition theo organization và book. Transaction return hoặc inventory availability ghi allocation outbox event. Dispatcher/worker claim người đầu tiên bằng row lock/lease, tạo hold expiry và notification. Job retry không tạo duplicate hold vì allocation có idempotency key `(organization_id, reservation_id, event_id)`.

## Audit và transactional outbox

Mọi mutation nghiệp vụ ghi `ops.audit_events` trong cùng transaction với state change. Audit và outbox mang `payload_version` cùng `correlation_id`; `organization_id` được SQL Server lấy từ tenant session context thay vì payload của caller. Audit payload dùng allow-list field, không chứa secret/token/password/raw payment credential và runtime database identity không được update/delete audit event.

Nếu mutation tạo notification, reservation allocation, overdue work, email, payment reconciliation hoặc side effect khác, transaction ghi thêm `ops.outbox_events`. Dispatcher pre-context chỉ gọi `ops.claim_outbox_event` để claim lease nguyên tử và nhận server-created organization id, sau đó mới set context, tạo hoặc đánh thức `ops.job_records`, rồi chỉ đánh dấu event delivered khi consumer xác nhận. Consumer ghi deduplication key trước side effect; retry bounded exponential backoff và dead-letter có metric/runbook. Vì event đã durable trước commit, transaction không phụ thuộc Celery/Redis/email provider đang sẵn sàng.

Reservation allocation dùng outbox event có idempotency key `(organization_id, reservation_id, event_id)`. Lease hết hạn chỉ cho phép worker khác claim lại event chưa delivered; không được tạo hold thứ hai hoặc nhảy queue.

## Payment lifecycle

Payment bắt đầu ở trạng thái `pending` và chỉ chuyển qua state machine đã công bố: `authorized`, `succeeded`, `failed`, `refunded`, `partially_refunded`, `disputed`. Provider webhook được xác thực chữ ký trên raw body, timestamp/replay window và provider event id trước khi ghi mutation. Timeout provider không tự đồng nghĩa thất bại; outbox job reconciliation xác minh payment pending. Partial payment/refund ghi allocation bất biến với fine và audit event, nên không cần đưa accounting engine vào Core.

## Tenant context và connection pool

Application không nhận `organization_id` đáng tin cậy từ request body. Tenant được lấy từ JWT principal. Mỗi transaction chạy:

```sql
EXEC sys.sp_set_session_context
    @key = N'organization_id',
    @value = @organization_id;
```

RLS filter predicate chặn row khác tenant; block predicate chặn insert/update sai tenant. Khi transaction kết thúc, context được reset trước khi connection trở về pool. Integration test bắt buộc mô phỏng reuse cùng connection cho hai tenant.

Tenant context setter chỉ nằm trong infrastructure middleware. Worker phải lấy organization context từ một job record đã được server tạo, không nhận tenant context tùy ý từ client.

## Policy snapshot

Loan lưu `max_days_at_checkout`, `borrower_type_at_checkout` và `due_at`. Membership plan hoặc education policy thay đổi sau checkout không được thay đổi lịch sử của loan đang hoạt động.

## Background processing

Celery chỉ xử lý công việc có thể retry: dispatcher/outbox delivery, email, notification delivery, overdue marking, reservation hold expiry, payment reconciliation và invoice side effects. Mỗi job có payload version, retry limit, exponential backoff, deduplication key và failure visibility. Business transaction chính không phụ thuộc vào email provider.

## Reliability and observability

- `/health/live` chỉ kiểm tra process.
- `/health/ready` kiểm tra SQL Server và Redis connectivity.
- Structured JSON logs chứa request id, organization id, actor id, use case và latency.
- Metrics tối thiểu: request latency/error rate, DB pool exhaustion, queue depth, failed jobs, active loans và RLS denial count.
- Audit không được dùng làm log debug; secrets, token và password tuyệt đối không xuất hiện trong cả hai.
