# OpenLibraryOS Coding Rules

## Architecture

1. Controller/route chỉ parse request, gọi application service và serialize response.
2. Domain không import Flask, SQLAlchemy session, Redis hoặc Celery.
3. Application service điều phối use case và transaction boundary.
4. Infrastructure triển khai persistence, queue, email và external adapters.
5. Core không import `education` hoặc `public_library`.
6. Không bypass service layer từ API, worker hoặc CLI.

## Database and tenancy

1. Mọi persistent table có `organization_id NOT NULL`.
2. Mọi tenant-scoped unique constraint/index đặt `organization_id` ở vị trí đầu.
3. Mọi migration phải reversible hoặc mô tả rõ lý do không thể rollback.
4. Mọi connection phải set và clear `SESSION_CONTEXT('organization_id')` trong transaction.
5. Không tin vào `organization_id` do client gửi; lấy tenant từ authenticated principal.
6. Loan, payment và audit data không được hard-delete.

## API and security

1. Endpoint mới phải nằm dưới `/api/v1` và có permission requirement rõ ràng.
2. Validation xảy ra tại API boundary và được lặp lại ở domain khi invariant quan trọng.
3. Error response dùng RFC Problem Details và không làm lộ stack trace hoặc secret.
4. Refresh/logout dùng CSRF protection; token không được lưu trong localStorage.
5. Mutation checkout, return và payment phải idempotent.
6. Password chỉ lưu dưới dạng Argon2id hash.

## Testing and review

1. Test thất bại phải tồn tại trước production code cho mọi behavior change.
2. Mọi bug phải có regression test.
3. TDD không thay thế integration test ở tenant, auth và transaction boundary.
4. Không merge khi checkpoint hoặc security review chưa đạt.
5. Không dùng mock để che giấu contract của database hoặc queue nếu integration test khả thi.
