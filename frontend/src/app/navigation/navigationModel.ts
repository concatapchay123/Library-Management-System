export interface NavigationItem {
  id: string;
  label: string;
  labelVi: string;
  href: string;
  description: string;
  descriptionVi: string;
}

/**
 * ARCHITECTURE INVARIANT:
 * Navigation links describe available product workspaces using human-readable product language.
 * Navigation visibility is strictly decoupled from authorization:
 * - Hiding or displaying a navigation link MUST NEVER be treated as an access control or security boundary.
 * - All authorization, role-based access control (RBAC), and tenant boundaries are enforced
 *   authoritatively by the backend domain/application services and database policies.
 */
export const navigationItems: readonly NavigationItem[] = [
  {
    id: 'catalog',
    label: 'Catalog',
    labelVi: 'Tra cứu sách',
    href: '#/catalog',
    description: 'Search bibliographic records, books, authors, and availability.',
    descriptionVi: 'Tìm kiếm thư mục sách, tác giả và kiểm tra tình trạng sách.',
  },
  {
    id: 'circulation',
    label: 'Circulation',
    labelVi: 'Mượn / Trả',
    href: '#/circulation',
    description: 'Circulation desk operations: checkout, check-in, loans, and returns.',
    descriptionVi: 'Quầy lưu hành: mượn sách, trả sách và quản lý phiếu mượn.',
  },
  {
    id: 'inventory',
    label: 'Inventory',
    labelVi: 'Kho sách',
    href: '#/inventory',
    description: 'Physical copies, shelf locations, and barcode status management.',
    descriptionVi: 'Quản lý bản sao vật lý, vị trí giá kệ và mã vạch sách.',
  },
  {
    id: 'education',
    label: 'Education & Members',
    labelVi: 'Độc giả & Học đường',
    href: '#/education',
    description: 'Borrower records, student & teacher profiles, academic relationships, and loan policies.',
    descriptionVi: 'Hồ sơ độc giả, học sinh & giáo viên và chính sách mượn.',
  },
  {
    id: 'reservations',
    label: 'Reservations',
    labelVi: 'Đặt trước',
    href: '#/reservations',
    description: 'Hold queue priorities, reservation allocations, and pickup notifications.',
    descriptionVi: 'Hàng đợi đặt trước, phân bổ bản sao và thông báo nhận sách.',
  },
  {
    id: 'public-library',
    label: 'Public Library & Finance',
    labelVi: 'Thư viện & Tài chính',
    href: '#/public-library',
    description: 'Public library memberships, subscription policies, fines, payments, and invoices.',
    descriptionVi: 'Thành viên thư viện công, phí phạt quá hạn, thanh toán và hóa đơn.',
  },
];
