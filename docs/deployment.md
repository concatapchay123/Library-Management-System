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

- SQL Server full/differential/log backup theo RPO đã cấu hình.
- Redis không phải source of truth cho business data; có thể recreate queue.
- Backup encryption key được quản lý ngoài database host.
- Restore drill phải tạo environment tách biệt, restore database, replay migration check và chạy RLS smoke tests.

## Rollback

Rollback ưu tiên deploy image trước đó nếu migration backward-compatible. Migration destructive chỉ được thực hiện sau contract phase và retention window. Nếu migration không thể rollback, release phải có forward-fix script và runbook được review trước.

## Operations

- Health endpoints: `/health/live`, `/health/ready`.
- Logs: JSON, request id, organization id, actor id, event name, duration.
- Alerts: API 5xx, readiness failure, DB pool saturation, queue backlog, failed jobs, disk/backup failure và repeated RLS denial.
- Nginx chặn access trực tiếp tới database/Redis.
- Worker concurrency và retry limit được cấu hình theo deployment size, không hard-code theo local machine.
