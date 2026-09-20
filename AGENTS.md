# OpenLibraryOS Agent Instructions

## Project philosophy

- Giữ backend là modular monolith cho đến khi có bằng chứng vận hành yêu cầu tách service.
- Đặt business rule trong domain/application service, không đặt trong controller hoặc React component.
- Mọi dữ liệu persistent phải giữ tenant boundary bằng `organization_id`.
- Ưu tiên giải pháp đơn giản, rõ ràng, dùng standard library hoặc dependency đã có trước khi thêm abstraction.
- Không tạo tính năng ngoài task hiện tại hoặc scaffold cho một giả định chưa được xác nhận.

## Repository structure

- `backend/`: Flask API, domain/application/infrastructure layers và backend tests.
- `frontend/`: React + TypeScript SPA, typed API client và frontend tests.
- `contracts/openapi/`: versioned API contracts.
- `docs/`: architecture, security, deployment và development documentation.
- `tasks/`: executable task specifications with checkpoints.
- `infra/`: Docker Compose, Nginx và operational configuration.
- `.github/workflows/`: CI/CD workflows.

## Coding standards

- Python: type hints, small modules, explicit service boundaries, SQLAlchemy 2.x patterns.
- TypeScript: strict mode, feature-oriented modules, no direct database access.
- API: `/api/v1`, RFC Problem Details for errors, `X-Request-ID` for correlation.
- Database: SQL Server migrations are mandatory for every schema change.
- Tenant tables: `organization_id NOT NULL`, tenant-prefixed unique constraints and indexes.
- Security: parameterized queries, boundary validation, least privilege, no secrets in source.
- Comments explain why a non-obvious rule exists; they do not restate code.

## Testing requirement

Every behavior change follows red-green-refactor: write a failing test, verify the expected failure, implement the smallest change, then run the focused and full suites. Tenant isolation, authorization, state transitions and money paths require integration coverage.

## Review process

Before merge:

1. Run the relevant unit, integration, frontend and build checks.
2. Validate database migrations and OpenAPI compatibility.
3. Run delegated Open Code Review against every reviewable file.
4. Resolve all critical and high findings.
5. Record the phase checkpoint evidence in the task file.

## Completion contract

Không tuyên bố task hoàn tất nếu chưa có command output xác nhận. Khi thay đổi task scope hoặc architecture, cập nhật tài liệu trước khi cập nhật code.
