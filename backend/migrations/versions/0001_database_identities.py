"""Create the SQL Server schema and runtime identity permission baseline.

Revision ID: 0001_database_identities
Revises:
Create Date: 2026-09-21
"""

from alembic import context, op


revision = "0001_database_identities"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create empty application schemas and constrained runtime grants."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute("CREATE SCHEMA core")
    op.execute("CREATE SCHEMA ops")
    op.execute("CREATE SCHEMA education")
    op.execute("CREATE SCHEMA public_library")
    op.execute(
        "CREATE TABLE core.runtime_permission_guard (guard_id int NOT NULL PRIMARY KEY)"
    )
    op.execute(
        "CREATE FUNCTION core.runtime_permission_guard_predicate "
        "(@guard_id int) RETURNS TABLE WITH SCHEMABINDING "
        "AS RETURN SELECT CAST(1 AS bit) AS predicate_result"
    )
    op.execute(
        "CREATE SECURITY POLICY core.runtime_permission_guard_policy "
        "ADD FILTER PREDICATE core.runtime_permission_guard_predicate(guard_id) "
        "ON core.runtime_permission_guard WITH (STATE = ON)"
    )
    for schema_name in ("core", "ops", "education", "public_library"):
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::"
            f"{schema_name} TO [{runtime_login}]"
        )


def downgrade() -> None:
    """Remove only this baseline's empty schema objects in reverse order."""
    op.execute("DROP SECURITY POLICY core.runtime_permission_guard_policy")
    op.execute("DROP FUNCTION core.runtime_permission_guard_predicate")
    op.execute("DROP TABLE core.runtime_permission_guard")
    op.execute("DROP SCHEMA public_library")
    op.execute("DROP SCHEMA education")
    op.execute("DROP SCHEMA ops")
    op.execute("DROP SCHEMA core")
