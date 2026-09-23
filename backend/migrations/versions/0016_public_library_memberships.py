"""Create public library membership entities and tenant-scoped relations with RLS.

Revision ID: 0016_public_library_memberships
Revises: 0015_education_entities
Create Date: 2026-09-23
"""

from alembic import op


revision = "0016_public_library_memberships"
down_revision = "0015_education_entities"
branch_labels = None
depends_on = None

_TABLES = [
    "public_library.membership_plans",
    "public_library.members",
    "public_library.subscriptions",
]


def _add_tenant_predicates(table_name: str) -> None:
    """Attach every data operation to the shared fail-closed tenant policy."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        f"ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
            f"ON {table_name} {operation}"
        )


def _drop_tenant_predicates(table_name: str) -> None:
    """Detach all predicates before dropping a tenant-owned table."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        f"DROP FILTER PREDICATE ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            f"DROP BLOCK PREDICATE ON {table_name} {operation}"
        )


def upgrade() -> None:
    """Create public library membership tables with composite tenant keys and RLS predicates."""
    # 1. membership_plans
    op.execute(
        "CREATE TABLE public_library.membership_plans ("
        "plan_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_membership_plans PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "code varchar(64) NOT NULL, "
        "name nvarchar(255) NOT NULL, "
        "description nvarchar(1024) NULL, "
        "max_active_loans int NOT NULL, "
        "duration_days int NOT NULL, "
        "price decimal(19,4) NOT NULL CONSTRAINT DF_public_library_plans_price DEFAULT 0.0000, "
        "currency varchar(3) NOT NULL CONSTRAINT DF_public_library_plans_currency DEFAULT 'USD', "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_plans_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_plans_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_public_library_plans_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_public_library_plans_org_plan UNIQUE (organization_id, plan_id), "
        "CONSTRAINT UQ_public_library_plans_org_code UNIQUE (organization_id, code), "
        "CONSTRAINT FK_public_library_plans_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id))"
    )
    _add_tenant_predicates("public_library.membership_plans")

    # 2. members
    op.execute(
        "CREATE TABLE public_library.members ("
        "member_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_members PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, "
        "member_number nvarchar(64) NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_members_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_members_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_public_library_members_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_public_library_members_org_member UNIQUE (organization_id, member_id), "
        "CONSTRAINT UQ_public_library_members_org_user UNIQUE (organization_id, user_id), "
        "CONSTRAINT UQ_public_library_members_org_number UNIQUE (organization_id, member_number), "
        "CONSTRAINT FK_public_library_members_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_members_user FOREIGN KEY (organization_id, user_id) REFERENCES core.users (organization_id, user_id))"
    )
    _add_tenant_predicates("public_library.members")

    # 3. subscriptions
    op.execute(
        "CREATE TABLE public_library.subscriptions ("
        "subscription_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_subscriptions PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "member_id uniqueidentifier NOT NULL, "
        "plan_id uniqueidentifier NOT NULL, "
        "starts_at datetime2 NOT NULL, "
        "ends_at datetime2 NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_subscriptions_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_subscriptions_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_public_library_subscriptions_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_public_library_subscriptions_dates CHECK (starts_at < ends_at), "
        "CONSTRAINT UQ_public_library_subscriptions_org_sub UNIQUE (organization_id, subscription_id), "
        "CONSTRAINT FK_public_library_subscriptions_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_subscriptions_member FOREIGN KEY (organization_id, member_id) REFERENCES public_library.members (organization_id, member_id), "
        "CONSTRAINT FK_public_library_subscriptions_plan FOREIGN KEY (organization_id, plan_id) REFERENCES public_library.membership_plans (organization_id, plan_id))"
    )
    _add_tenant_predicates("public_library.subscriptions")

    # Composite tenant indexes
    op.execute(
        "CREATE INDEX IX_public_library_subscriptions_member_status "
        "ON public_library.subscriptions (organization_id, member_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_members_user "
        "ON public_library.members (organization_id, user_id)"
    )


def downgrade() -> None:
    """Detach RLS predicates and drop public library membership tables in reverse dependency order."""
    op.execute("DROP INDEX IX_public_library_members_user ON public_library.members")
    op.execute(
        "DROP INDEX IX_public_library_subscriptions_member_status ON public_library.subscriptions"
    )
    for table_name in reversed(_TABLES):
        _drop_tenant_predicates(table_name)
        op.execute(f"DROP TABLE {table_name}")
