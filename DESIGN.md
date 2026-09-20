# OpenLibraryOS Product Design

## Vision

OpenLibraryOS là nền tảng vận hành thư viện mã nguồn mở cho trường học, đại học, trung tâm đào tạo, thư viện công cộng và thư viện tư nhân. Một backend core dùng chung cung cấp catalog, inventory, circulation, identity và audit; các edition bổ sung nghiệp vụ riêng mà không làm bẩn core.

## Users

- Platform administrator: bootstrap và vận hành instance.
- Organization administrator: cấu hình tenant, branding, user và permissions.
- Librarian: quản lý catalog, copies, locations, checkout, return và reservation.
- Student/teacher: người mượn trong Education edition.
- Member: người mượn trong Public Library edition.
- Contributor/operator: phát triển, deploy và bảo trì platform.

## Editions

- Core Platform: organization, identity, RBAC, catalog, inventory, circulation, reservation, notification và audit.
- Education Edition: student, teacher, department, class, course, semester và policy theo borrower profile.
- Public Library Edition: member, membership plan, subscription, fine, payment và invoice.

## Architecture principles

- Modular monolith trước, service extraction khi có bằng chứng.
- API-first contract với React frontend độc lập.
- Một SQL Server database với schema boundaries và SQL Server Row-Level Security.
- Service layer là nơi điều phối use case; database constraint/RLS là lớp bảo vệ cuối.
- Mọi thay đổi quan trọng phải có migration, test và audit trail.

## Product boundaries

V1 không bao gồm microservices, mobile application, recommendation engine, full accounting hoặc managed SaaS control plane. Các capability này chỉ được thêm sau khi core circulation và tenant isolation ổn định trong production.
