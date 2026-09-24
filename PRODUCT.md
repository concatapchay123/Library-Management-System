# OpenLibraryOS Product Context & Operate-Mode UI Brief

## Product Overview & Vision

OpenLibraryOS là nền tảng vận hành thư viện mã nguồn mở cho trường học, đại học, trung tâm đào tạo, thư viện công cộng và thư viện tư nhân. Kiến trúc hệ thống bao gồm một backend core dùng chung cung cấp catalog, inventory, circulation, identity và audit; các edition bổ sung nghiệp vụ riêng biệt mà không làm bẩn core.

Mặt trước của hệ thống (Frontend) là một Single Page Application (SPA) xây dựng trên nền tảng React, TypeScript và Vite, giao tiếp độc lập với backend qua REST API `/api/v1` tuân theo chuẩn hợp đồng OpenAPI.

---

## Audience & Personas

Tất cả người dùng và vai trò trong hệ thống được xác định chính xác theo `DESIGN.md`:

1. **Platform Administrator**: Bootstrap và vận hành instance qua control plane/operational command riêng, không sử dụng tenant user API.
2. **Organization Administrator**: Cấu hình tenant, branding cơ bản, quản trị user và phân quyền (RBAC).
3. **Librarian (Thủ thư)**: Nhân sự vận hành chính hàng ngày; quản lý catalog, copies, locations, checkout, return và reservation.
4. **Student / Teacher**: Người mượn (borrowers) trong Education Edition gắn liền với profile học thuật.
5. **Member (Độc giả thành viên)**: Người mượn trong Public Library Edition gắn liền với membership plan và thanh toán.
6. **Contributor / Operator**: Nhà phát triển, kỹ sư triển khai và bảo trì nền tảng.

---

## Editions & Domain Capabilities

Theo `DESIGN.md`, sản phẩm bao gồm Core Platform và 2 edition chuyên biệt:

- **Core Platform**: Organization, identity, RBAC, catalog, inventory, circulation, reservation, notification và audit trail.
- **Education Edition**: Student, teacher, department, class, course, semester và policy mượn theo borrower profile.
- **Public Library Edition**: Member, membership plan, subscription, fine, payment và invoice.

---

## Operating Mode: "Operate-Mode"

Giao diện người dùng của OpenLibraryOS được thiết kế chuyên biệt cho chế độ vận hành thường nhật (**Operate-Mode**). 

### Đặc điểm của Operate-Mode:
- **Tập trung vào tác vụ cốt lõi**: Phục vụ các thao tác quầy lặp đi lặp lại với tần suất cao (quét mã barcode/ISBN, mượn sách siêu tốc, trả sách, kiểm tra vị trí bản sao trên giá kệ, tra cứu danh mục).
- **Phản hồi tức thì & tối ưu nhận thức**: Giao diện nhẹ, không có animation thừa thãi, render không phụ thuộc vào các cuộc gọi mạng chặn ban đầu, bố cục dữ liệu rõ nét dưới mọi điều kiện ánh sáng tại quầy thư viện.
- **Thân thiện với phần cứng phổ thông**: Hoạt động ổn định trên màn hình và máy trạm văn phòng phổ thông, bàn phím số/máy quét mã vạch và thiết bị ngoại vi tại quầy.

---

## The Minimum-Comprehension UI Rule

Quy tắc cốt lõi của UI Operate-Mode: **"Mọi màn hình, biểu mẫu và danh sách dữ liệu phải đạt mức độ dễ hiểu tối đa (minimum cognitive effort) — một thủ thư tình nguyện mới hoặc sinh viên có thể vận hành chính xác ngay từ lần đầu tiên mà không cần tài liệu hướng dẫn."**

### 5 Bất biến nhận thức bắt buộc:

1. **Jakob's Law (Quy ước quen thuộc trên hết)**:
   - Sử dụng các quy ước giao diện chuẩn mực: Logo góc trên dẫn về màn hình chính; điều hướng phân cấp trực quan; thanh tìm kiếm luôn có placeholder gợi ý cụ thể; trạng thái tài khoản ở góc trên bên phải; dialog/modal có nút đóng và hỗ trợ phím `Escape`.
   - Cấm thay đổi nghịch đảo vị trí các nút bấm tiêu chuẩn làm người dùng thao tác nhầm lẫn.

2. **Hick's Law (Tối giản lựa chọn & 01 Primary Action)**:
   - Trên mỗi màn hình, card nghiệp vụ hoặc modal thao tác: chỉ định duy nhất **01 Primary Action** (hành động chính yếu), các hành động khác phải là Secondary hoặc Ghost.
   - Giảm thiểu số lượng lựa chọn hiển thị cùng một lúc để tối đa hóa tốc độ phản xạ và xử lý của thủ thư.

3. **Law of Proximity (Định luật gần gũi Gestalt & Hệ thống Spacing phân tầng)**:
   - Khoảng cách thị giác phải phản ánh cấu trúc logic: Khoảng cách giữa nhãn (label) và ô nhập (input) luôn là $12px$; khoảng cách giữa các nhóm trường (group-to-group) luôn là $24px$; khoảng cách đến nút bấm gửi (form-to-submit) là $32px$ trở lên.
   - Nhóm dữ liệu liên quan phải nằm sát nhau; các trường không liên quan phải có khoảng cách phân định rõ ràng.

4. **Miller's Law (Kỹ thuật phân mảnh Chunking 7 ± 2)**:
   - Bất kỳ biểu mẫu nào vượt quá 5–7 trường phải được chia thành các nhóm logic có tiêu đề phân đoạn rõ ràng hoặc quy trình nhiều bước (stepper).
   - Mã định danh, số điện thoại, ISBN phải được định dạng theo cụm dễ quét mắt.

5. **Von Restorff Effect (Điểm nhấn thị giác độc tôn)**:
   - Mỗi ngữ cảnh chỉ có một tiêu điểm thị giác nổi bật nhất. Không cạnh tranh thị giác bằng nhiều nút màu rực rỡ ngang hàng.

### Bất biến về Màu sắc, Độ tương phản & Khả năng tiếp cận:

- **Tuyệt đối cấm Pure Black (`#000000`) và Pure White (`#ffffff`)**:
  - Nền sáng dùng trắng ngà/xám sáng dịu như `#f8fafc`, `#f4f4f5`, `#e7e9eb`.
  - Chữ tối dùng than chì sâu mềm mại như `#121212`, `#18181b`, `#242424`.
  - Lý do: Triệt tiêu hiện tượng lóa mắt, chói sáng và mỏi mắt khi thủ thư làm việc ca dài 8–10 tiếng trước màn hình máy tính.
- **Tiêu chuẩn tương phản WCAG AA**:
  - Mọi văn bản và phần tử điều khiển phải đạt tỷ lệ tương phản tối thiểu $4.5:1$ so với nền.
- **Bắt buộc Non-Color Status Cues (Chỉ báo trạng thái phi màu sắc)**:
  - Mọi trạng thái thông tin (Thành công, Cảnh báo, Nguy hiểm/Lỗi, Thông tin) không bao giờ được truyền tải duy nhất bằng màu sắc.
  - Bắt buộc luôn đi kèm nhãn chữ rõ nghĩa (Success, Warning, Danger, Info) và biểu tượng trực quan (icon).
  - Hành động phá hủy (xóa dữ liệu, hủy thẻ) bắt buộc sử dụng màu Đỏ cảnh báo (Danger Red) kèm hộp thoại xác nhận với động từ hành động cụ thể (`Delete` / `Keep`).
- **Visible Keyboard Focus (Chỉ báo tiêu điểm bàn phím rõ nét)**:
  - Mọi phần tử tương tác (button, input, select, link) bắt buộc có viền focus nổi bật (`outline: 2px solid #2563eb; outline-offset: 2px`) khi điều hướng bằng phím Tab.
- **Tỷ lệ đệm nút bấm 2:1**:
  - Đệm ngang gấp đôi đệm dọc ($Padding_X = 2 \times Padding_Y$), nhãn nút dạng Title Case (`Check Out`, `Add Book`, `Save Changes`).

---

## Product Scope Boundaries (V1)

Theo đúng quy định tại `DESIGN.md`, phạm vi V1 của OpenLibraryOS **không bao gồm**:
1. Microservices architecture (giữ vững kiến trúc Modular Monolith).
2. Mobile application (tập trung hoàn thiện Desktop/Web responsive SPA).
3. Recommendation engine (gợi ý sách AI/ML).
4. Full accounting system (chỉ xử lý fine/fee/payment cơ bản trong Public Library).
5. Managed multi-tenant SaaS control plane (chỉ hỗ trợ self-hosted deployment với SQL Server RLS).

Các capability nâng cao này chỉ được xem xét sau khi core circulation và cơ chế tenant isolation đạt độ ổn định tuyệt đối trong môi trường production.
