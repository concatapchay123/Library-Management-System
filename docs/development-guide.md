# Hướng dẫn phát triển OpenLibraryOS

## Prerequisites

- Python 3.11 hoặc mới hơn.
- Node.js LTS tương thích với frontend toolchain.
- Docker Desktop và Docker Compose.
- SQL Server chạy bằng Compose hoặc một instance development riêng.
- Git.

## Development flow

1. Chọn `TASK-*` và đọc dependency/checkpoint.
2. Tạo branch ngắn theo task.
3. Viết failing test cho behavior đầu tiên.
4. Implement code tối thiểu qua đúng layer.
5. Chạy focused tests, full tests, lint và type checks.
6. Cập nhật migration/OpenAPI/docs nếu interface thay đổi.
7. Chạy security checklist và delegated code review.
8. Ghi evidence vào task checkpoint rồi mở pull request.

## Backend conventions

- App factory không tạo global mutable request state.
- Flask extension được khởi tạo một lần và bind trong factory.
- Route module mỏng; use case nằm trong application service.
- Repository query luôn áp dụng tenant context và không nhận raw tenant id từ client.
- Transaction boundary nằm ở application service hoặc unit-of-work adapter.
- Domain error map sang stable problem type/status ở API layer.

## Frontend conventions

- TypeScript strict mode.
- API client được generate hoặc cập nhật từ OpenAPI contract.
- Auth state không lưu token trong localStorage.
- Route guard chỉ cải thiện UX; backend vẫn là authorization authority.
- Feature module không import internal state của feature khác.

## Database workflow

- Mỗi schema change có migration và integration test.
- Migration phải thể hiện organization foreign key, composite tenant foreign key, tenant-first index và cả RLS filter/block policy; system-catalog integration test phải fail nếu thiếu một thành phần.
- Seed permission/role là idempotent và tenant-aware.
- Không sửa database thủ công rồi coi đó là migration.

Mỗi mutation có audit row trong cùng transaction; nếu tạo side effect bất đồng bộ thì cùng transaction phải thêm versioned outbox event. Runtime database credential không chạy migration hoặc có quyền đổi RLS policy.

## Documentation workflow

Thay đổi public API cập nhật `docs/api-design.md` và OpenAPI. Thay đổi module boundary cập nhật `docs/architecture.md`/`docs/system-design.md`. Thay đổi data model cập nhật `docs/database-design.md` và migration plan. Mỗi task file phải giữ checkpoint evidence sau khi task hoàn tất.
