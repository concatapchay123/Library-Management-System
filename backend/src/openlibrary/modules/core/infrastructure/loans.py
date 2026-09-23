"""SQL Server persistence for circulation loans under tenant context."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from openlibrary.modules.core.application.loans import Loan, LoanStore
from openlibrary.modules.core.domain.loans import LoanNotFoundError, LoanStatus
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerLoanStore(LoanStore):
    """Execute parameterized circulation loan queries and mutations under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def create_loan(self, loan: Loan) -> Loan:
        with self._tenant_connection(loan.organization_id) as connection:
            return self.record_create_loan_in_connection(connection, loan)

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT loan_id, organization_id, copy_id, borrower_user_id, "
                        "status, loan_status, request_status, requested_at, approved_at, "
                        "checked_out_at, due_at, returned_at, policy_snapshot_json, "
                        "created_at, updated_at FROM core.loans "
                        "WHERE loan_id = :loan_id"
                    ),
                    {"loan_id": str(loan_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LoanNotFoundError(loan_id)
        return _loan_from_row(row)

    def update_loan(self, loan: Loan) -> Loan:
        with self._tenant_connection(loan.organization_id) as connection:
            return self.record_update_loan_in_connection(connection, loan)

    def list_loans(
        self,
        organization_id: UUID,
        *,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]:
        clauses = ["1=1"]
        params: dict[str, object] = {}
        if borrower_user_id is not None:
            clauses.append("borrower_user_id = :borrower_user_id")
            params["borrower_user_id"] = str(borrower_user_id)
        if copy_id is not None:
            clauses.append("copy_id = :copy_id")
            params["copy_id"] = str(copy_id)
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status

        query = (
            "SELECT loan_id, organization_id, copy_id, borrower_user_id, "
            "status, loan_status, request_status, requested_at, approved_at, "
            "checked_out_at, due_at, returned_at, policy_snapshot_json, "
            "created_at, updated_at FROM core.loans "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC, loan_id DESC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(query), params).mappings()
            return [_loan_from_row(row) for row in rows]

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
        query = (
            "SELECT COUNT(*) AS active_count FROM core.loans "
            "WHERE borrower_user_id = :borrower_user_id AND status IN ('checked_out', 'overdue')"
        )
        with self._tenant_connection(organization_id) as connection:
            val = connection.execute(
                text(query),
                {
                    "borrower_user_id": str(borrower_user_id),
                },
            ).scalar_one()
            return int(val)

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        query = (
            "SELECT loan_id, organization_id, copy_id, borrower_user_id, "
            "status, loan_status, request_status, requested_at, approved_at, "
            "checked_out_at, due_at, returned_at, policy_snapshot_json, "
            "created_at, updated_at FROM core.loans "
            "WHERE copy_id = :copy_id AND status IN ('checked_out', 'overdue')"
        )
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(query),
                    {"copy_id": str(copy_id)},
                )
                .mappings()
                .one_or_none()
            )
            return _loan_from_row(row) if row is not None else None

    def find_overdue_loans(self, organization_id: UUID, as_of: datetime) -> list[Loan]:
        with self._tenant_connection(organization_id) as connection:
            return self.find_overdue_loans_in_connection(
                connection, organization_id, as_of
            )

    def find_overdue_loans_in_connection(
        self, connection: Connection, organization_id: UUID, as_of: datetime
    ) -> list[Loan]:
        query = (
            "SELECT loan_id, organization_id, copy_id, borrower_user_id, "
            "status, loan_status, request_status, requested_at, approved_at, "
            "checked_out_at, due_at, returned_at, policy_snapshot_json, "
            "created_at, updated_at FROM core.loans "
            "WHERE status = :status AND due_at IS NOT NULL AND due_at < :as_of "
            "ORDER BY due_at ASC, loan_id ASC"
        )
        rows = connection.execute(
            text(query),
            {"status": LoanStatus.CHECKED_OUT, "as_of": as_of},
        ).mappings()
        return [_loan_from_row(row) for row in rows]

    def record_create_loan_in_connection(
        self, connection: Connection, loan: Loan
    ) -> Loan:
        """Insert a new loan atomically inside an active transaction."""
        connection.execute(
            text(
                "INSERT INTO core.loans (loan_id, organization_id, copy_id, "
                "borrower_user_id, status, loan_status, request_status, "
                "requested_at, approved_at, checked_out_at, due_at, returned_at, "
                "policy_snapshot_json, created_at, updated_at) "
                "VALUES (:loan_id, :organization_id, :copy_id, :borrower_user_id, "
                ":status, :loan_status, :request_status, :requested_at, :approved_at, "
                ":checked_out_at, :due_at, :returned_at, :policy_snapshot_json, "
                ":created_at, :updated_at)"
            ),
            _loan_params(loan),
        )
        return loan

    def record_update_loan_in_connection(
        self, connection: Connection, loan: Loan
    ) -> Loan:
        """Update an existing loan atomically inside an active transaction."""
        result = connection.execute(
            text(
                "UPDATE core.loans SET status = :status, loan_status = :loan_status, "
                "request_status = :request_status, approved_at = :approved_at, "
                "checked_out_at = :checked_out_at, due_at = :due_at, "
                "returned_at = :returned_at, policy_snapshot_json = :policy_snapshot_json, "
                "updated_at = SYSUTCDATETIME() WHERE loan_id = :loan_id"
            ),
            _loan_update_params(loan),
        )
        if result.rowcount != 1:
            raise LoanNotFoundError(loan.loan_id)
        return loan

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)


def _loan_params(loan: Loan) -> dict[str, object]:
    return {
        "loan_id": str(loan.loan_id),
        "organization_id": str(loan.organization_id),
        "copy_id": str(loan.copy_id),
        "borrower_user_id": str(loan.borrower_user_id),
        "status": loan.status,
        "loan_status": loan.loan_status,
        "request_status": loan.request_status,
        "requested_at": loan.requested_at,
        "approved_at": loan.approved_at,
        "checked_out_at": loan.checked_out_at,
        "due_at": loan.due_at,
        "returned_at": loan.returned_at,
        "policy_snapshot_json": json.dumps(loan.policy_snapshot),
        "created_at": loan.created_at,
        "updated_at": loan.updated_at,
    }


def _loan_update_params(loan: Loan) -> dict[str, object]:
    return {
        "loan_id": str(loan.loan_id),
        "status": loan.status,
        "loan_status": loan.loan_status,
        "request_status": loan.request_status,
        "approved_at": loan.approved_at,
        "checked_out_at": loan.checked_out_at,
        "due_at": loan.due_at,
        "returned_at": loan.returned_at,
        "policy_snapshot_json": json.dumps(loan.policy_snapshot),
    }


def _loan_from_row(row: RowMapping) -> Loan:
    raw_snapshot = row["policy_snapshot_json"]
    snapshot: dict[str, object] = {}
    if raw_snapshot:
        try:
            snapshot = json.loads(str(raw_snapshot))
        except (ValueError, TypeError):
            snapshot = {}

    return Loan(
        loan_id=UUID(str(row["loan_id"])),
        organization_id=UUID(str(row["organization_id"])),
        copy_id=UUID(str(row["copy_id"])),
        borrower_user_id=UUID(str(row["borrower_user_id"])),
        status=str(row["status"]),
        loan_status=str(row["loan_status"]),
        request_status=str(row["request_status"]),
        requested_at=_parse_dt(row["requested_at"]),
        approved_at=_parse_opt_dt(row["approved_at"]),
        checked_out_at=_parse_opt_dt(row["checked_out_at"]),
        due_at=_parse_opt_dt(row["due_at"]),
        returned_at=_parse_opt_dt(row["returned_at"]),
        policy_snapshot=snapshot,
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(val: object) -> datetime:
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


def _parse_opt_dt(val: object) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))
