# Deployment OpenLibraryOS

## Local Compose services

| Service | Vai trò | Persistent data |
|---|---|---|
| `app` | Flask API | Không |
| `worker` | Celery worker | Không |
| `database` | SQL Server | Named volume hoặc external volume |
| `redis` | Queue, rate limit, short-lived state | Named volume khi cần |
| `nginx` | TLS/reverse proxy/static frontend | Certificate mount |

Frontend production build được phục vụ bởi Nginx. API proxy giữ `/api/` cùng origin để đơn giản hóa cookie, CSRF và CORS.

## Environment strategy

`.env.example` liệt kê tên biến bắt buộc, không chứa secret thật. Các nhóm biến:

- `APP_ENV`, `SECRET_KEY`, `JWT_SIGNING_KEY`.
- SQL Server host, port, database, user, password và encryption mode.
- Redis URL và Celery queue names.
- Cookie domain, SameSite, secure flag và allowed origins.
- Email provider adapter và sender identity.
- Rate limits, log level và feature flags.

Mỗi environment có secret store riêng. Production không dùng default credential hoặc development signing key.

## Startup and migrations

1. Pull image với immutable tag/digest.
2. Validate environment và secret presence.
3. Run migration job once with deployment identity.
4. Start app/worker mới.
5. Wait for readiness, then route traffic.
6. Confirm migration version and health metrics.

App container không tự chạy migration trên mọi replica startup; deployment orchestrator chịu trách nhiệm migration lock và one-time execution.

## Backup and restore

- Default self-hosted target là availability 99.5% mỗi tháng, RPO không quá 15 phút và RTO không quá 4 giờ. Môi trường có mục tiêu khác phải ghi giá trị chặt hơn hoặc lý do/owner chấp thuận trong release manifest.
- SQL Server full backup hằng tuần, differential hằng ngày, transaction-log backup mỗi 15 phút; backup mã hóa được giữ ít nhất 35 ngày.
- Redis không phải source of truth cho business data; có thể recreate queue.
- Backup encryption key được quản lý ngoài database host.
- Restore drill tối thiểu mỗi quý, có operational owner, tạo environment tách biệt, restore database, replay migration check và chạy RLS smoke tests. Chỉ đạt khi database usable, migration version khớp và RLS test pass.

## Rollback

Rollback ưu tiên deploy image trước đó nếu migration backward-compatible. Migration destructive chỉ được thực hiện sau contract phase và retention window. Nếu migration không thể rollback, release phải có forward-fix script và runbook được review trước.

## Operations

- Health endpoints: `/health/live`, `/health/ready`.
- Logs: JSON, request id, organization id, actor id, event name, duration.
- Alerts: page khi backup failure, restore drill quá hạn, readiness failure, API 5xx vượt 2% trong 5 phút hoặc p95 vượt hai lần baseline trong 15 phút. DB pool saturation, queue backlog/dead-letter, disk failure và repeated RLS denial phải có threshold, runbook và owner.
- Nginx chặn access trực tiếp tới database/Redis.
- Worker concurrency và retry limit được cấu hình theo deployment size, không hard-code theo local machine.

## Database identities

Migration job dùng identity tách khỏi runtime app. Runtime identity không có `db_owner`, DDL, `CONTROL`, `IMPERSONATE` hoặc quyền thay đổi RLS policy; migration identity không được cấp cho app/worker container. Deployment smoke test phải xác minh grants này, RLS catalog coverage và việc app không dùng credential migration.
