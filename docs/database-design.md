# Thiết kế database OpenLibraryOS

## Nguyên tắc chung

- Database engine: SQL Server.
- Khóa chính dùng `uniqueidentifier`; service tạo UUID và database có thể dùng `NEWSEQUENTIALID()` cho bảng mới.
- Timestamp dùng `datetime2(3)` ở UTC.
- Tiền dùng `decimal(19,4)` với currency code `char(3)`.
- Trạng thái dùng `varchar(32)` kết hợp check constraint hoặc lookup table; domain service kiểm tra transition.
- Mọi tenant-owned table có `organization_id uniqueidentifier NOT NULL` và foreign key tới `core.organizations(organization_id)`. `core.organizations` là root registry nên không có parent foreign key, nhưng vẫn là tenant-addressable row và có RLS sau login. Pre-auth chỉ resolve qua `core.resolve_login_tenant` hoặc `core.resolve_refresh_session`, stored procedure `EXECUTE AS OWNER` với quyền `EXECUTE` hẹp; runtime không có pre-context `SELECT`. Ngoại lệ system/control-plane duy nhất hiện tại là `ops.prelogin_security_events`: login failure không resolve được tenant được ghi bằng `ops.record_prelogin_security_event`, một procedure owner-executing nhận classification allow-list và correlation ID, không nhận password, email hay slug thô; runtime chỉ được `EXECUTE` và không có direct DML/read. Mọi ngoại lệ mới phải được ghi trong `docs/foundational-decisions.md`, có lý do và test riêng.
- Mọi bảng có `created_at`, `updated_at`; bảng nghiệp vụ có `created_by`/`updated_by` khi cần audit actor.
- Không dùng cascade delete cho loan, payment hoặc audit.
- Mỗi parent table tenant-owned có candidate key `(organization_id, <primary_id>)`; child table tham chiếu parent bằng composite foreign key `(organization_id, <foreign_id>)`. Không dùng single-column UUID foreign key giữa hai tenant table.

## Core schema

| Table | Columns chính | Khóa và quan hệ |
|---|---|---|
| `core.organizations` | `organization_id`, `name`, `slug`, `organization_type`, `status`, `timezone`, `settings_json` | root PK `organization_id`, unique `slug`, RLS after login; pre-auth lookup only through `core.resolve_login_tenant` |
| `core.organization_modules` | `organization_module_id`, `organization_id`, `module_code`, `status`, `enabled_at`, `disabled_at` | unique `(organization_id, module_code)` |
| `core.users` | `user_id`, `organization_id`, `email`, `password_hash`, `status`, `last_login_at` | PK `user_id`, unique `(organization_id, email)` |
| `core.user_profiles` | `profile_id`, `organization_id`, `user_id`, `display_name`, `phone`, `avatar_url` | composite FK `(organization_id, user_id)`, unique `(organization_id, user_id)` |
| `core.roles` | `role_id`, `organization_id`, `name`, `description`, `is_system` | unique `(organization_id, name)` |
| `core.permissions` | `permission_id`, `organization_id`, `code`, `description` | unique `(organization_id, code)`; permission rows seeded per tenant |
| `core.role_permissions` | `organization_id`, `role_id`, `permission_id` | composite PK and tenant FKs |
| `core.user_roles` | `organization_id`, `user_id`, `role_id` | composite PK and tenant FKs |
| `core.refresh_sessions` | `session_id`, `organization_id`, `user_id`, `token_hash`, `parent_session_id`, `expires_at`, `revoked_at`, `last_used_at` | composite FK user và self-FK parent session; unique token hash; pre-auth resolution only via `core.resolve_refresh_session`; rotation chain |
| `core.books` | `book_id`, `organization_id`, `isbn`, `title`, `subtitle`, `authors_json`, `publisher`, `published_year`, `language`, `status` | index title/ISBN per tenant |
| `core.book_copies` | `copy_id`, `organization_id`, `book_id`, `barcode`, `location_id`, `status`, `condition_code`, `acquired_at` | composite FK book/location; unique `(organization_id, barcode)` |
| `core.locations` | `location_id`, `organization_id`, `name`, `code`, `parent_location_id`, `status` | composite self-FK parent location; unique `(organization_id, code)` |
| `core.copy_status_history` | `history_id`, `organization_id`, `copy_id`, `from_status`, `to_status`, `reason`, `actor_id` | append-only composite FK copy/actor |
| `core.loans` | `loan_id`, `organization_id`, `copy_id`, `borrower_user_id`, `request_status`, `loan_status`, `requested_at`, `approved_at`, `checked_out_at`, `due_at`, `returned_at`, `policy_snapshot_json` | composite FK copy/borrower; filtered unique active loan per copy |
| `core.reservations` | `reservation_id`, `organization_id`, `book_id`, `requester_user_id`, `queue_position`, `status`, `hold_expires_at` | composite FK book/requester; queue index by book/status/created time |
| `core.notifications` | `notification_id`, `organization_id`, `user_id`, `channel`, `type`, `payload_json`, `status`, `read_at` | composite FK user; user inbox index |

## Education schema

| Table | Columns chính | Quan hệ |
|---|---|---|
| `education.students` | `student_id`, `organization_id`, `user_id`, `student_number`, `department_id`, `status` | one-to-one user profile |
| `education.teachers` | `teacher_id`, `organization_id`, `user_id`, `employee_number`, `department_id`, `status` | one-to-one user profile |
| `education.departments` | `department_id`, `organization_id`, `code`, `name`, `status` | unique code per tenant |
| `education.classes` | `class_id`, `organization_id`, `code`, `name`, `department_id`, `semester_id` | department/semester FK |
| `education.courses` | `course_id`, `organization_id`, `code`, `name`, `department_id` | unique code per tenant |
| `education.semesters` | `semester_id`, `organization_id`, `name`, `starts_on`, `ends_on`, `status` | date check constraint |
| `education.class_memberships` | `organization_id`, `class_id`, `student_id`, `joined_at`, `left_at` | composite uniqueness |
| `education.borrower_policies` | `policy_id`, `organization_id`, `borrower_type`, `max_active_loans`, `duration_days` | one active policy per type |

## Public library schema

| Table | Columns chính | Quan hệ |
|---|---|---|
| `public_library.members` | `member_id`, `organization_id`, `user_id`, `member_number`, `status` | unique member number |
| `public_library.membership_plans` | `plan_id`, `organization_id`, `name`, `max_active_loans`, `duration_days`, `price`, `currency`, `status` | plan history preserved |
| `public_library.subscriptions` | `subscription_id`, `organization_id`, `member_id`, `plan_id`, `starts_at`, `ends_at`, `status` | active subscription constraint |
| `public_library.fines` | `fine_id`, `organization_id`, `member_id`, `loan_id`, `amount`, `currency`, `status`, `assessed_at` | loan/payment relation |
| `public_library.payments` | `payment_id`, `organization_id`, `member_id`, `fine_id`, `amount`, `currency`, `provider`, `provider_reference`, `provider_event_id`, `status`, `paid_at` | composite FK member/fine; unique `(organization_id, provider, provider_event_id)`; state machine |
| `public_library.payment_allocations` | `allocation_id`, `organization_id`, `payment_id`, `fine_id`, `amount`, `allocation_type`, `created_at` | composite FK payment/fine; supports partial-payment/refund allocation |
| `public_library.invoices` | `invoice_id`, `organization_id`, `member_id`, `number`, `subtotal`, `tax`, `total`, `currency`, `status`, `issued_at` | unique `(organization_id, number)` |
| `public_library.invoice_lines` | `invoice_line_id`, `organization_id`, `invoice_id`, `description`, `quantity`, `unit_price`, `amount` | immutable after issue |

## Ops schema

| Table | Columns chính | Quy tắc |
|---|---|---|
| `ops.audit_events` | `audit_id`, `organization_id`, `actor_user_id`, `actor_type`, `action`, `entity_type`, `entity_id`, `payload_version`, `payload_json`, `correlation_id`, `occurred_at` | append-only, allow-listed JSON payload, no secrets; runtime identity cannot update/delete |
| `ops.prelogin_security_events` | `event_id`, `action`, `correlation_id`, `occurred_at` | system-scope unknown-tenant login failures only; no credential, email or raw slug; inserted solely through `ops.record_prelogin_security_event` and unreadable by runtime |
| `ops.outbox_events` | `event_id`, `organization_id`, `event_type`, `aggregate_type`, `aggregate_id`, `payload_version`, `payload_json`, `correlation_id`, `idempotency_key`, `created_at` | durable transactional outbox; unique `(organization_id, event_type, idempotency_key)`; claim/delivery fields arrive with the dispatcher task |
| `ops.job_records` | `job_id`, `organization_id`, `outbox_event_id`, `job_type`, `payload_version`, `status`, `attempts`, `next_run_at`, `last_error` | composite tenant relation, consumer deduplication and dead-letter visibility |
| `ops.idempotency_keys` | `organization_id`, `key`, `method`, `endpoint`, `request_hash`, `resource_reference`, `safe_response_json`, `expires_at` | unique `(organization_id, key, method, endpoint)`; 24-hour expiry; no secret/raw PII |

## Relationships

```text
organizations
 ├── users ── user_roles ── roles ── role_permissions ── permissions
 ├── books ── book_copies ── locations
 ├── users ── loans ── book_copies
 ├── users ── reservations ── books
 ├── users ── notifications
 ├── users ── education.students / education.teachers
 └── public_library.members ── subscriptions ── membership_plans
```

## Index strategy

- Tất cả tenant lookup index bắt đầu bằng `organization_id`.
- `users`: `(organization_id, email)`, `(organization_id, status)`.
- `books`: `(organization_id, isbn)`, full-text/search index theo `title` và author data khi volume chứng minh cần.
- `book_copies`: `(organization_id, barcode)`, `(organization_id, book_id, status)`.
- `loans`: `(organization_id, copy_id, loan_status)`, `(organization_id, borrower_user_id, loan_status)`, `(organization_id, due_at, loan_status)`.
- `reservations`: `(organization_id, book_id, status, created_at, reservation_id)`.
- `audit_events`: `(organization_id, entity_type, entity_id, occurred_at)` và `(organization_id, actor_user_id, occurred_at)`.
- Không tạo index cho mọi cột theo thói quen; mỗi index phải gắn với query hoặc constraint được kiểm chứng.

## Row-Level Security

Mỗi tenant-addressable table, gồm `core.organizations`, có security policy dùng cùng schema-bound predicate function. Predicate lấy `SESSION_CONTEXT(N'organization_id')`, dùng `TRY_CONVERT` sang `uniqueidentifier` và trả false khi context thiếu hoặc không hợp lệ. Filter predicate bảo vệ SELECT; block predicate bảo vệ INSERT/UPDATE/DELETE. Pre-auth lookup chỉ đi qua `core.resolve_login_tenant` hoặc `core.resolve_refresh_session`; runtime không được query trực tiếp khi context chưa có.

Runtime identity không là database owner và không có DDL, `CONTROL`, `IMPERSONATE` hoặc quyền thay đổi/bỏ qua security policy. Migration/platform identity tách biệt mới được tạo policy, seed tenant hoặc bootstrap organization. CI chạy system-catalog test để fail khi bất kỳ tenant-addressable table nào thiếu cả filter và block predicate, hoặc runtime có direct pre-context select thay vì procedure grant. `ops.claim_outbox_event` là procedure `EXECUTE AS OWNER` duy nhất được dispatcher dùng trước khi biết organization context.

RLS test matrix phải chứng minh:

1. Tenant A không đọc được row Tenant B.
2. Tenant A không update/delete được row Tenant B.
3. Insert với `organization_id` khác session context bị block.
4. Connection pool reuse không giữ context của request trước.
5. Privileged bootstrap path là explicit, audited và không được dùng bởi request thường.
6. System-catalog test phát hiện mọi tenant-owned table không có cả filter và block policy.
7. Runtime database identity không có quyền DDL, owner hoặc thay đổi/bỏ qua security policy.

## Migration policy

Migration dùng Flask-Migrate/Alembic, chạy trong CI và deployment. Schema change đi theo expand → migrate data → switch reads/writes → contract. Không drop column hoặc đổi type trực tiếp khi còn application version cũ đang chạy.
