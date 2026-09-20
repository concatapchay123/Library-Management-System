# Thiết kế database OpenLibraryOS

## Nguyên tắc chung

- Database engine: SQL Server.
- Khóa chính dùng `uniqueidentifier`; service tạo UUID và database có thể dùng `NEWSEQUENTIALID()` cho bảng mới.
- Timestamp dùng `datetime2(3)` ở UTC.
- Tiền dùng `decimal(19,4)` với currency code `char(3)`.
- Trạng thái dùng `varchar(32)` kết hợp check constraint hoặc lookup table; domain service kiểm tra transition.
- Mọi persistent table có `organization_id uniqueidentifier NOT NULL` và foreign key tới `core.organizations(organization_id)`, ngoại trừ chính bảng `core.organizations`, nơi `organization_id` là khóa gốc.
- Mọi bảng có `created_at`, `updated_at`; bảng nghiệp vụ có `created_by`/`updated_by` khi cần audit actor.
- Không dùng cascade delete cho loan, payment hoặc audit.

## Core schema

| Table | Columns chính | Khóa và quan hệ |
|---|---|---|
| `core.organizations` | `organization_id`, `name`, `slug`, `organization_type`, `status`, `timezone`, `settings_json` | PK `organization_id`, unique `slug` |
| `core.organization_modules` | `organization_module_id`, `organization_id`, `module_code`, `status`, `enabled_at`, `disabled_at` | unique `(organization_id, module_code)` |
| `core.users` | `user_id`, `organization_id`, `email`, `password_hash`, `status`, `last_login_at` | PK `user_id`, unique `(organization_id, email)` |
| `core.user_profiles` | `profile_id`, `organization_id`, `user_id`, `display_name`, `phone`, `avatar_url` | FK user, unique `(organization_id, user_id)` |
| `core.roles` | `role_id`, `organization_id`, `name`, `description`, `is_system` | unique `(organization_id, name)` |
| `core.permissions` | `permission_id`, `organization_id`, `code`, `description` | unique `(organization_id, code)`; permission rows seeded per tenant |
| `core.role_permissions` | `organization_id`, `role_id`, `permission_id` | composite PK and tenant FKs |
| `core.user_roles` | `organization_id`, `user_id`, `role_id` | composite PK and tenant FKs |
| `core.refresh_sessions` | `session_id`, `organization_id`, `user_id`, `token_hash`, `parent_session_id`, `expires_at`, `revoked_at`, `last_used_at` | unique token hash; rotation chain |
| `core.books` | `book_id`, `organization_id`, `isbn`, `title`, `subtitle`, `authors_json`, `publisher`, `published_year`, `language`, `status` | index title/ISBN per tenant |
| `core.book_copies` | `copy_id`, `organization_id`, `book_id`, `barcode`, `location_id`, `status`, `condition_code`, `acquired_at` | unique `(organization_id, barcode)` |
| `core.locations` | `location_id`, `organization_id`, `name`, `code`, `parent_location_id`, `status` | unique `(organization_id, code)` |
| `core.copy_status_history` | `history_id`, `organization_id`, `copy_id`, `from_status`, `to_status`, `reason`, `actor_id` | append-only FK copy |
| `core.loans` | `loan_id`, `organization_id`, `copy_id`, `borrower_user_id`, `request_status`, `loan_status`, `requested_at`, `approved_at`, `checked_out_at`, `due_at`, `returned_at`, `policy_snapshot_json` | filtered unique active loan per copy |
| `core.reservations` | `reservation_id`, `organization_id`, `book_id`, `requester_user_id`, `queue_position`, `status`, `hold_expires_at` | queue index by book/status/created time |
| `core.notifications` | `notification_id`, `organization_id`, `user_id`, `channel`, `type`, `payload_json`, `status`, `read_at` | user inbox index |

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
| `public_library.payments` | `payment_id`, `organization_id`, `member_id`, `fine_id`, `amount`, `currency`, `provider`, `provider_reference`, `status`, `paid_at` | idempotent provider reference |
| `public_library.invoices` | `invoice_id`, `organization_id`, `member_id`, `number`, `subtotal`, `tax`, `total`, `currency`, `status`, `issued_at` | unique `(organization_id, number)` |
| `public_library.invoice_lines` | `invoice_line_id`, `organization_id`, `invoice_id`, `description`, `quantity`, `unit_price`, `amount` | immutable after issue |

## Ops schema

| Table | Columns chính | Quy tắc |
|---|---|---|
| `ops.audit_events` | `audit_id`, `organization_id`, `actor_user_id`, `action`, `entity_type`, `entity_id`, `before_json`, `after_json`, `request_id`, `occurred_at` | append-only, no secrets |
| `ops.job_records` | `job_id`, `organization_id`, `job_type`, `payload_json`, `status`, `attempts`, `next_run_at`, `last_error` | retry and dead-letter visibility |
| `ops.idempotency_keys` | `organization_id`, `key`, `endpoint`, `request_hash`, `response_status`, `response_json`, `expires_at` | unique `(organization_id, key, endpoint)` |

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

Mỗi tenant table có security policy dùng cùng predicate function. Predicate lấy `SESSION_CONTEXT(N'organization_id')`, cast sang `uniqueidentifier` và so sánh với `organization_id`. Filter predicate bảo vệ SELECT; block predicate bảo vệ INSERT/UPDATE/DELETE. Bootstrap path cho organization mới dùng connection role có quyền tạo tenant và ghi audit.

RLS test matrix phải chứng minh:

1. Tenant A không đọc được row Tenant B.
2. Tenant A không update/delete được row Tenant B.
3. Insert với `organization_id` khác session context bị block.
4. Connection pool reuse không giữ context của request trước.
5. Privileged bootstrap path là explicit, audited và không được dùng bởi request thường.

## Migration policy

Migration dùng Flask-Migrate/Alembic, chạy trong CI và deployment. Schema change đi theo expand → migrate data → switch reads/writes → contract. Không drop column hoặc đổi type trực tiếp khi còn application version cũ đang chạy.
