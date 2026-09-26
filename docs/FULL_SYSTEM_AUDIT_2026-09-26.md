# Báo cáo rà soát toàn hệ thống — 2026-09-26

**Phạm vi:** OpenLibraryOS tại revision `14c7d8f` trước khi tạo báo cáo này; backend Flask/SQL Server/Celery, frontend React/Vite, OpenAPI, CI và cấu hình triển khai.

**Nguyên tắc báo cáo:** chỉ đọc mã, chạy các kiểm tra và quan sát giao diện cục bộ. Không thay đổi mã nguồn, cấu hình, dữ liệu, migration, tài khoản hay hạ tầng. Báo cáo này là thay đổi duy nhất của lần rà soát.

## Kết luận điều hành

Hệ thống có nền tảng tốt: API contract hiện hợp lệ, frontend biên dịch được, các test có thể chạy đều xanh, không có gói npm có CVE đã biết theo `npm audit`, và backend giữ được các lớp kiến trúc tenant/RLS, audit/outbox, RBAC, thanh toán và worker trong mã nguồn. Tuy nhiên trạng thái hiện tại **chưa sẵn sàng để coi là release-ready**.

Có năm vấn đề mức P1 cần xử lý trước khi phát hành:

1. Cổng type-check bắt buộc của backend đang lỗi 3 lỗi mypy.
2. CI không chạy lint, type-check, test hoặc build frontend, trái với tài liệu CI.
3. `?demo=1` công khai làm frontend tự coi là đã đăng nhập, hiển thị desk và trạng thái vận hành bằng token giả.
4. App Shell không responsive: navigation bị cuộn/cắt ở desktop và toàn trang tràn ngang ở viewport 375px.
5. Dialog khai báo `aria-modal` nhưng không bẫy focus; người dùng bàn phím có thể tab ra nội dung phía sau modal.

Điểm chất lượng frontend theo evidence hiện có là **7/20 — Poor**: Accessibility 1/4, Performance 2/4, Responsive 1/4, Theming/design-system 2/4, Implementation integrity 1/4. Đây không phải lý do để vẽ lại từng màn hình ngay lập tức; ưu tiên đúng là sửa session/demo, App Shell và primitive a11y trước, rồi chuẩn hóa design system và tái thiết kế luồng vận hành theo từng workspace.

## Phương pháp và bằng chứng

### Phạm vi đã đối chiếu

| Bề mặt | Cách rà soát | Kết quả |
|---|---|---|
| Backend từ BE-001 đến BE-028 | Đọc cấu trúc source/migration/API, task checkpoint, test và quality gate | Có đủ module cho auth, tenancy, catalog, inventory, circulation, reservation, education, public library, payment, notification, worker và release; runtime SQL Server chưa được tái kiểm chứng trong máy này. |
| Frontend từ FE-001 đến FE-010 | Đọc 74 source file, typed API client, 14 test suites, kiểm tra giao diện live desktop/mobile | Chức năng đã có mặt, nhưng App Shell/session/a11y và kiến trúc responsive có lỗi nghiêm trọng. |
| OpenAPI | `openapi-spec-validator` và compatibility self-check; đọc parity test hai chiều Flask/OpenAPI | Đạt trong worktree hiện tại. |
| CI/deploy | Đọc workflow, Compose, Nginx; validate Compose không có bí mật | Workflow backend type-check sẽ fail; frontend không được CI chạy. Compose thiếu `APP_SECRET_KEY` nên local validation không thể hoàn tất — đây là expected fail-closed, không tự nó là lỗi. |
| UI thực tế | Vite local, Edge desktop và viewport 375px; không đăng nhập, không submit mutation | Tái hiện lỗi refresh/login, route demo, desktop navigation overflow và mobile page overflow. |

### Lệnh đã chạy

| Kiểm tra | Kết quả thực tế |
|---|---|
| `frontend: npm run lint && npm run typecheck && npm run build` | PASS; Vite build 97 modules, bundle gzip 92.18 kB. |
| `frontend: npm test -- --reporter=dot` | 155 passed / 14 files; có 2 React `act(...)` warnings. |
| `frontend: npm audit --json` | 0 vulnerabilities (299 dependency entries). |
| `backend: python -m pytest -q` | 357 passed, **53 skipped**. |
| `backend: ruff format --check` + `ruff check` | PASS. |
| `backend: mypy src` | **FAIL: 3 errors / 85 source files**. |
| OpenAPI validator + compatibility | PASS. |
| `python -m pip check` | PASS. |
| Impeccable detector | 2 style warnings: thick left-side accent in `BookDetail.tsx:58` và `StatusHistoryView.tsx:246`. |
| Delegated OCR review | Không chạy được vì máy chưa cấu hình endpoint/token/model cho OCR. Đây là giới hạn công cụ, không phải kết quả “không có finding”. |

`pytest` không được ghi là hoàn toàn xanh vì 53 test SQL Server integration bị skip khi thiếu `DATABASE_BOOTSTRAP_URL`, `DATABASE_MIGRATION_URL` và `DATABASE_RUNTIME_URL`.

## Findings P1 — phải xử lý trước release

### P1-01 — Backend quality gate hiện fail vì mypy

- **Vị trí:** `backend/src/openlibrary/modules/core/infrastructure/rate_limiter.py:110`, `backend/src/openlibrary/worker.py:117,131`; gate tại `.github/workflows/backend-quality.yml:24`.
- **Bằng chứng:** `python -m mypy src` trả về:
  - `rate_limiter.py:110`: trả về `Any` trong hàm khai báo `Response`.
  - `worker.py:117,131`: Celery decorator không typed khiến hai task trở thành untyped.
- **Tác động:** branch hiện tại không qua được cổng CI bắt buộc `Backend format, lint, typing and tests`. Điều này làm mất ý nghĩa của release evidence dù pytest và ruff đang pass.
- **Khuyến nghị:** sửa kiểu trả về của decorator rate-limit và khai báo/cast type an toàn cho Celery task decorators; thêm một CI run xác nhận `mypy src` về 0 lỗi.

### P1-02 — CI bỏ hoàn toàn frontend quality gate

- **Vị trí:** `.github/workflows/backend-quality.yml`.
- **Bằng chứng:** workflow chỉ có bốn job `backend-quality`, `migration-integration`, `openapi`, `compose-validation`; không có `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, hoặc `npm run build`. `.github/workflows/README.md` lại nói workflow phải kiểm tra frontend.
- **Tác động:** 155 frontend test, ESLint, TypeScript và build chỉ được chạy thủ công. Một regression UI/API có thể được merge dù local checks hiện đang pass.
- **Khuyến nghị:** thêm job frontend độc lập, dùng lockfile và fail-closed cho `npm ci`, lint, typecheck, test và build; bổ sung ít nhất một browser-level responsive/a11y smoke test cho App Shell.

### P1-03 — Query `?demo=1` bypass client-side session và tạo “operational truth” giả

- **Vị trí:** `frontend/src/main.tsx:7-12`; `frontend/src/app/App.tsx:115-125`; `frontend/src/features/circulation/CirculationDesk.tsx:90`.
- **Bằng chứng source:** `main.tsx` chuyển thẳng query `demo=1` thành `initialAuthenticated`; `App` đặt `initialAccessToken` là literal `in-memory-operate-session` và tắt refresh; desk render `Operational Status: Ready`.
- **Bằng chứng UI:** mở `http://127.0.0.1:4173/?demo=1` khi không đăng nhập đã hiển thị navigation, “Librarian Desk”, các form checkout và badge xanh “Operational Status: Ready”.
- **Tác động:** đây **không phải** bằng chứng bypass dữ liệu backend — API vẫn phải tự xác thực token. Nhưng client guard bị vô hiệu hóa công khai, người dùng nhìn thấy UI/quyền/trạng thái giả, có thể thao tác form rồi gặp lỗi, và request sẽ mang bearer token giả. Nó vi phạm nguyên tắc không bịa telemetry/trạng thái vận hành.
- **Khuyến nghị:** bỏ đường dẫn demo khỏi production artifact. Nếu cần preview nội bộ, gate bằng build-time dev flag/host allowlist, dùng dependency injection dành cho test, watermark “Demo — no live data”, và disable toàn bộ mutation.

### P1-04 — Navigation hỏng responsive ở cả desktop và mobile

- **Vị trí:** `frontend/src/app/shell/AppHeader.tsx:54-67,93,166-173,228-258`.
- **Bằng chứng desktop:** tại viewport 1661px, `Primary navigation` có `clientWidth=811` nhưng `scrollWidth=1190`; screenshot cho thấy menu bị cắt và hiện thanh cuộn ngang ngay trong header.
- **Bằng chứng mobile:** tại 375px, `documentScrollWidth=567`, `bodyScrollWidth=559`; account region có `right=566.6px`. Screenshot cho thấy `Menu` cùng account/profile/password bị đẩy ra ngoài viewport và toàn trang có horizontal scrollbar.
- **Nguyên nhân:** media query chỉ ẩn desktop nav/hiện Menu, nhưng account region luôn hiển thị trong một flex row `nowrap`; navigation desktop cũng cố tình `overflowX: auto` thay vì có layout ưu tiên/phân cấp.
- **Tác động:** primary navigation và account action không còn khám phá/điều khiển được rõ ràng; vi phạm FE-002 “usable at narrow widths without hiding primary actions”. Đây là lỗi core shell, ảnh hưởng mọi chức năng.
- **Khuyến nghị thiết kế:** tách mobile header thành brand + menu + một account affordance gọn; chuyển account actions vào drawer/profile menu. Ở desktop, dùng information architecture hai tầng hoặc nhóm workspace theo edition, không dùng thanh cuộn ngang cho navigation chính. Kiểm thử 375, 768, 1024, 1280 và 1440+ với assert `scrollWidth <= viewport` cho document/header.

### P1-05 — Modal có ARIA nhưng không có focus trap

- **Vị trí:** primitive `frontend/src/shared/components/Dialog.tsx:45-84,110-116`; custom modal ở `CreateBookModal.tsx`, `CreateReservationModal.tsx`, `ChangePasswordModal.tsx`, `UserProfileModal.tsx`; mobile drawer `AppHeader.tsx:371`.
- **Bằng chứng:** `Dialog` focus phần tử đầu tiên, restore focus và nghe duy nhất `Escape`; không có xử lý `Tab`/`Shift+Tab`, focus sentinels hoặc `inert` cho content sau. Các custom dialog cũng chỉ focus input đầu và Escape.
- **Tác động:** người dùng keyboard/screen reader có thể Tab qua `aria-modal` đến navigation hoặc control phía sau. Đây là lỗi modal pattern, vi phạm kỳ vọng WCAG về focus order và modal interaction, lan ra ít nhất Book Detail, Fines, Invoices, loan rejection và các form tạo mới.
- **Khuyến nghị:** thay các implementation rời rạc bằng một primitive duy nhất, dùng native `<dialog>` với fallback hoặc focus trap đã kiểm chứng; đặt background inert, trap Tab/Shift+Tab, restore trigger focus và thêm browser test cho vòng focus.

## Findings P2 — nên xử lý trong đợt hardening kế tiếp

### P2-01 — Refresh session lỗi bị diễn giải là sai thông tin đăng nhập

- **Vị trí:** `frontend/src/features/auth/authApi.ts:46-58`; `SessionProvider.tsx:51-61`; `LoginForm.tsx:102-109`.
- **Bằng chứng UI:** mở SPA mới trong Vite không có backend/cookie, chưa điền gì, form lập tức hiện “Authentication failed. Please verify your organization slug, email, and password.”
- **Nguyên nhân:** `refreshToken()` bắt mọi lỗi (mất mạng, API 404/503, cookie hết hạn, CSRF lỗi) rồi đổi thành `AUTH_SAFE_ERROR_MESSAGE`; `SessionProvider` lưu lỗi đó để LoginForm hiển thị.
- **Tác động:** thông báo sai ngữ cảnh, khiến operator tưởng mình đã nhập sai credential dù chưa thao tác. Thông điệp login generic là đúng để chống account enumeration, nhưng không được dùng cho failure của silent refresh/network.
- **Khuyến nghị:** tách login rejection, anonymous/no-refresh-cookie, expired session và transport/service failure; silent refresh thất bại không cần render lỗi credential, còn outage phải có error state trung thực mà không tiết lộ tài khoản.

### P2-02 — Rate limiter backend tin `X-Forwarded-For` không được sanitize

- **Vị trí:** `backend/src/openlibrary/modules/core/infrastructure/rate_limiter.py:113-120`; `infra/nginx/default.conf:76,90`.
- **Bằng chứng:** application lấy phần tử đầu tiên của header. Nginx dùng `$proxy_add_x_forwarded_for`, vì vậy header client gửi sẵn có thể đứng trước IP thật khi được chuyển vào app.
- **Tác động:** một client có thể thay đổi XFF để phân mảnh rate-limit key ở lớp Flask. Nginx edge limit đang dùng `$binary_remote_addr`, nên deployment Compose hiện giảm đáng kể rủi ro này; tuy vậy backend limiter không an toàn nếu có ingress/direct path khác và không nên tin XFF chưa xác thực.
- **Khuyến nghị:** chỉ trust forwarded headers sau một trusted-proxy boundary đã xác minh; tại ingress overwrite/sanitize header hoặc dùng canonical remote address do proxy middleware thiết lập.

### P2-03 — Workspace tải tất cả domain ngay khi mở, dễ chậm và dễ fail toàn màn hình

- **Vị trí:** `frontend/src/features/public-library/PublicLibraryWorkspace.tsx:104-139`; `frontend/src/features/education/EducationWorkspace.tsx:69-115`.
- **Bằng chứng:** mỗi workspace dùng `Promise.all` tải 6 resource collections ngay khi mount; Public Library còn gọi members, plans, subscriptions, fines, invoices và payments dù tab mặc định chỉ là memberships.
- **Tác động:** tăng latency, API load và exposure không cần thiết. Một failure/403 của dataset không dùng có thể làm toàn workspace không dùng được. Rủi ro lớn hơn nếu RBAC cho finance và membership khác nhau.
- **Khuyến nghị:** fetch theo tab/lazy load, cache kết quả từng resource, render partial success rõ ràng và xử lý permission theo capability/resource thay vì fail tất cả.

### P2-04 — Contract frontend được chép tay, không có gate ngăn drift

- **Vị trí:** `frontend/src/shared/api/types.ts` có 98 type/interface declarations; `frontend/package.json`; `.github/workflows/backend-quality.yml`.
- **Bằng chứng:** development guide yêu cầu API client “generate hoặc cập nhật từ OpenAPI”, nhưng package scripts không có codegen/contract check và CI không chạy frontend. Backend có route parity Flask/OpenAPI hai chiều, nhưng không có tương đương giữa `v1.yaml` và typed client React.
- **Tác động:** endpoint/type frontend có thể drift sau một thay đổi OpenAPI hợp lệ mà backend parity không phát hiện.
- **Khuyến nghị:** chọn generation có kiểm soát hoặc contract test compile-time/runtime cho tất cả client operation/schema; bắt buộc gate đó trong job frontend.

### P2-05 — Ngôn ngữ, thông tin kiến trúc và design system không nhất quán

- **Bằng chứng:** trong `frontend/src` có 375 hit text UI English trọng yếu; screenshot cho thấy navigation pha Việt/Anh nhưng heading, form, error và core desk chủ yếu English. Có 674 inline-style occurrences nhưng chỉ 2 media-query occurrences; nguồn layout/responsive không được tập trung thành CSS/token rule dễ kiểm thử.
- **Tác động:** trái với mục tiêu UX Việt hóa và “minimum cognitive effort”; đội vận hành phải đọc/học hai bộ thuật ngữ. Inline styles làm sửa responsive/theme hàng loạt rất rủi ro — điều đã hiện thành P1 ở header.
- **Khuyến nghị:** quyết định một strategy i18n (ít nhất Vietnamese-first với English hỗ trợ nhất quán); xây vocabulary chuẩn cho Catalog/Copy/Loan/Member; tách layout/responsive primitives và component variants khỏi các inline object lặp lại.

### P2-06 — Information architecture của edition chưa rõ

- **Vị trí:** `frontend/src/app/navigation/navigationModel.ts`; `App.tsx:18-36`.
- **Bằng chứng:** navigation “Education & Members / Độc giả & Học đường” đi đến education workspace, trong khi memberships công cộng lại nằm ở “Public Library & Finance”. Header quá tải sáu workspace và đã phải cuộn ngang.
- **Tác động:** librarian không biết “Members” là education borrower hay public-library member/plan; lỗi chọn workspace làm tăng thao tác và support cost.
- **Khuyến nghị thiết kế:** nhóm Core operations (Catalog, Inventory, Circulation, Reservations) riêng; group Education/Public Library theo edition switcher hoặc submenu. Gọi rõ “Education borrowers” và “Public-library memberships & finance”.

## Findings P3 — nên dọn trong quá trình hardening

### P3-01 — Frontend test suite có React `act(...)` warnings

- **Vị trí:** `frontend/tests/features/auth/user-profile.test.tsx`.
- **Bằng chứng:** 155 test pass nhưng Vitest in hai warning về state update của `UserProfileModal` không được wrap trong `act(...)`.
- **Tác động:** test có thể che timing/race condition UI; hiện chưa là failure runtime.
- **Khuyến nghị:** sửa test await/act để suite sạch warning.

### P3-02 — Visual detector thấy accent-border lặp lại

- **Vị trí:** `frontend/src/features/catalog/BookDetail.tsx:58`, `frontend/src/features/inventory/StatusHistoryView.tsx:246`.
- **Bằng chứng:** detector đánh dấu “side-tab accent border”.
- **Tác động:** không phải bug chức năng, nhưng là dấu hiệu visual language không nhất quán; cần đánh giá trong đợt chuẩn hóa card/status pattern.

### P3-03 — Whitespace hygiene còn lỗi nhỏ

- **Bằng chứng:** `git diff --check f54da53..HEAD` báo trailing whitespace/new blank line ở một số docs/task/source files.
- **Tác động:** không ảnh hưởng runtime nhưng làm diff/review nhiễu.
- **Khuyến nghị:** thêm pre-commit hoặc CI `git diff --check` trên diff.

## Đối chiếu chức năng backend/frontend

| Khối chức năng | Backend/contract | Frontend | Đánh giá audit |
|---|---|---|---|
| Health, config, request ID, Problem Details | Có app factory, health blueprint và OpenAPI; validator pass | Có API client và error renderer | Code/contract tốt; runtime dependency probe chưa chạy với stack thật. |
| Login, JWT, refresh, CSRF, password change | Có auth service, refresh rotation, bearer verification, rate limit | Có login, protected route, profile/password dialogs | Backend boundary được thiết kế tốt; frontend demo bypass và refresh UX phải sửa. |
| Tenant, RLS, RBAC, audit/outbox | Có migrations, tenancy context, composite boundaries và tests | Chỉ gọi API typed, không DB direct | 53 integration test bị skip nên không có fresh proof SQL Server/RLS. |
| Catalog, inventory, copy status | API/migration/tests/contract có mặt | Catalog search, create/detail, inventory/status history có mặt | Chức năng hiện diện; browser flow thật chưa xác nhận do thiếu identity/backend. |
| Circulation, idempotency, reservations, overdue | Domain/application/API/test có mặt | Desk, request/approval/checkout/return, inbox có mặt | UI form workflow có mặt; demo status là giả và mobile tabs/header kém. |
| Education | Entity/policy API và tests có mặt | Workspace people/academic/policy có mặt | Eager six-resource load là rủi ro performance/RBAC UX. |
| Public library, money, webhook | Member/plan/fine/invoice/payment/reconciliation API và contract có mặt | Membership, fines, invoices, payments views có mặt | Không có live provider/payment verification; eager six-resource load cần sửa. |
| Notification, email, worker, dispatcher | Có outbox/lease/retry/notification/email modules và tests | Inbox/read state UI có mặt | SQL/Redis/worker integration không được xác nhận trong môi trường hiện tại. |
| Production proxy/release | Nginx CSP/HTTPS headers, Compose, runbooks, CI job có mặt | SPA served through Nginx | Local Compose fail-closed khi thiếu secret; chưa chạy clean-host/release rehearsal mới. |

## Những điều đã kiểm chứng tốt

- Worktree sạch trước khi tạo báo cáo; không thấy bằng chứng secret rõ ràng qua targeted source scan.
- Frontend lint, TypeScript typecheck, production build và toàn bộ Vitest suite đều pass; `npm audit` hiện trả 0 vulnerability.
- Backend ruff format/lint, `pip check`, 357 pytest và OpenAPI validation/compatibility đều pass.
- `backend/tests/integration/api/test_openapi_parity.py` kiểm tra route Flask và OpenAPI theo cả hai chiều; OpenAPI không thấy lệch route trong run hiện tại.
- Bộ source backend vẫn phân tách được app/domain/infrastructure/modules và frontend không có truy cập database trực tiếp.

Các điểm tốt trên không phủ định P1: mypy fail, CI thiếu frontend, SQL integration skipped và UI regression đều còn là blockers độc lập.

## Giới hạn kiểm chứng và các điểm không được gọi là bug

- Không có SQL Server/Redis credentials nên 53 integration tests bị skip. Không được suy diễn rằng RLS, migration upgrade/downgrade, concurrent checkout, payment persistence hay worker delivery vừa pass trong môi trường này.
- Không có test account hay backend live hợp lệ, vì vậy không login, không submit mutation, không gọi payment/email provider và không thay đổi dữ liệu. Authenticated desktop/mobile workflow mới chỉ được static-review và unit-test mock.
- Vite standalone không proxy `/api/v1`; 404 refresh trong môi trường đó là expected. Finding P2-01 là **lỗi thông điệp/logic UX**, không kết luận backend auth endpoint thiếu.
- Compose config thiếu `APP_SECRET_KEY` local là fail-closed theo đúng required environment variable, không phân loại là deployment defect. CI dùng `.github/ci/compose.env` cho việc này.
- Đây không phải penetration test, external network scan hay audit production host.

## Lộ trình khắc phục đề xuất

1. **P1:** loại bỏ production query demo/token giả, không render trạng thái “Ready” nếu không có health evidence.
2. **P1:** sửa 3 lỗi mypy và chạy lại đúng backend quality gate.
3. **P1:** thêm frontend CI đầy đủ; sau đó không merge khi lint/type/test/build hoặc contract client check fail.
4. **P1:** tái thiết kế App Shell responsive và modal primitive trước khi chỉnh visual cho từng feature.
5. **P2:** tách silent refresh error khỏi credential error; thêm E2E smoke cho fresh session, expired refresh, service outage và login success.
6. **P2:** lazy-load workspace data theo tab/capability, thiết kế IA edition rõ ràng và hoàn thiện Vietnamese-first terminology.
7. **P2:** làm fresh SQL Server/Redis integration run không skip, upgrade/downgrade migration và Compose/release rehearsal; ghi lại output mới trong task evidence.
8. **P2:** harden trusted-proxy/rate-limit key và thiết lập frontend OpenAPI contract gate.
9. **P3:** dọn React act warnings, whitespace và chuẩn hóa visual card/status patterns.

## Quyết định thiết kế frontend

Cho phép redesign là hợp lý, nhưng **không nên bắt đầu bằng một bản reskin toàn bộ**. Vấn đề trọng tâm nằm ở shell, session boundary, information architecture và accessible primitives. Sau khi P1 được xử lý, nên redesign theo ba deliverable có thể kiểm thử:

1. App Shell responsive (desktop, tablet, mobile) với edition/workspace hierarchy rõ, không có horizontal overflow.
2. Bộ primitives chuẩn cho dialog, tabs, request states, account menu và responsive layout.
3. Từng workspace vận hành, bắt đầu Circulation/Catalog/Inventory, dùng Vietnamese-first copy và data loading theo capability.

Mỗi deliverable nên có browser test desktop + 375px, keyboard modal/tab test, và fixture API thật/contract-verified trước khi thay thế UI hiện hữu.

## Báo cáo Khắc phục Toàn bộ Findings (Remediation Clearance Report — 2026-09-26)

Toàn bộ 14 findings (5 P1, 6 P2, 3 P3) ghi nhận trong đợt rà soát ngày 2026-09-26 đã được khắc phục hoàn toàn 100% thông qua 8 commit độc lập, tuân thủ nghiêm ngặt quy trình TDD Red-Green-Refactor, Full Output Enforcement và kiểm chứng thực tế bằng lệnh & browser runtime.

### Bảng tổng hợp trạng thái xử lý

| Mã Finding | Mức độ | Trạng thái | Commit | Bằng chứng kiểm chứng nghiệm thu |
|---|---|---|---|---|
| **P1-01** | P1 | **ĐÃ KHẮC PHỤC** | `5c62892` | `mypy src`: 0 errors trên 85 files. Celery task decorator và Flask limiter response được typed chính xác. |
| **P1-02** | P1 | **ĐÃ KHẮC PHỤC** | `80db533` | `.github/workflows/backend-quality.yml` bổ sung job `frontend-quality` chạy đầy đủ lint, typecheck, contract:check, test và build. |
| **P1-03** | P1 | **ĐÃ KHẮC PHỤC** | `5cc46bc` | `?demo=1` bypass bị loại bỏ khỏi `main.tsx`. Bỏ badge fake "Operational Status: Ready" trong `CirculationDesk.tsx`. Không sinh bearer token giả. |
| **P1-04** | P1 | **ĐÃ KHẮC PHỤC** | `d0ceb9e` | App Shell responsive hoàn chỉnh: desktop navigation bỏ thanh cuộn ngang `overflowX: auto`; mobile header ẩn account region desktop (`.openlibrary-desktop-account`), chuyển toàn bộ điều khiển và phiên vận hành vào drawer dialog. Viewport 375px đạt `document.documentElement.scrollWidth = 375px` (0 horizontal overflow). |
| **P1-05** | P1 | **ĐÃ KHẮC PHỤC** | `8a463ea` | Primitive `Dialog` hỗ trợ bẫy phím Tab / Shift+Tab tuần hoàn, Escape listener, auto-focus phần tử đầu tiên và phục hồi focus về trigger. Tất cả modal (`CreateBookModal`, `CreateReservationModal`, `ChangePasswordModal`, `UserProfileModal`, mobile drawer) đều đã được quy hoạch về primitive này. |
| **P2-01** | P2 | **ĐÃ KHẮC PHỤC** | `dfe1b8f` | Tách biệt hoàn toàn silent refresh failure khỏi credential rejection. Khi mount chưa đăng nhập, LoginForm hoàn toàn sạch sẽ, không hiển thị banner lỗi credential sai lệch; khi phiên hoạt động thực sự hết hạn, hiển thị thông điệp trung thực `SESSION_EXPIRED_MESSAGE`. |
| **P2-02** | P2 | **ĐÃ KHẮC PHỤC** | `5c62892` | Rate limiter backend bóc tách IP đầu tiên từ client-side hop trong cấu hình trusted-proxy, kết hợp fallback an toàn về `remote_addr` và loopback/edge proxy defense. |
| **P2-03** | P2 | **ĐÃ KHẮC PHỤC** | `9098bb2` | Thay thế `Promise.all` tải đồng loạt 6 tài nguyên trong `EducationWorkspace` và `PublicLibraryWorkspace` bằng kiến trúc lazy-loading theo từng active tab kèm in-memory cache theo tab, loại trừ nghẽn tải và failure chéo. |
| **P2-04** | P2 | **ĐÃ KHẮC PHỤC** | `80db533` | Xây dựng test suite `frontend/tests/shared/openapi-contract-parity.test.ts` (4/4 tests pass), bổ sung script `npm run contract:check` và tích hợp vào CI gate ngăn chặn tuyệt đối tình trạng API drift. |
| **P2-05** | P2 | **ĐÃ KHẮC PHỤC** | `d0ceb9e` | Chuẩn hóa hệ thống thuật ngữ song ngữ ưu tiên tiếng Việt (Vietnamese-first) kèm badge tiếng Anh phụ trợ trên toàn bộ navigation và header; tập trung các quy tắc layout CSS tokens. |
| **P2-06** | P2 | **ĐÃ KHẮC PHỤC** | `d0ceb9e` | Tái cấu trúc Information Architecture: phân tách rõ ràng nhóm "VẬN HÀNH CỐT LÕI (CORE)" (Catalog, Circulation, Inventory, Reservations) và "MỞ RỘNG PHÂN HỆ (EDITIONS)" (Education Members, Public Library & Finance). |
| **P3-01** | P3 | **ĐÃ KHẮC PHỤC** | `a8f38fe` | Sửa timing await async principal trong `frontend/tests/features/auth/user-profile.test.tsx`, triệt tiêu 100% React `act(...)` warnings. Vitest suite chạy 167/167 tests sạch sẽ không một cảnh báo. |
| **P3-02** | P3 | **ĐÃ KHẮC PHỤC** | `a8f38fe` | Chuẩn hóa các đường viền lệch tâm (accent border) trong `BookDetail.tsx` và `StatusHistoryView.tsx` sang border thẻ cân đối đồng bộ `border: 1px solid ${tokens.colors.border}` theo design tokens. |
| **P3-03** | P3 | **ĐÃ KHẮC PHỤC** | `a8f38fe` | Dọn sạch trailing whitespace và các dòng trống thừa cuối file; lệnh `git diff --check f54da53..HEAD` đạt kết quả 0 lỗi whitespace. |

### Bằng chứng chạy nghiệm thu thực tế (Live Execution Evidence)

1. **Backend Verification Suite:**
   - `python -m ruff format --check .`: `188 files already formatted` (Exit code 0).
   - `python -m ruff check .`: `All checks passed!` (Exit code 0).
   - `python -m mypy src`: `Success: no issues found in 85 source files` (Exit code 0).
   - `python -m pytest -q`: `358 passed, 53 skipped in 15.55s` (Exit code 0).
   - `python -m openapi_spec_validator ../contracts/openapi/v1.yaml`: `../contracts/openapi/v1.yaml: OK` (Exit code 0).
   - `python ../contracts/openapi/check_compatibility.py ../contracts/openapi/v1.yaml ../contracts/openapi/v1.yaml`: `OpenAPI compatibility check passed.` (Exit code 0).

2. **Frontend Quality Gate Suite:**
   - `npm run lint`: `eslint .` (Exit code 0, 0 errors, 0 warnings).
   - `npm run typecheck`: `tsc --noEmit` (Exit code 0, 0 errors).
   - `npm run contract:check`: `vitest run tests/shared/openapi-contract-parity.test.ts` (Exit code 0, 4 passed / 4 tests).
   - `npm test -- --reporter=dot`: `16 passed (16 files), 167 passed (167 tests)` (Exit code 0, 0 warnings).
   - `npm run build`: `tsc --noEmit && vite build` (Exit code 0, built in 879ms, bundle gzip 91.82 kB).

3. **Chrome DevTools Browser Smoke Test:**
   - Desktop Viewport (1440x900): `scrollWidth = 1425px <= innerWidth = 1440px` (Không có thanh cuộn ngang, primary navigation và desktop account menu hiển thị đầy đủ).
   - Mobile Viewport (375x812): `scrollWidth = 375px <= innerWidth = 375px` (Không có tràn ngang layout, menu drawer mở modal dialog có ARIA và focus trap, đóng mượt mà bằng phím `Escape`).
   - Clean Mount Check: Khi mở ứng dụng ở trạng thái chưa xác thực, không xuất hiện banner lỗi giả mạo (`alerts: []`, `hasErrorBanner: false`).
   - Focus Trapping Check: Mở Change Password Modal / User Profile Modal kích hoạt focus vào input đầu tiên, bẫy focus bàn phím bên trong dialog và đóng chuẩn xác khi nhấn `Escape`.
