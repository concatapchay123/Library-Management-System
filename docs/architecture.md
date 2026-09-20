# Kiến trúc OpenLibraryOS

## Mục tiêu

OpenLibraryOS dùng một modular monolith để giữ transaction boundary, debugging và local development đơn giản trong giai đoạn domain còn đang tiến hóa. Ranh giới module được thiết kế đủ rõ để sau này có thể tách thành service mà không phải viết lại domain model.

## Quyết định chính

| Chủ đề | Quyết định |
|---|---|
| Repository | Một monorepo gồm `backend/` và `frontend/`. |
| Backend | Python 3.11+, Flask app factory, SQLAlchemy 2.x, Flask-Migrate. |
| Frontend | React, TypeScript, Vite; không truy cập database. |
| API | REST `/api/v1`, OpenAPI contract-first. |
| Database | Một SQL Server database; schema `core`, `education`, `public_library`, `ops`. |
| Tenancy | `organization_id` ở mọi tenant-owned table; SQL Server RLS + service authorization. `core.organizations` là root row không có parent FK nhưng vẫn có RLS; system exception phải được liệt kê tại `foundational-decisions.md`. |
| Async | Redis và Celery cho notification, overdue và reservation expiry. |
| Edge | Nginx reverse proxy, TLS termination và security headers. |

## Dependency direction

```text
frontend
    │ HTTPS/JSON
    ▼
api adapters ──► application services ──► domain model
    │                    │                    │
    │                    ▼                    │
    └──────────────► infrastructure ◄─────────┘
                         │
                         ├── SQL Server
                         ├── Redis/Celery
                         └── Email adapter
```

- `domain` chỉ biết value objects, entities, policies và domain errors.
- `application` biết use case, authorization input và transaction boundary.
- `infrastructure` biết ORM, Redis, Celery, email và SQL Server session context.
- `api` biết Flask, request/response schema và HTTP status.
- `education` và `public_library` gọi interface của core, không sửa core internals.

## Target backend layout

```text
backend/
├── pyproject.toml
├── src/openlibrary/
│   ├── app/
│   ├── shared/
│   └── modules/
│       ├── core/
│       │   ├── domain/
│       │   ├── application/
│       │   ├── infrastructure/
│       │   └── api/
│       ├── education/
│       └── public_library/
└── tests/
    ├── unit/
    ├── integration/
    └── api/
```

## Target frontend layout

```text
frontend/
├── package.json
├── src/
│   ├── app/
│   ├── features/auth/
│   ├── features/catalog/
│   ├── features/circulation/
│   ├── features/education/
│   ├── features/public-library/
│   └── shared/
└── tests/
```

Frontend feature code may own view state and client validation, nhưng business invariant vẫn phải được enforce lại ở backend.

## Module boundaries

Core cung cấp các capability: organization, identity, RBAC, catalog, inventory, circulation, reservation, notification và audit. Education chỉ thêm borrower profile và policy resolver cho student/teacher. Public library chỉ thêm member, plan, subscription, fine, payment và invoice.

Core không biết một borrower là student hay member. Core chỉ nhận một policy interface và borrower reference đã được authorization. Điều này cho phép thêm edition mới mà không tạo conditional branch trong circulation.

## Request lifecycle

1. Nginx tạo `X-Request-ID` hoặc forward giá trị đã qua validation.
2. Login public dùng `organization_slug` qua resolver hẹp; refresh public dùng hash cookie qua resolver session hẹp. Các endpoint protected xác thực access JWT và lấy `user_id`, `organization_id`, session và permission.
3. Tenant middleware mở transaction, set `SESSION_CONTEXT('organization_id')` trước query đầu tiên và fail closed khi context không hợp lệ.
4. Route parse input bằng Pydantic schema và gọi application service.
5. Service kiểm tra permission, invariant và ownership; ORM query được RLS bảo vệ thêm.
6. Mutation ghi audit event và outbox event trong cùng transaction khi có side effect bất đồng bộ.
7. Middleware clear tenant context trước khi trả connection về pool; clear failure invalidate connection.
8. API trả JSON thành công hoặc RFC Problem Details kèm request id.

Platform control plane không đi qua request lifecycle này. Bootstrap, migration, restore và thao tác liên tenant dùng operational command cùng database/deployment identity riêng. Quy tắc chi tiết nằm tại `docs/foundational-decisions.md`.

## Future extraction rule

Chỉ tách module thành service khi có một trong các bằng chứng: throughput độc lập, deployment cadence độc lập, failure isolation cần thiết hoặc ownership team rõ ràng. Trước khi tách, module phải giao tiếp qua application ports và có integration contract độc lập.
