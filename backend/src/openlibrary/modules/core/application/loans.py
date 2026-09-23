"""Application service and ports for circulation loan lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus, validate_transition
from openlibrary.modules.core.domain.loans import (
    ActiveLoanLimitExceededError,
    CopyNotAvailableForLoanError,
    LoanStatus,
    validate_loan_transition,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)


@dataclass(frozen=True, slots=True)
class Loan:
    """One immutable representation of a library copy loan lifecycle."""

    loan_id: UUID
    organization_id: UUID
    copy_id: UUID
    borrower_user_id: UUID
    status: str
    loan_status: str
    request_status: str
    requested_at: datetime
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    checked_out_at: datetime | None = None
    due_at: datetime | None = None
    returned_at: datetime | None = None
    policy_snapshot: Mapping[str, object] = field(default_factory=dict)


class LoanStore(Protocol):
    """Persistence port for tenant-scoped loans."""

    def create_loan(self, loan: Loan) -> Loan: ...

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan: ...

    def update_loan(self, loan: Loan) -> Loan: ...

    def list_loans(
        self,
        organization_id: UUID,
        *,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]: ...

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int: ...

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None: ...

    def find_overdue_loans(
        self, organization_id: UUID, as_of: datetime
    ) -> list[Loan]: ...


@dataclass(frozen=True, slots=True)
class BorrowingPolicy:
    """One immutable representation of policy rules governing a borrower's active loans and checkout duration."""

    borrower_type: str
    max_active_loans: int
    duration_days: int
    policy_snapshot: Mapping[str, object] = field(default_factory=dict)


class BorrowingPolicyResolver(Protocol):
    """Port for resolving borrowing policies by tenant organization and borrower."""

    def resolve_policy(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> BorrowingPolicy: ...


class DefaultBorrowingPolicyResolver:
    """Fallback borrowing policy resolver applying standard system defaults."""

    def __init__(
        self,
        default_max_active_loans: int = 5,
        default_duration_days: int = 14,
    ) -> None:
        self._max_active_loans = default_max_active_loans
        self._duration_days = default_duration_days

    def resolve_policy(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> BorrowingPolicy:
        return BorrowingPolicy(
            borrower_type="standard",
            max_active_loans=self._max_active_loans,
            duration_days=self._duration_days,
            policy_snapshot={
                "borrower_type": "standard",
                "max_active_loans": self._max_active_loans,
                "duration_days": self._duration_days,
            },
        )


class LoanService:
    """Unified application service for self-service and librarian-desk circulation flows."""

    _PERM_REQUEST = "circulation.request"
    _PERM_APPROVE = "circulation.approve"
    _PERM_CHECKOUT = "circulation.checkout"
    _PERM_RETURN = "circulation.return"
    _PERM_READ = "circulation.read"
    _PERM_MANAGE = "circulation.manage"

    _DEFAULT_ACTIVE_LIMIT = 5
    _DEFAULT_DURATION_DAYS = 14

    def __init__(
        self,
        *,
        loan_store: LoanStore,
        copy_store: CopyStatusStore,
        authorizer: AuthorizationPort,
        policy_resolver: BorrowingPolicyResolver | None = None,
        transaction: AuditedTransaction | None = None,
        connection_provider: Callable[[UUID], AbstractContextManager[object]]
        | None = None,
    ) -> None:
        self._loan_store = loan_store
        self._copy_store = copy_store
        self._authorizer = authorizer
        self._policy_resolver = policy_resolver or DefaultBorrowingPolicyResolver()
        self._transaction = transaction
        self._connection_provider = connection_provider

    def _require_perm(self, actor: Principal, permission: str) -> None:
        try:
            self._authorizer.require(actor, permission)
        except AuthorizationDenied:
            try:
                self._authorizer.require(actor, self._PERM_MANAGE)
            except AuthorizationDenied:
                raise AuthorizationDenied(f"Permission {permission} required")

    def _allows(self, actor: Principal, permission: str) -> bool:
        try:
            self._require_perm(actor, permission)
            return True
        except AuthorizationDenied:
            return False

    def request_loan(
        self,
        *,
        actor: Principal,
        copy_id: UUID,
        borrower_user_id: UUID | None = None,
        duration_days: int | None = None,
        policy_snapshot: Mapping[str, object] | None = None,
        correlation_id: UUID | None = None,
    ) -> Loan:
        """Create a self-service or staff-assisted loan request."""
        target_borrower = borrower_user_id or actor.user_id
        if target_borrower is None:
            raise ValueError("Borrower user_id is required")

        if target_borrower != actor.user_id:
            # Assisting another borrower requires staff checkout/manage or request permission
            if not (
                self._allows(actor, self._PERM_CHECKOUT)
                or self._allows(actor, self._PERM_MANAGE)
                or self._allows(actor, self._PERM_REQUEST)
            ):
                raise AuthorizationDenied(
                    "Staff permission required to request on behalf of others"
                )
        else:
            self._require_perm(actor, self._PERM_REQUEST)

        # Invariant check: copy exists in tenant
        copy = self._copy_store.get_copy(actor.organization_id, copy_id)
        if copy.status != CopyStatus.AVAILABLE:
            raise CopyNotAvailableForLoanError(copy_id, copy.status)

        # Resolve borrowing policy for this borrower in this tenant
        policy = self._policy_resolver.resolve_policy(
            actor.organization_id, target_borrower
        )

        # Invariant check: active loan count limit
        active_count = self._loan_store.count_active_loans_for_borrower(
            actor.organization_id, target_borrower
        )
        if active_count >= policy.max_active_loans:
            raise ActiveLoanLimitExceededError()

        now = datetime.now(timezone.utc)
        effective_duration = (
            duration_days
            if (duration_days is not None and duration_days > 0)
            else policy.duration_days
        )
        snapshot = dict(policy.policy_snapshot)
        if policy_snapshot is not None:
            snapshot.update(policy_snapshot)
        snapshot.setdefault("borrower_type", policy.borrower_type)
        snapshot.setdefault("max_active_loans", policy.max_active_loans)
        snapshot["max_days_at_checkout"] = effective_duration
        snapshot["duration_days"] = effective_duration

        loan_id = uuid4()
        loan = Loan(
            loan_id=loan_id,
            organization_id=actor.organization_id,
            copy_id=copy_id,
            borrower_user_id=target_borrower,
            status=LoanStatus.REQUESTED,
            loan_status=LoanStatus.REQUESTED,
            request_status="pending",
            requested_at=now,
            created_at=now,
            updated_at=now,
            policy_snapshot=snapshot,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="loan.requested",
            entity_type="loan",
            entity_id=loan_id,
            payload={
                "loan_id": str(loan_id),
                "copy_id": str(copy_id),
                "borrower_user_id": str(target_borrower),
                "status": LoanStatus.REQUESTED,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.loan_requested",
            aggregate_type="loan",
            aggregate_id=loan_id,
            payload_version=1,
            payload={
                "loan_id": str(loan_id),
                "organization_id": str(actor.organization_id),
                "copy_id": str(copy_id),
                "borrower_user_id": str(target_borrower),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"loan:{loan_id}:requested",
        )

        def _mutation(connection: object) -> Loan:
            if hasattr(self._loan_store, "record_create_loan_in_connection"):
                return self._loan_store.record_create_loan_in_connection(  # type: ignore[no-any-return]
                    connection, loan
                )
            return self._loan_store.create_loan(loan)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def approve_loan(
        self,
        *,
        actor: Principal,
        loan_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Loan:
        """Librarian approval action for a requested loan."""
        self._require_perm(actor, self._PERM_APPROVE)
        current = self._loan_store.get_loan(actor.organization_id, loan_id)

        validate_loan_transition(current.status, LoanStatus.APPROVED)

        now = datetime.now(timezone.utc)
        updated = Loan(
            loan_id=current.loan_id,
            organization_id=current.organization_id,
            copy_id=current.copy_id,
            borrower_user_id=current.borrower_user_id,
            status=LoanStatus.APPROVED,
            loan_status=LoanStatus.APPROVED,
            request_status="approved",
            requested_at=current.requested_at,
            approved_at=now,
            checked_out_at=current.checked_out_at,
            due_at=current.due_at,
            returned_at=current.returned_at,
            policy_snapshot=current.policy_snapshot,
            created_at=current.created_at,
            updated_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="loan.approved",
            entity_type="loan",
            entity_id=loan_id,
            payload={
                "loan_id": str(loan_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
                "status": LoanStatus.APPROVED,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.loan_approved",
            aggregate_type="loan",
            aggregate_id=loan_id,
            payload_version=1,
            payload={
                "loan_id": str(loan_id),
                "organization_id": str(actor.organization_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"loan:{loan_id}:approved",
        )

        def _mutation(connection: object) -> Loan:
            if hasattr(self._loan_store, "record_update_loan_in_connection"):
                return self._loan_store.record_update_loan_in_connection(  # type: ignore[no-any-return]
                    connection, updated
                )
            return self._loan_store.update_loan(updated)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def reject_loan(
        self,
        *,
        actor: Principal,
        loan_id: UUID,
        reason: str = "",
        correlation_id: UUID | None = None,
    ) -> Loan:
        """Librarian rejection action for a requested loan."""
        self._require_perm(actor, self._PERM_APPROVE)
        current = self._loan_store.get_loan(actor.organization_id, loan_id)

        validate_loan_transition(current.status, LoanStatus.REJECTED)

        now = datetime.now(timezone.utc)
        updated = Loan(
            loan_id=current.loan_id,
            organization_id=current.organization_id,
            copy_id=current.copy_id,
            borrower_user_id=current.borrower_user_id,
            status=LoanStatus.REJECTED,
            loan_status=LoanStatus.REJECTED,
            request_status="rejected",
            requested_at=current.requested_at,
            approved_at=current.approved_at,
            checked_out_at=current.checked_out_at,
            due_at=current.due_at,
            returned_at=current.returned_at,
            policy_snapshot=current.policy_snapshot,
            created_at=current.created_at,
            updated_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="loan.rejected",
            entity_type="loan",
            entity_id=loan_id,
            payload={
                "loan_id": str(loan_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
                "reason": reason,
                "status": LoanStatus.REJECTED,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.loan_rejected",
            aggregate_type="loan",
            aggregate_id=loan_id,
            payload_version=1,
            payload={
                "loan_id": str(loan_id),
                "organization_id": str(actor.organization_id),
                "copy_id": str(current.copy_id),
                "reason": reason,
            },
            correlation_id=audit_correlation,
            idempotency_key=f"loan:{loan_id}:rejected",
        )

        def _mutation(connection: object) -> Loan:
            if hasattr(self._loan_store, "record_update_loan_in_connection"):
                return self._loan_store.record_update_loan_in_connection(  # type: ignore[no-any-return]
                    connection, updated
                )
            return self._loan_store.update_loan(updated)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def checkout_loan(
        self,
        *,
        actor: Principal,
        loan_id: UUID,
        duration_days: int | None = None,
        correlation_id: UUID | None = None,
    ) -> Loan:
        """Fulfill an approved loan by transitioning copy to borrowed and loan to checked_out."""
        self._require_perm(actor, self._PERM_CHECKOUT)
        current = self._loan_store.get_loan(actor.organization_id, loan_id)

        # Invariant: Self-service requests cannot checkout without approval
        validate_loan_transition(current.status, LoanStatus.CHECKED_OUT)

        # Invariant: Copy must be available and can transition to borrowed
        copy = self._copy_store.get_copy(actor.organization_id, current.copy_id)
        if copy.status != CopyStatus.AVAILABLE:
            raise CopyNotAvailableForLoanError(copy.copy_id, copy.status)
        validate_transition(copy.status, CopyStatus.BORROWED)

        now = datetime.now(timezone.utc)
        updated_snapshot = dict(current.policy_snapshot)
        if (
            "max_active_loans" not in updated_snapshot
            or "borrower_type" not in updated_snapshot
        ):
            policy = self._policy_resolver.resolve_policy(
                actor.organization_id, current.borrower_user_id
            )
            for k, v in policy.policy_snapshot.items():
                updated_snapshot.setdefault(k, v)
            updated_snapshot.setdefault("borrower_type", policy.borrower_type)
            updated_snapshot.setdefault("max_active_loans", policy.max_active_loans)

        raw_days = updated_snapshot.get("duration_days")
        effective_days = duration_days or (
            int(str(raw_days)) if raw_days is not None else self._DEFAULT_DURATION_DAYS
        )
        due_at = now + timedelta(days=effective_days)

        updated_snapshot["max_days_at_checkout"] = effective_days
        updated_snapshot["duration_days"] = effective_days

        updated = Loan(
            loan_id=current.loan_id,
            organization_id=current.organization_id,
            copy_id=current.copy_id,
            borrower_user_id=current.borrower_user_id,
            status=LoanStatus.CHECKED_OUT,
            loan_status=LoanStatus.CHECKED_OUT,
            request_status="fulfilled",
            requested_at=current.requested_at,
            approved_at=current.approved_at,
            checked_out_at=now,
            due_at=due_at,
            returned_at=None,
            policy_snapshot=updated_snapshot,
            created_at=current.created_at,
            updated_at=now,
        )

        history_record = CopyStatusHistory(
            history_id=uuid4(),
            organization_id=actor.organization_id,
            copy_id=copy.copy_id,
            from_status=copy.status,
            to_status=CopyStatus.BORROWED,
            reason=f"Checked out under loan {loan_id}",
            actor_id=actor.user_id,
            created_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="loan.checked_out",
            entity_type="loan",
            entity_id=loan_id,
            payload={
                "loan_id": str(loan_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
                "due_at": due_at.isoformat(),
                "status": LoanStatus.CHECKED_OUT,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.loan_checked_out",
            aggregate_type="loan",
            aggregate_id=loan_id,
            payload_version=1,
            payload={
                "loan_id": str(loan_id),
                "organization_id": str(actor.organization_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
                "due_at": due_at.isoformat(),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"loan:{loan_id}:checked_out",
        )

        def _mutation(connection: object) -> Loan:
            if (
                hasattr(self._copy_store, "get_copy_for_update_in_connection")
                and connection is not None
            ):
                locked_copy = getattr(
                    self._copy_store, "get_copy_for_update_in_connection"
                )(connection, actor.organization_id, current.copy_id)
            else:
                locked_copy = self._copy_store.get_copy(
                    actor.organization_id, current.copy_id
                )
            if locked_copy.status != CopyStatus.AVAILABLE:
                raise CopyNotAvailableForLoanError(
                    locked_copy.copy_id, locked_copy.status
                )
            validate_transition(locked_copy.status, CopyStatus.BORROWED)

            if hasattr(self._copy_store, "record_transition_in_connection"):
                getattr(self._copy_store, "record_transition_in_connection")(
                    connection,
                    organization_id=actor.organization_id,
                    copy_id=copy.copy_id,
                    to_status=CopyStatus.BORROWED,
                    history_record=history_record,
                )
            else:
                self._copy_store.update_copy_status(
                    actor.organization_id, copy.copy_id, CopyStatus.BORROWED
                )
                self._copy_store.append_history(history_record)

            if hasattr(self._loan_store, "record_update_loan_in_connection"):
                return self._loan_store.record_update_loan_in_connection(  # type: ignore[no-any-return]
                    connection, updated
                )
            return self._loan_store.update_loan(updated)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def desk_checkout(
        self,
        *,
        actor: Principal,
        copy_id: UUID,
        borrower_user_id: UUID,
        duration_days: int | None = None,
        policy_snapshot: Mapping[str, object] | None = None,
        correlation_id: UUID | None = None,
    ) -> Loan:
        """Staff desk flow: request, explicit approval, then checkout via the shared service."""
        self._require_perm(actor, self._PERM_CHECKOUT)

        # 1. Initiate loan request
        requested_loan = self.request_loan(
            actor=actor,
            copy_id=copy_id,
            borrower_user_id=borrower_user_id,
            duration_days=duration_days,
            policy_snapshot=policy_snapshot,
            correlation_id=correlation_id,
        )

        # 2. Explicit approval action
        approved_loan = self.approve_loan(
            actor=actor,
            loan_id=requested_loan.loan_id,
            correlation_id=correlation_id,
        )

        # 3. Invoke the shared checkout service
        return self.checkout_loan(
            actor=actor,
            loan_id=approved_loan.loan_id,
            duration_days=duration_days,
            correlation_id=correlation_id,
        )

    def return_loan(
        self,
        *,
        actor: Principal,
        loan_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Loan:
        """Atomic return of a borrowed copy: updates loan to returned and copy to available."""
        self._require_perm(actor, self._PERM_RETURN)
        current = self._loan_store.get_loan(actor.organization_id, loan_id)

        validate_loan_transition(current.status, LoanStatus.RETURNED)

        copy = self._copy_store.get_copy(actor.organization_id, current.copy_id)
        validate_transition(copy.status, CopyStatus.AVAILABLE)

        now = datetime.now(timezone.utc)
        updated = Loan(
            loan_id=current.loan_id,
            organization_id=current.organization_id,
            copy_id=current.copy_id,
            borrower_user_id=current.borrower_user_id,
            status=LoanStatus.RETURNED,
            loan_status=LoanStatus.RETURNED,
            request_status="fulfilled",
            requested_at=current.requested_at,
            approved_at=current.approved_at,
            checked_out_at=current.checked_out_at,
            due_at=current.due_at,
            returned_at=now,
            policy_snapshot=current.policy_snapshot,
            created_at=current.created_at,
            updated_at=now,
        )

        history_record = CopyStatusHistory(
            history_id=uuid4(),
            organization_id=actor.organization_id,
            copy_id=copy.copy_id,
            from_status=copy.status,
            to_status=CopyStatus.AVAILABLE,
            reason=f"Returned from loan {loan_id}",
            actor_id=actor.user_id,
            created_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="loan.returned",
            entity_type="loan",
            entity_id=loan_id,
            payload={
                "loan_id": str(loan_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
                "returned_at": now.isoformat(),
                "status": LoanStatus.RETURNED,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.loan_returned",
            aggregate_type="loan",
            aggregate_id=loan_id,
            payload_version=1,
            payload={
                "loan_id": str(loan_id),
                "organization_id": str(actor.organization_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.borrower_user_id),
                "returned_at": now.isoformat(),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"loan:{loan_id}:returned",
        )

        def _mutation(connection: object) -> Loan:
            if hasattr(self._copy_store, "record_transition_in_connection"):
                getattr(self._copy_store, "record_transition_in_connection")(
                    connection,
                    organization_id=actor.organization_id,
                    copy_id=copy.copy_id,
                    to_status=CopyStatus.AVAILABLE,
                    history_record=history_record,
                )
            else:
                self._copy_store.update_copy_status(
                    actor.organization_id, copy.copy_id, CopyStatus.AVAILABLE
                )
                self._copy_store.append_history(history_record)

            if hasattr(self._loan_store, "record_update_loan_in_connection"):
                return self._loan_store.record_update_loan_in_connection(  # type: ignore[no-any-return]
                    connection, updated
                )
            return self._loan_store.update_loan(updated)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def get_loan(self, *, actor: Principal, loan_id: UUID) -> Loan:
        """Fetch a single loan, enforcing borrower ownership or staff read permission."""
        loan = self._loan_store.get_loan(actor.organization_id, loan_id)
        if loan.borrower_user_id != actor.user_id:
            self._require_perm(actor, self._PERM_READ)
        return loan

    def list_loans(
        self,
        *,
        actor: Principal,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]:
        """List loans within the tenant, filtered by borrower, copy or status."""
        target_borrower = borrower_user_id
        if not self._allows(actor, self._PERM_READ):
            # Self-service borrowers can only list their own loans
            target_borrower = actor.user_id
        return self._loan_store.list_loans(
            actor.organization_id,
            borrower_user_id=target_borrower,
            copy_id=copy_id,
            status=status,
        )
