# Quyết định nền tảng bắt buộc

Tài liệu này là nguồn quyết định chung cho các ranh giới tenant, control plane, database identity, audit/outbox và vòng đời dữ liệu. Các tài liệu chuyên biệt phải tuân theo tài liệu này; khi có mâu thuẫn, quyết định ở đây được ưu tiên cho đến khi được thay đổi có review.

## 1. Tenant discovery và platform control plane

`organization_id` không bao giờ được client chọn sau khi đã xác thực. Tuy nhiên, endpoint công khai `POST /api/v1/auth/login` bắt buộc nhận `organization_slug`, `email` và `password`. `organization_slug` chỉ dùng để xác định tenant mà credential sẽ được kiểm tra; nó không phải authorization claim và không được chấp nhận ở bất kỳ protected endpoint nào.

`core.organizations` là root registry của tenant: nó là ngoại lệ cho yêu cầu foreign key tới chính organization nhưng vẫn là tenant-addressable row và phải có RLS khi request đã có context. Pre-auth access chỉ dùng các stored procedure `EXECUTE AS OWNER` có grant `EXECUTE` hẹp: `core.resolve_login_tenant` nhận normalized slug và trả `organization_id` cùng trạng thái tối thiểu cho password verification; `core.resolve_refresh_session` nhận hash refresh token và chỉ trả principal của session hợp lệ để middleware set context. Không có pre-auth `SELECT` tổng quát. Resolver không có row active phải vẫn chạy Argon verification trên dummy hash cùng cost; slug không tồn tại, tenant bị vô hiệu hóa hoặc password sai đều trả cùng một Problem Details xác thực thất bại. Sau login/refresh, access token là nguồn duy nhất cho `organization_id`.

Platform administrator không dùng user/role của tenant và không có API công khai trong V1. Bootstrap tenant, migration, khôi phục backup và thao tác liên tenant chạy qua management command/operational runbook, dùng deployment identity riêng, secret manager và audit event actor loại `platform`. Runtime application identity không có quyền thực hiện các thao tác này.

## 2. Database identities và RLS fail-closed

Mỗi deployment dùng tối thiểu hai SQL Server identity:

- `migration` sở hữu quyền DDL cần thiết để tạo schema, constraint, RLS predicate/security policy và seed có kiểm soát.
- `runtime` chỉ có DML/EXEC cần thiết cho application; không là `db_owner`, không có `ALTER ANY SECURITY POLICY`, `CONTROL`, `IMPERSONATE`, quyền DDL hay quyền bypass RLS.

RLS predicate phải schema-bound, `TRY_CONVERT` session value sang `uniqueidentifier`, và trả false khi context thiếu hoặc không hợp lệ. Nó áp dụng cho mọi tenant-addressable table, gồm cả `core.organizations` sau login. Chỉ tenant middleware, worker transaction wrapper và management command được phép gọi `sp_set_session_context`; mọi wrapper phải đặt context trước query đầu tiên, clear nó trong `finally`, rồi invalidate connection nếu clear thất bại. Các đường pre-context duy nhất là procedures `EXECUTE AS OWNER` đã liệt kê; chúng chỉ trả dữ liệu tối thiểu, không nhận client-supplied organization id và có integration test riêng. Migration/CI phải đối chiếu system catalog để fail khi tenant-addressable table thiếu filter hoặc block predicate.

Mọi tenant-owned parent table phải có candidate key `(organization_id, entity_id)`. Mọi foreign key giữa tenant-owned tables phải tham chiếu cặp `(organization_id, foreign_id)` tương ứng. Việc UUID toàn cục là primary key không thay thế ràng buộc này. `core.organizations` không có parent foreign key, nhưng không là ngoại lệ RLS; system/control-plane exception khác phải được liệt kê rõ trong database design và có test truy cập riêng.

## 3. Audit, outbox và worker

Mọi mutation nghiệp vụ ghi audit event trong cùng transaction. `ops.audit_events` append-only; runtime identity chỉ được insert/select theo RLS, không có quyền update/delete. Payload audit dùng allow-list field và không chứa password, token, credential thanh toán, raw webhook body hoặc PII không cần thiết. Một login failure không resolve được tenant là system-scope security fact, không phải tenant-owned row: chỉ `ops.record_prelogin_security_event` với `EXECUTE AS OWNER` được ghi một classification allow-list và correlation ID vào `ops.prelogin_security_events`; runtime chỉ có quyền `EXECUTE`, không có `SELECT`/DML trực tiếp, và procedure không nhận password, email hoặc slug thô.

Mọi side effect bất đồng bộ bắt buộc ghi `ops.outbox_events` trong transaction tạo dữ liệu nghiệp vụ. Một event gồm `event_id`, `organization_id`, `topic`, aggregate type/id, `payload_version`, payload allow-list, idempotency key, `occurred_at`, attempts, `available_at`, lease token/expiry, `delivered_at` và lỗi đã sanitize. Unique key `(organization_id, topic, idempotency_key)` ngăn cùng logical event được ghi hai lần.

Dispatcher claim event bằng `ops.claim_outbox_event`, stored procedure `EXECUTE AS OWNER` claim lease nguyên tử và chỉ trả một server-created event. Sau đó worker set tenant context từ event, gửi tới handler/Celery và chỉ đánh dấu delivered khi consumer xác nhận. Consumer lưu deduplication key trước side effect. Retry có exponential backoff hữu hạn; event hết retry vào dead-letter trạng thái quan sát được. Payload và handler version phải tương thích ngược cho tới khi backlog version cũ bằng không. Worker không nhận tenant id từ message client.

## 4. Identity, edge security và idempotency

Access JWT dùng duy nhất `RS256`, header `kid`, `iss`, `aud`, `sub`, `organization_id`, `session_id`, `iat`, `nbf`, `exp` và token version. Verifier allow-list chính xác algorithm, issuer và audience; không chấp nhận `none` hay algorithm khác. Rotation giữ public key trước đó cho đến khi access token cũ hết hạn; private key chỉ ở secret manager và rotation được audit.

`X-Request-ID` do server tạo nếu thiếu; giá trị client gửi chỉ được giữ khi khớp `[A-Za-z0-9._-]{1,128}`. Giá trị sai được thay bằng UUID mới trước khi log hoặc trả response.

Redis-backed limiter fail-closed với login, refresh, password change và webhook endpoint: khi limiter không khả dụng, endpoint trả `503` Problem Details không tiết lộ trạng thái account. Những endpoint khác phải phát metric `rate_limit_backend_unavailable`; chỉ được fail-open khi deployment policy cho phép và phải có compensating edge rate limit.

Idempotency key gắn với tenant, method, canonical endpoint và hash canonical request body. Bản ghi sống 24 giờ rồi bị worker dọn. Nó chỉ lưu metadata và representation đã allow-list/được mã hóa khi cần; không lưu secret, raw token, raw card data hoặc raw webhook. Replay dựng stable response từ resource reference hoặc representation an toàn; cùng key khác request hash trả `409`.

## 5. Payment, privacy và retention

Payment provider callback đi qua endpoint riêng theo provider, xác thực chữ ký trên raw request body trước parse, kiểm tra timestamp/replay window tối đa 5 phút và deduplicate `(organization_id, provider, provider_event_id)`. Lưu hash payload và event metadata đã sanitize, không lưu raw credential/card data. Payment state chỉ chuyển theo state machine `pending`, `authorized`, `succeeded`, `failed`, `refunded`, `partially_refunded`, `disputed`; partial/refund phải có allocation record và audit. Job reconciliation xử lý payment `pending` quá timeout, không giả định timeout là thất bại.

PII được phân loại ở schema/API và chỉ trả cho principal có permission đúng. Profile/account được deactive trước; anonymization hoặc deletion chỉ chạy theo retention policy đã được tenant operator phê duyệt, có legal-hold exception và audit. Loan, payment và audit history không hard-delete. Trước production, release manifest bắt buộc ghi policy owner, jurisdiction, thời hạn dữ liệu profile/audit/payment/log và cơ chế legal hold; không có giá trị đó thì deployment bị chặn.

## 6. Mục tiêu vận hành mặc định

Mặc định self-hosted V1 có availability objective 99.5% mỗi tháng, RPO không quá 15 phút và RTO không quá 4 giờ. Môi trường có cam kết khác phải ghi giá trị chặt hơn hoặc lý do/owner chấp thuận trong release manifest.

SQL Server dùng full backup hằng tuần, differential backup hằng ngày và transaction-log backup mỗi 15 phút; giữ backup ít nhất 35 ngày, mã hóa và tách khóa khỏi database host. Restore drill diễn ra tối thiểu mỗi quý vào môi trường cô lập, với một operator owner được chỉ định; drill chỉ đạt khi database khôi phục, migration version khớp và RLS smoke tests pass.

Alert page khi backup thất bại, restore drill quá hạn, readiness không đạt, 5xx vượt 2% trong 5 phút, hoặc p95 latency vượt hai lần baseline đã ghi trong 15 phút. Queue backlog, dead-letter event, database pool saturation và RLS denial tăng bất thường tạo alert có runbook và owner.
