"""Seed demo organization, user, role, and catalog data for live browser verification."""

from __future__ import annotations

import os
from uuid import uuid4
from sqlalchemy import create_engine, text
from openlibrary.modules.core.domain.passwords import PasswordService


def seed() -> None:
    migration_url = os.environ["DATABASE_MIGRATION_URL"]
    engine = create_engine(migration_url)

    org_id = str(uuid4())
    user_id = str(uuid4())
    profile_id = str(uuid4())
    role_id = str(uuid4())
    book_id = str(uuid4())

    pw_hash = PasswordService().hash("correct-horse-battery-staple")

    permissions = [
        "catalog.manage",
        "catalog.read",
        "catalog.write",
        "circulation.manage",
        "circulation.read",
        "circulation.write",
        "patron.manage",
        "invoice.manage",
        "reports.view",
    ]

    with engine.begin() as conn:
        # Check if org already exists
        existing_org = conn.execute(
            text(
                "SELECT organization_id FROM core.organizations WHERE slug = 'campus-central'"
            )
        ).scalar()

        if existing_org:
            print("Demo data already seeded.")
            return

        conn.execute(
            text(
                "INSERT INTO core.organizations (organization_id, name, slug, organization_type, status, timezone, settings_json) "
                "VALUES (:org_id, 'Central Campus Library', 'campus-central', 'public_library', 'active', 'Asia/Ho_Chi_Minh', '{}')"
            ),
            {"org_id": org_id},
        )

        conn.execute(
            text(
                "INSERT INTO core.users (user_id, organization_id, email, password_hash, status) "
                "VALUES (:user_id, :org_id, 'librarian@example.test', :pw_hash, 'active')"
            ),
            {"user_id": user_id, "org_id": org_id, "pw_hash": pw_hash},
        )

        conn.execute(
            text(
                "INSERT INTO core.user_profiles (profile_id, organization_id, user_id, display_name, phone) "
                "VALUES (:profile_id, :org_id, :user_id, 'Chief Librarian', '+84901234567')"
            ),
            {"profile_id": profile_id, "org_id": org_id, "user_id": user_id},
        )

        conn.execute(
            text(
                "INSERT INTO core.roles (role_id, organization_id, name) "
                "VALUES (:role_id, :org_id, 'Librarian')"
            ),
            {"role_id": role_id, "org_id": org_id},
        )

        for code in permissions:
            perm_id = str(uuid4())
            conn.execute(
                text(
                    "INSERT INTO core.permissions (permission_id, organization_id, code) "
                    "VALUES (:perm_id, :org_id, :code)"
                ),
                {"perm_id": perm_id, "org_id": org_id, "code": code},
            )
            conn.execute(
                text(
                    "INSERT INTO core.role_permissions (organization_id, role_id, permission_id) "
                    "VALUES (:org_id, :role_id, :perm_id)"
                ),
                {"org_id": org_id, "role_id": role_id, "perm_id": perm_id},
            )

        conn.execute(
            text(
                "INSERT INTO core.user_roles (organization_id, user_id, role_id) "
                "VALUES (:org_id, :user_id, :role_id)"
            ),
            {"org_id": org_id, "user_id": user_id, "role_id": role_id},
        )

        conn.execute(
            text(
                "INSERT INTO core.books (book_id, organization_id, title, title_sort_key, isbn, authors_json, published_year) "
                "VALUES (:book_id, :org_id, 'Clean Architecture: A Craftsman Guide', 'clean architecture a craftsman guide', '9780134494166', '[\"Robert C. Martin\"]', 2017)"
            ),
            {"book_id": book_id, "org_id": org_id},
        )

    print(
        f"Successfully seeded demo database for org {org_id} (campus-central) and user {user_id}"
    )


if __name__ == "__main__":
    seed()
