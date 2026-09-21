"""Opaque browser refresh-session issuance, rotation, and revocation rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    Principal,
)
from openlibrary.modules.core.application.login import LoginResult


class CsrfValidationError(ValueError):
    """Raised only for an absent or mismatched double-submit CSRF value."""


@dataclass(frozen=True, slots=True)
class RefreshSession:
    """Durable state containing only non-reversible token representations."""

    session_id: UUID
    root_session_id: UUID
    parent_session_id: UUID | None
    organization_id: UUID
    user_id: UUID
    token_hash: str
    csrf_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    rotated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """One browser delivery payload; secrets are consumed only by the HTTP adapter."""

    access_token: str
    refresh_token: str
    csrf_token: str


class RefreshSessionStore(Protocol):
    """Transaction-aware persistence operations for refresh-session state."""

    def create(self, session: RefreshSession) -> None:
        """Persist a new session whose token and CSRF values are already hashed."""

    def resolve(self, token_hash: str) -> RefreshSession | None:
        """Resolve one token hash through the narrow pre-auth database boundary."""

    def rotate(
        self, session: RefreshSession, replacement: RefreshSession, when: datetime
    ) -> bool:
        """Atomically consume one session and persist its replacement."""

    def revoke_chain(
        self, root_session_id: UUID, organization_id: UUID, when: datetime
    ) -> None:
        """Revoke every descendant of a compromised or logged-out session."""


Clock = Callable[[], datetime]
TokenGenerator = Callable[[], str]


class RefreshSessionService:
    """Keep refresh secrets outside persistence while binding JWTs to session state."""

    def __init__(
        self,
        *,
        store: RefreshSessionStore,
        access_tokens: AccessTokenService,
        refresh_token_ttl: timedelta,
        now: Clock | None = None,
        random_token: TokenGenerator | None = None,
    ) -> None:
        if refresh_token_ttl <= timedelta(0):
            raise ValueError("Refresh-token lifetime must be positive")
        self._store = store
        self._access_tokens = access_tokens
        self._refresh_token_ttl = refresh_token_ttl
        self._now = now or _utc_now
        self._random_token = random_token or _random_token

    def start(self, result: LoginResult) -> RefreshResult:
        """Create the root session after successful credential verification."""
        session, refresh_result = self._new_session(result, parent=None, root=None)
        self._store.create(session)
        return refresh_result

    def rotate(self, raw_token: str, csrf_token: str) -> RefreshResult | None:
        """Consume a refresh value once and revoke its chain when it is replayed."""
        session = self._store.resolve(_token_hash(raw_token))
        if session is None:
            return None
        self._verify_csrf(session, csrf_token)
        now = self._now()
        if session.revoked_at is not None or session.expires_at <= now:
            return None
        if session.rotated_at is not None:
            self._store.revoke_chain(
                session.root_session_id, session.organization_id, now
            )
            return None
        replacement, refresh_result = self._new_session(
            LoginResult(
                user_id=session.user_id, organization_id=session.organization_id
            ),
            parent=session.session_id,
            root=session.root_session_id,
        )
        if not self._store.rotate(session, replacement, now):
            self._store.revoke_chain(
                session.root_session_id, session.organization_id, now
            )
            return None
        return refresh_result

    def logout(self, raw_token: str, csrf_token: str, principal: Principal) -> bool:
        """Revoke only the refresh chain bound to the verified bearer principal."""
        session = self._store.resolve(_token_hash(raw_token))
        if session is None:
            return False
        self._verify_csrf(session, csrf_token)
        if (
            session.revoked_at is not None
            or session.expires_at <= self._now()
            or session.session_id != principal.session_id
            or session.user_id != principal.user_id
            or session.organization_id != principal.organization_id
        ):
            return False
        self._store.revoke_chain(
            session.root_session_id, session.organization_id, self._now()
        )
        return True

    def _new_session(
        self,
        result: LoginResult,
        *,
        parent: UUID | None,
        root: UUID | None,
    ) -> tuple[RefreshSession, RefreshResult]:
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("The refresh-session clock must return an aware datetime")
        refresh_token = self._random_token()
        csrf_token = self._random_token()
        session_id = uuid4()
        session = RefreshSession(
            session_id=session_id,
            root_session_id=root or session_id,
            parent_session_id=parent,
            organization_id=result.organization_id,
            user_id=result.user_id,
            token_hash=_token_hash(refresh_token),
            csrf_hash=_csrf_hash(csrf_token),
            expires_at=now + self._refresh_token_ttl,
        )
        return session, RefreshResult(
            access_token=self._access_tokens.issue(result, session_id=session_id),
            refresh_token=refresh_token,
            csrf_token=csrf_token,
        )

    def _verify_csrf(self, session: RefreshSession, csrf_token: str) -> None:
        if not csrf_token or not hmac.compare_digest(
            session.csrf_hash, _csrf_hash(csrf_token)
        ):
            raise CsrfValidationError("CSRF validation failed")


def _token_hash(raw_token: str) -> str:
    """Domain-separate deterministic hashes for high-entropy opaque refresh values."""
    return hashlib.sha256(
        b"openlibraryos:refresh-token:v1\x00" + raw_token.encode("utf-8")
    ).hexdigest()


def _csrf_hash(raw_token: str) -> str:
    """Keep the CSRF secret out of durable storage just like the refresh token."""
    return hashlib.sha256(
        b"openlibraryos:refresh-csrf:v1\x00" + raw_token.encode("utf-8")
    ).hexdigest()


def _random_token() -> str:
    return secrets.token_urlsafe(32)


def _utc_now() -> datetime:
    return datetime.now(UTC)
