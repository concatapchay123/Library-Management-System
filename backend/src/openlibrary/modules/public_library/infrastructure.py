"""SQL Server infrastructure store implementation for public library edition."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.public_library.application import (
    DEFAULT_BASIC_DURATION_DAYS,
    DEFAULT_BASIC_MAX_ACTIVE_LOANS,
    DEFAULT_PREMIUM_DURATION_DAYS,
    DEFAULT_PREMIUM_MAX_ACTIVE_LOANS,
    PublicLibraryStore,
)
from openlibrary.modules.public_library.domain import (
    DuplicateIdentifierError,
    Fine,
    InvalidSubscriptionDatesError,
    Invoice,
    InvoiceLine,
    Member,
    MembershipPlan,
    Payment,
    PaymentAllocation,
    ProfileAlreadyExistsError,
    Subscription,
)


class SqlServerPublicLibraryStore(PublicLibraryStore):
    """Production SQL Server persistence store enforcing tenant boundary via RLS context."""

    def __init__(
        self,
        database_url: str,
        tenant_context: SqlServerTenantContext | None = None,
    ) -> None:
        self._database_url = database_url
        self._tenant_context = tenant_context

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        """Check whether the public library edition is active for the organization."""
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT organization_type, settings_json "
                        "FROM core.organizations "
                        "WHERE organization_id = :org_id"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return False
        org_type = str(row["organization_type"]).strip().lower()
        if org_type in ("public_library", "public"):
            return True
        try:
            settings = json.loads(str(row["settings_json"]))
            if not isinstance(settings, dict):
                return False
            if settings.get("public_library_enabled") is True:
                return True
            editions = settings.get("editions")
            if isinstance(editions, dict) and (
                editions.get("public_library") is True or editions.get("public") is True
            ):
                return True
            if isinstance(editions, list) and (
                "public_library" in editions or "public" in editions
            ):
                return True
            enabled_editions = settings.get("enabled_editions")
            if isinstance(enabled_editions, list) and (
                "public_library" in enabled_editions or "public" in enabled_editions
            ):
                return True
        except (ValueError, TypeError):
            return False
        return False

    # --- Members ---

    def create_member(self, member: Member) -> Member:
        with self._tenant_connection(member.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO public_library.members ("
                        "member_id, organization_id, user_id, member_number, status, created_at, updated_at"
                        ") VALUES ("
                        ":member_id, :organization_id, :user_id, :member_number, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "member_id": str(member.member_id),
                        "organization_id": str(member.organization_id),
                        "user_id": str(member.user_id),
                        "member_number": member.member_number,
                        "status": member.status,
                        "created_at": member.created_at,
                        "updated_at": member.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_public_library_members_org_user" in msg:
                    raise ProfileAlreadyExistsError(
                        f"User {member.user_id} already has a member profile in organization {member.organization_id}"
                    ) from err
                if "uq_public_library_members_org_number" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        f"Member number '{member.member_number}' already exists in organization {member.organization_id}"
                    ) from err
                raise
        return member

    def get_member(self, organization_id: UUID, member_id: UUID) -> Member | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT member_id, organization_id, user_id, member_number, status, created_at, updated_at "
                        "FROM public_library.members "
                        "WHERE organization_id = :org_id AND member_id = :member_id"
                    ),
                    {"org_id": str(organization_id), "member_id": str(member_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _member_from_row(row)

    def get_member_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Member | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT member_id, organization_id, user_id, member_number, status, created_at, updated_at "
                        "FROM public_library.members "
                        "WHERE organization_id = :org_id AND user_id = :user_id"
                    ),
                    {"org_id": str(organization_id), "user_id": str(user_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _member_from_row(row)

    def get_member_by_number(
        self, organization_id: UUID, member_number: str
    ) -> Member | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT member_id, organization_id, user_id, member_number, status, created_at, updated_at "
                        "FROM public_library.members "
                        "WHERE organization_id = :org_id AND member_number = :number"
                    ),
                    {"org_id": str(organization_id), "number": member_number},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _member_from_row(row)

    def list_members(self, organization_id: UUID) -> list[Member]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT member_id, organization_id, user_id, member_number, status, created_at, updated_at "
                        "FROM public_library.members "
                        "WHERE organization_id = :org_id "
                        "ORDER BY created_at DESC"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_member_from_row(r) for r in rows]

    def update_member(self, member: Member) -> Member:
        with self._tenant_connection(member.organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE public_library.members "
                    "SET status = :status, updated_at = :updated_at "
                    "WHERE organization_id = :org_id AND member_id = :member_id"
                ),
                {
                    "status": member.status,
                    "updated_at": member.updated_at,
                    "org_id": str(member.organization_id),
                    "member_id": str(member.member_id),
                },
            )
        return member

    # --- Membership Plans ---

    def create_plan(self, plan: MembershipPlan) -> MembershipPlan:
        with self._tenant_connection(plan.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO public_library.membership_plans ("
                        "plan_id, organization_id, code, name, description, max_active_loans, "
                        "duration_days, price, currency, status, created_at, updated_at"
                        ") VALUES ("
                        ":plan_id, :organization_id, :code, :name, :description, :max_active_loans, "
                        ":duration_days, :price, :currency, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "plan_id": str(plan.plan_id),
                        "organization_id": str(plan.organization_id),
                        "code": plan.code,
                        "name": plan.name,
                        "description": plan.description,
                        "max_active_loans": plan.max_active_loans,
                        "duration_days": plan.duration_days,
                        "price": plan.price,
                        "currency": plan.currency,
                        "status": plan.status,
                        "created_at": plan.created_at,
                        "updated_at": plan.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_public_library_plans_org_code" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        f"Plan code '{plan.code}' already exists in organization {plan.organization_id}"
                    ) from err
                raise
        return plan

    def get_plan(self, organization_id: UUID, plan_id: UUID) -> MembershipPlan | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT plan_id, organization_id, code, name, description, max_active_loans, "
                        "duration_days, price, currency, status, created_at, updated_at "
                        "FROM public_library.membership_plans "
                        "WHERE organization_id = :org_id AND plan_id = :plan_id"
                    ),
                    {"org_id": str(organization_id), "plan_id": str(plan_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _plan_from_row(row)

    def get_plan_by_code(
        self, organization_id: UUID, code: str
    ) -> MembershipPlan | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT plan_id, organization_id, code, name, description, max_active_loans, "
                        "duration_days, price, currency, status, created_at, updated_at "
                        "FROM public_library.membership_plans "
                        "WHERE organization_id = :org_id AND code = :code"
                    ),
                    {"org_id": str(organization_id), "code": code.strip().lower()},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _plan_from_row(row)

    def list_plans(
        self, organization_id: UUID, status: str | None = None
    ) -> list[MembershipPlan]:
        query = (
            "SELECT plan_id, organization_id, code, name, description, max_active_loans, "
            "duration_days, price, currency, status, created_at, updated_at "
            "FROM public_library.membership_plans "
            "WHERE organization_id = :org_id"
        )
        params: dict[str, Any] = {"org_id": str(organization_id)}
        if status is not None:
            query += " AND status = :status"
            params["status"] = status
        query += " ORDER BY created_at ASC"

        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [_plan_from_row(r) for r in rows]

    def update_plan(self, plan: MembershipPlan) -> MembershipPlan:
        with self._tenant_connection(plan.organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE public_library.membership_plans "
                    "SET name = :name, description = :description, "
                    "max_active_loans = :max_active_loans, duration_days = :duration_days, "
                    "price = :price, currency = :currency, status = :status, updated_at = :updated_at "
                    "WHERE organization_id = :org_id AND plan_id = :plan_id"
                ),
                {
                    "name": plan.name,
                    "description": plan.description,
                    "max_active_loans": plan.max_active_loans,
                    "duration_days": plan.duration_days,
                    "price": plan.price,
                    "currency": plan.currency,
                    "status": plan.status,
                    "updated_at": plan.updated_at,
                    "org_id": str(plan.organization_id),
                    "plan_id": str(plan.plan_id),
                },
            )
        return plan

    def seed_default_plans(self, organization_id: UUID) -> list[MembershipPlan]:
        """Insert standard Basic and Premium plans if they do not exist for the organization."""
        now = datetime.now(timezone.utc)
        basic_id = uuid4()
        premium_id = uuid4()

        with self._tenant_connection(organization_id) as connection:
            connection.execute(
                text(
                    "MERGE public_library.membership_plans AS target "
                    "USING (VALUES "
                    "  (:basic_id, :org_id, 'basic', 'Basic Membership', "
                    "   'Standard membership plan with basic borrowing limits', "
                    "   :basic_loans, :basic_days, CAST(0.0000 AS decimal(19,4)), 'USD', 'active', :now1, :now2), "
                    "  (:premium_id, :org_id, 'premium', 'Premium Membership', "
                    "   'Extended membership plan with expanded limits and checkout duration', "
                    "   :premium_loans, :premium_days, CAST(0.0000 AS decimal(19,4)), 'USD', 'active', :now3, :now4) "
                    ") AS src (plan_id, organization_id, code, name, description, max_active_loans, "
                    "          duration_days, price, currency, status, created_at, updated_at) "
                    "ON target.organization_id = src.organization_id AND target.code = src.code "
                    "WHEN NOT MATCHED THEN "
                    "  INSERT (plan_id, organization_id, code, name, description, max_active_loans, "
                    "          duration_days, price, currency, status, created_at, updated_at) "
                    "  VALUES (src.plan_id, src.organization_id, src.code, src.name, src.description, "
                    "          src.max_active_loans, src.duration_days, src.price, src.currency, "
                    "          src.status, src.created_at, src.updated_at);"
                ),
                {
                    "basic_id": str(basic_id),
                    "premium_id": str(premium_id),
                    "org_id": str(organization_id),
                    "basic_loans": DEFAULT_BASIC_MAX_ACTIVE_LOANS,
                    "basic_days": DEFAULT_BASIC_DURATION_DAYS,
                    "premium_loans": DEFAULT_PREMIUM_MAX_ACTIVE_LOANS,
                    "premium_days": DEFAULT_PREMIUM_DURATION_DAYS,
                    "now1": now,
                    "now2": now,
                    "now3": now,
                    "now4": now,
                },
            )
            rows = (
                connection.execute(
                    text(
                        "SELECT plan_id, organization_id, code, name, description, max_active_loans, "
                        "duration_days, price, currency, status, created_at, updated_at "
                        "FROM public_library.membership_plans "
                        "WHERE organization_id = :org_id AND code IN ('basic', 'premium') "
                        "ORDER BY code ASC"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_plan_from_row(r) for r in rows]

    # --- Subscriptions ---

    def create_subscription(self, subscription: Subscription) -> Subscription:
        with self._tenant_connection(subscription.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO public_library.subscriptions ("
                        "subscription_id, organization_id, member_id, plan_id, "
                        "starts_at, ends_at, status, created_at, updated_at"
                        ") VALUES ("
                        ":subscription_id, :organization_id, :member_id, :plan_id, "
                        ":starts_at, :ends_at, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "subscription_id": str(subscription.subscription_id),
                        "organization_id": str(subscription.organization_id),
                        "member_id": str(subscription.member_id),
                        "plan_id": str(subscription.plan_id),
                        "starts_at": subscription.starts_at,
                        "ends_at": subscription.ends_at,
                        "status": subscription.status,
                        "created_at": subscription.created_at,
                        "updated_at": subscription.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "ck_public_library_subscriptions_dates" in msg:
                    raise InvalidSubscriptionDatesError(
                        "Subscription ends_at must be strictly after starts_at"
                    ) from err
                raise
        return subscription

    def get_subscription(
        self, organization_id: UUID, subscription_id: UUID
    ) -> Subscription | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT subscription_id, organization_id, member_id, plan_id, "
                        "starts_at, ends_at, status, created_at, updated_at "
                        "FROM public_library.subscriptions "
                        "WHERE organization_id = :org_id AND subscription_id = :subscription_id"
                    ),
                    {
                        "org_id": str(organization_id),
                        "subscription_id": str(subscription_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _subscription_from_row(row)

    def list_subscriptions(
        self,
        organization_id: UUID,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Subscription]:
        query = (
            "SELECT subscription_id, organization_id, member_id, plan_id, "
            "starts_at, ends_at, status, created_at, updated_at "
            "FROM public_library.subscriptions "
            "WHERE organization_id = :org_id"
        )
        params: dict[str, Any] = {"org_id": str(organization_id)}
        if member_id is not None:
            query += " AND member_id = :member_id"
            params["member_id"] = str(member_id)
        if status is not None:
            query += " AND status = :status"
            params["status"] = status
        query += " ORDER BY created_at DESC"

        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [_subscription_from_row(r) for r in rows]

    def get_active_subscription_for_member(
        self, organization_id: UUID, member_id: UUID, as_of: datetime
    ) -> Subscription | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT TOP 1 subscription_id, organization_id, member_id, plan_id, "
                        "starts_at, ends_at, status, created_at, updated_at "
                        "FROM public_library.subscriptions "
                        "WHERE organization_id = :org_id AND member_id = :member_id "
                        "AND status = 'active' AND starts_at <= :as_of AND ends_at > :as_of "
                        "ORDER BY ends_at DESC"
                    ),
                    {
                        "org_id": str(organization_id),
                        "member_id": str(member_id),
                        "as_of": as_of,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _subscription_from_row(row)

    def update_subscription(self, subscription: Subscription) -> Subscription:
        with self._tenant_connection(subscription.organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE public_library.subscriptions "
                    "SET status = :status, updated_at = :updated_at "
                    "WHERE organization_id = :org_id AND subscription_id = :sub_id"
                ),
                {
                    "status": subscription.status,
                    "updated_at": subscription.updated_at,
                    "org_id": str(subscription.organization_id),
                    "sub_id": str(subscription.subscription_id),
                },
            )
        return subscription

    # --- Fines ---

    def create_fine(self, fine: Fine) -> Fine:
        with self._tenant_connection(fine.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO public_library.fines ("
                    "fine_id, organization_id, member_id, loan_id, amount, currency, status, reason, assessed_at, created_at, updated_at"
                    ") VALUES ("
                    ":fine_id, :org_id, :member_id, :loan_id, :amount, :currency, :status, :reason, :assessed_at, :created_at, :updated_at"
                    ")"
                ),
                {
                    "fine_id": str(fine.fine_id),
                    "org_id": str(fine.organization_id),
                    "member_id": str(fine.member_id),
                    "loan_id": str(fine.loan_id) if fine.loan_id else None,
                    "amount": fine.amount,
                    "currency": fine.currency,
                    "status": fine.status,
                    "reason": fine.reason,
                    "assessed_at": fine.assessed_at,
                    "created_at": fine.created_at,
                    "updated_at": fine.updated_at,
                },
            )
        return fine

    def get_fine(self, organization_id: UUID, fine_id: UUID) -> Fine | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT fine_id, organization_id, member_id, loan_id, amount, currency, status, reason, assessed_at, created_at, updated_at "
                        "FROM public_library.fines "
                        "WHERE organization_id = :org_id AND fine_id = :fine_id"
                    ),
                    {"org_id": str(organization_id), "fine_id": str(fine_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _fine_from_row(row)

    def list_fines(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        loan_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Fine]:
        clauses = ["organization_id = :org_id"]
        params: dict[str, Any] = {"org_id": str(organization_id)}
        if member_id is not None:
            clauses.append("member_id = :member_id")
            params["member_id"] = str(member_id)
        if loan_id is not None:
            clauses.append("loan_id = :loan_id")
            params["loan_id"] = str(loan_id)
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status

        sql = (
            "SELECT fine_id, organization_id, member_id, loan_id, amount, currency, status, reason, assessed_at, created_at, updated_at "
            "FROM public_library.fines "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(sql), params).mappings().all()
        return [_fine_from_row(r) for r in rows]

    def update_fine(self, fine: Fine) -> Fine:
        with self._tenant_connection(fine.organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE public_library.fines "
                    "SET status = :status, reason = :reason, updated_at = :updated_at "
                    "WHERE organization_id = :org_id AND fine_id = :fine_id"
                ),
                {
                    "status": fine.status,
                    "reason": fine.reason,
                    "updated_at": fine.updated_at,
                    "org_id": str(fine.organization_id),
                    "fine_id": str(fine.fine_id),
                },
            )
        return fine

    # --- Invoices ---

    def create_invoice(self, invoice: Invoice, lines: list[InvoiceLine]) -> Invoice:
        with self._tenant_connection(invoice.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO public_library.invoices ("
                    "invoice_id, organization_id, member_id, invoice_number, subtotal, tax, total, currency, status, issued_at, due_at, created_at, updated_at"
                    ") VALUES ("
                    ":invoice_id, :org_id, :member_id, :invoice_number, :subtotal, :tax, :total, :currency, :status, :issued_at, :due_at, :created_at, :updated_at"
                    ")"
                ),
                {
                    "invoice_id": str(invoice.invoice_id),
                    "org_id": str(invoice.organization_id),
                    "member_id": str(invoice.member_id),
                    "invoice_number": invoice.invoice_number,
                    "subtotal": invoice.subtotal,
                    "tax": invoice.tax,
                    "total": invoice.total,
                    "currency": invoice.currency,
                    "status": invoice.status,
                    "issued_at": invoice.issued_at,
                    "due_at": invoice.due_at,
                    "created_at": invoice.created_at,
                    "updated_at": invoice.updated_at,
                },
            )
            for line in lines:
                connection.execute(
                    text(
                        "INSERT INTO public_library.invoice_lines ("
                        "invoice_line_id, organization_id, invoice_id, line_number, description, quantity, unit_price, amount, fine_id, created_at"
                        ") VALUES ("
                        ":line_id, :org_id, :inv_id, :line_number, :description, :quantity, :unit_price, :amount, :fine_id, :created_at"
                        ")"
                    ),
                    {
                        "line_id": str(line.invoice_line_id),
                        "org_id": str(line.organization_id),
                        "inv_id": str(line.invoice_id),
                        "line_number": line.line_number,
                        "description": line.description,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                        "amount": line.amount,
                        "fine_id": str(line.fine_id) if line.fine_id else None,
                        "created_at": line.created_at,
                    },
                )
        return invoice

    def get_invoice(self, organization_id: UUID, invoice_id: UUID) -> Invoice | None:
        with self._tenant_connection(organization_id) as connection:
            inv_row = (
                connection.execute(
                    text(
                        "SELECT invoice_id, organization_id, member_id, invoice_number, subtotal, tax, total, currency, status, issued_at, due_at, created_at, updated_at "
                        "FROM public_library.invoices "
                        "WHERE organization_id = :org_id AND invoice_id = :inv_id"
                    ),
                    {"org_id": str(organization_id), "inv_id": str(invoice_id)},
                )
                .mappings()
                .one_or_none()
            )
            if inv_row is None:
                return None
            line_rows = (
                connection.execute(
                    text(
                        "SELECT invoice_line_id, organization_id, invoice_id, line_number, description, quantity, unit_price, amount, fine_id, created_at "
                        "FROM public_library.invoice_lines "
                        "WHERE organization_id = :org_id AND invoice_id = :inv_id "
                        "ORDER BY line_number ASC"
                    ),
                    {"org_id": str(organization_id), "inv_id": str(invoice_id)},
                )
                .mappings()
                .all()
            )
        lines = [_invoice_line_from_row(r) for r in line_rows]
        return _invoice_from_row(inv_row, lines)

    def list_invoices(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Invoice]:
        clauses = ["organization_id = :org_id"]
        params: dict[str, Any] = {"org_id": str(organization_id)}
        if member_id is not None:
            clauses.append("member_id = :member_id")
            params["member_id"] = str(member_id)
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status

        sql = (
            "SELECT invoice_id, organization_id, member_id, invoice_number, subtotal, tax, total, currency, status, issued_at, due_at, created_at, updated_at "
            "FROM public_library.invoices "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(sql), params).mappings().all()
            result: list[Invoice] = []
            for r in rows:
                inv_id = str(r["invoice_id"])
                line_rows = (
                    connection.execute(
                        text(
                            "SELECT invoice_line_id, organization_id, invoice_id, line_number, description, quantity, unit_price, amount, fine_id, created_at "
                            "FROM public_library.invoice_lines "
                            "WHERE organization_id = :org_id AND invoice_id = :inv_id "
                            "ORDER BY line_number ASC"
                        ),
                        {"org_id": str(organization_id), "inv_id": inv_id},
                    )
                    .mappings()
                    .all()
                )
                lines = [_invoice_line_from_row(lr) for lr in line_rows]
                result.append(_invoice_from_row(r, lines))
        return result

    def update_invoice(self, invoice: Invoice) -> Invoice:
        with self._tenant_connection(invoice.organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE public_library.invoices "
                    "SET status = :status, updated_at = :updated_at "
                    "WHERE organization_id = :org_id AND invoice_id = :inv_id"
                ),
                {
                    "status": invoice.status,
                    "updated_at": invoice.updated_at,
                    "org_id": str(invoice.organization_id),
                    "inv_id": str(invoice.invoice_id),
                },
            )
        return invoice

    # --- Payments ---

    def create_payment(self, payment: Payment) -> Payment:
        with self._tenant_connection(payment.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO public_library.payments ("
                    "payment_id, organization_id, member_id, amount, currency, provider, provider_reference, provider_event_id, status, paid_at, created_at, updated_at"
                    ") VALUES ("
                    ":payment_id, :org_id, :member_id, :amount, :currency, :provider, :provider_reference, :provider_event_id, :status, :paid_at, :created_at, :updated_at"
                    ")"
                ),
                {
                    "payment_id": str(payment.payment_id),
                    "org_id": str(payment.organization_id),
                    "member_id": str(payment.member_id),
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "provider": payment.provider,
                    "provider_reference": payment.provider_reference,
                    "provider_event_id": payment.provider_event_id,
                    "status": payment.status,
                    "paid_at": payment.paid_at,
                    "created_at": payment.created_at,
                    "updated_at": payment.updated_at,
                },
            )
        return payment

    def get_payment(self, organization_id: UUID, payment_id: UUID) -> Payment | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT payment_id, organization_id, member_id, amount, currency, provider, provider_reference, provider_event_id, status, paid_at, created_at, updated_at "
                        "FROM public_library.payments "
                        "WHERE organization_id = :org_id AND payment_id = :payment_id"
                    ),
                    {"org_id": str(organization_id), "payment_id": str(payment_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _payment_from_row(row)

    def list_payments(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Payment]:
        clauses = ["organization_id = :org_id"]
        params: dict[str, Any] = {"org_id": str(organization_id)}
        if member_id is not None:
            clauses.append("member_id = :member_id")
            params["member_id"] = str(member_id)
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status

        sql = (
            "SELECT payment_id, organization_id, member_id, amount, currency, provider, provider_reference, provider_event_id, status, paid_at, created_at, updated_at "
            "FROM public_library.payments "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(sql), params).mappings().all()
        return [_payment_from_row(r) for r in rows]

    def update_payment(self, payment: Payment) -> Payment:
        with self._tenant_connection(payment.organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE public_library.payments "
                    "SET status = :status, paid_at = :paid_at, updated_at = :updated_at "
                    "WHERE organization_id = :org_id AND payment_id = :payment_id"
                ),
                {
                    "status": payment.status,
                    "paid_at": payment.paid_at,
                    "updated_at": payment.updated_at,
                    "org_id": str(payment.organization_id),
                    "payment_id": str(payment.payment_id),
                },
            )
        return payment

    # --- Allocations ---

    def create_allocation(self, allocation: PaymentAllocation) -> PaymentAllocation:
        with self._tenant_connection(allocation.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO public_library.payment_allocations ("
                    "allocation_id, organization_id, payment_id, fine_id, invoice_id, amount, allocation_type, created_at"
                    ") VALUES ("
                    ":alloc_id, :org_id, :pay_id, :fine_id, :inv_id, :amount, :allocation_type, :created_at"
                    ")"
                ),
                {
                    "alloc_id": str(allocation.allocation_id),
                    "org_id": str(allocation.organization_id),
                    "pay_id": str(allocation.payment_id),
                    "fine_id": str(allocation.fine_id),
                    "inv_id": str(allocation.invoice_id)
                    if allocation.invoice_id
                    else None,
                    "amount": allocation.amount,
                    "allocation_type": allocation.allocation_type,
                    "created_at": allocation.created_at,
                },
            )
        return allocation

    def get_allocation(
        self, organization_id: UUID, allocation_id: UUID
    ) -> PaymentAllocation | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT allocation_id, organization_id, payment_id, fine_id, invoice_id, amount, allocation_type, created_at "
                        "FROM public_library.payment_allocations "
                        "WHERE organization_id = :org_id AND allocation_id = :alloc_id"
                    ),
                    {"org_id": str(organization_id), "alloc_id": str(allocation_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _allocation_from_row(row)

    def list_allocations_for_fine(
        self, organization_id: UUID, fine_id: UUID
    ) -> list[PaymentAllocation]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT allocation_id, organization_id, payment_id, fine_id, invoice_id, amount, allocation_type, created_at "
                        "FROM public_library.payment_allocations "
                        "WHERE organization_id = :org_id AND fine_id = :fine_id "
                        "ORDER BY created_at ASC"
                    ),
                    {"org_id": str(organization_id), "fine_id": str(fine_id)},
                )
                .mappings()
                .all()
            )
        return [_allocation_from_row(r) for r in rows]

    def list_allocations_for_payment(
        self, organization_id: UUID, payment_id: UUID
    ) -> list[PaymentAllocation]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT allocation_id, organization_id, payment_id, fine_id, invoice_id, amount, allocation_type, created_at "
                        "FROM public_library.payment_allocations "
                        "WHERE organization_id = :org_id AND payment_id = :payment_id "
                        "ORDER BY created_at ASC"
                    ),
                    {"org_id": str(organization_id), "payment_id": str(payment_id)},
                )
                .mappings()
                .all()
            )
        return [_allocation_from_row(r) for r in rows]


def _member_from_row(row: RowMapping) -> Member:
    return Member(
        member_id=UUID(str(row["member_id"])),
        organization_id=UUID(str(row["organization_id"])),
        user_id=UUID(str(row["user_id"])),
        member_number=str(row["member_number"]),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _plan_from_row(row: RowMapping) -> MembershipPlan:
    desc = row["description"]
    price_val = row["price"]
    return MembershipPlan(
        plan_id=UUID(str(row["plan_id"])),
        organization_id=UUID(str(row["organization_id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        description=str(desc) if desc is not None else None,
        max_active_loans=int(row["max_active_loans"]),
        duration_days=int(row["duration_days"]),
        price=Decimal(str(price_val)) if price_val is not None else Decimal("0.0000"),
        currency=str(row["currency"]),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _subscription_from_row(row: RowMapping) -> Subscription:
    return Subscription(
        subscription_id=UUID(str(row["subscription_id"])),
        organization_id=UUID(str(row["organization_id"])),
        member_id=UUID(str(row["member_id"])),
        plan_id=UUID(str(row["plan_id"])),
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _fine_from_row(row: RowMapping) -> Fine:
    loan_val = row["loan_id"]
    return Fine(
        fine_id=UUID(str(row["fine_id"])),
        organization_id=UUID(str(row["organization_id"])),
        member_id=UUID(str(row["member_id"])),
        amount=Decimal(str(row["amount"])),
        currency=str(row["currency"]),
        status=str(row["status"]),
        reason=str(row["reason"]),
        assessed_at=row["assessed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        loan_id=UUID(str(loan_val)) if loan_val is not None else None,
    )


def _invoice_line_from_row(row: RowMapping) -> InvoiceLine:
    fine_val = row["fine_id"]
    return InvoiceLine(
        invoice_line_id=UUID(str(row["invoice_line_id"])),
        organization_id=UUID(str(row["organization_id"])),
        invoice_id=UUID(str(row["invoice_id"])),
        line_number=int(row["line_number"]),
        description=str(row["description"]),
        quantity=int(row["quantity"]),
        unit_price=Decimal(str(row["unit_price"])),
        amount=Decimal(str(row["amount"])),
        created_at=row["created_at"],
        fine_id=UUID(str(fine_val)) if fine_val is not None else None,
    )


def _invoice_from_row(row: RowMapping, lines: list[InvoiceLine]) -> Invoice:
    due_val = row["due_at"]
    return Invoice(
        invoice_id=UUID(str(row["invoice_id"])),
        organization_id=UUID(str(row["organization_id"])),
        member_id=UUID(str(row["member_id"])),
        invoice_number=str(row["invoice_number"]),
        subtotal=Decimal(str(row["subtotal"])),
        tax=Decimal(str(row["tax"])),
        total=Decimal(str(row["total"])),
        currency=str(row["currency"]),
        status=str(row["status"]),
        issued_at=row["issued_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        lines=lines,
        due_at=due_val if due_val is not None else None,
    )


def _payment_from_row(row: RowMapping) -> Payment:
    ref_val = row["provider_reference"]
    event_val = row["provider_event_id"]
    paid_val = row["paid_at"]
    return Payment(
        payment_id=UUID(str(row["payment_id"])),
        organization_id=UUID(str(row["organization_id"])),
        member_id=UUID(str(row["member_id"])),
        amount=Decimal(str(row["amount"])),
        currency=str(row["currency"]),
        provider=str(row["provider"]),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        provider_reference=str(ref_val) if ref_val is not None else None,
        provider_event_id=str(event_val) if event_val is not None else None,
        paid_at=paid_val if paid_val is not None else None,
    )


def _allocation_from_row(row: RowMapping) -> PaymentAllocation:
    inv_val = row["invoice_id"]
    return PaymentAllocation(
        allocation_id=UUID(str(row["allocation_id"])),
        organization_id=UUID(str(row["organization_id"])),
        payment_id=UUID(str(row["payment_id"])),
        fine_id=UUID(str(row["fine_id"])),
        amount=Decimal(str(row["amount"])),
        allocation_type=str(row["allocation_type"]),
        created_at=row["created_at"],
        invoice_id=UUID(str(inv_val)) if inv_val is not None else None,
    )
