# OpenLibraryOS Frontend Package

Single Page Application (SPA) xây dựng trên nền tảng React 18, TypeScript và Vite, giao tiếp với backend core qua REST API `/api/v1` tuân theo chuẩn hợp đồng OpenAPI (`contracts/openapi/v1.yaml`).

## Architecture & Layout

Cấu trúc thư mục tuân thủ chặt chẽ `docs/architecture.md`:

```text
frontend/
├── package.json          # Dependencies & scripts
├── tsconfig.json         # Strict TypeScript configuration
├── vite.config.ts        # Vite + Vitest configuration
├── eslint.config.js      # ESLint 9 configuration
├── index.html            # HTML5 shell entrypoint
├── src/
│   ├── app/              # Root application bootstrap & providers
│   │   ├── App.tsx
│   │   └── ...
│   ├── features/         # Feature modules
│   │   ├── auth/
│   │   ├── catalog/
│   │   ├── circulation/
│   │   ├── education/
│   │   └── public-library/
│   ├── shared/           # Shared cross-cutting components & tokens
│   │   └── tokens/       # Foundational design token system
│   └── main.tsx          # Client entrypoint
└── tests/
    ├── setup.ts          # Test runner DOM matchers setup
    └── app/
        └── bootstrap.test.tsx
```

## Design System & Tokens

Module `src/shared/tokens/` cung cấp nền tảng token nhất quán phục vụ chế độ vận hành (Operate-Mode):
- **Spacing**: Thang lũy tiến (4px, 8px, 12px, 16px, 24px, 32px, 48px, 64px) kết hợp các khoảng cách ngữ nghĩa Gestalt (`labelToInput: 12px`, `groupToGroup: 24px`, `formToSubmit: 32px`).
- **Colors**: Tuyệt đối cấm pure white (`#ffffff`) và pure black (`#000000`). Độ tương phản text tối thiểu 4.5:1 (WCAG AA).
- **Status Cues**: Mọi trạng thái (Success, Warning, Danger, Info) luôn đi kèm chỉ báo phi màu sắc (biểu tượng icon + nhãn text).
- **Focus**: Chỉ báo bàn phím nổi bật (`2px solid #2563eb; outline-offset: 2px`).
- **Radius**: Hỗ trợ công thức bo góc lồng nhau: $R_{inner} = \max(0, R_{outer} - Padding)$ qua `calcNestedRadius`.
- **Button Whitespace**: Tỷ lệ vàng đệm nút bấm 2:1 ($Padding_X = 2 \times Padding_Y$).

## Development Lifecycle & Known Limits

- **Phase 0 & Foundation**: Thiết lập ranh giới kiến trúc (boundary), hợp đồng OpenAPI, product context tại `PRODUCT.md`, foundational design tokens và test tooling. Hiện tại chưa bao gồm navigation đầy đủ, màn hình đăng nhập hoặc API state caching (được lên kế hoạch tại FE-002 và các task kế tiếp).

## Deterministic Verification Commands

Mọi lệnh kiểm tra frontend được chuẩn hóa trong `package.json`:

```bash
# Chạy bộ test suite tập trung (Vitest)
npm run test -- --run tests/app/bootstrap.test.tsx

# Kiểm tra kiểu dữ liệu nghiêm ngặt (TypeScript strict mode)
npm run typecheck

# Rà soát cú pháp và quy chuẩn mã nguồn (ESLint)
npm run lint

# Biên dịch gói sản phẩm (Production build)
npm run build
```
