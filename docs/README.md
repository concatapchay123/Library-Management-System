# OpenLibraryOS documentation

Quyết định xuyên suốt về tenant discovery, platform control plane, database identity/RLS, audit/outbox, payment và retention nằm tại [foundational-decisions.md](foundational-decisions.md). Tài liệu đó được ưu tiên khi một quy tắc chuyên biệt mâu thuẫn.

Đây là source of truth cho kiến trúc, database, API, security, deployment, development, testing và roadmap. Tài liệu dùng tiếng Việt; tên module, endpoint, table và code identifier dùng tiếng Anh để nhất quán với source code.

Mọi thay đổi làm thay đổi public interface, tenant boundary hoặc phase checkpoint phải cập nhật tài liệu liên quan trước khi merge code.
