"""Browser refresh-session HTTP contracts and replay resistance."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask.testing import FlaskClient
import pytest

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    JwtKey,
)
from openlibrary.modules.core.application.login import LoginResult
from openlibrary.modules.core.application.refresh_sessions import (
    RefreshSessionService,
    RefreshSessionStore,
)


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class StoredRefreshSession:
    """Test-only durable state; it deliberately holds hashes rather than secrets."""

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


class MemoryRefreshSessionStore(RefreshSessionStore):
    """Minimal persistence double that makes rotation and chain state inspectable."""

    def __init__(self) -> None:
        self.sessions: dict[UUID, StoredRefreshSession] = {}
        self.fail_creates = False

    def create(self, session: StoredRefreshSession) -> None:
        if self.fail_creates:
            raise RuntimeError("simulated insert failure")
        self.sessions[session.session_id] = session

    def resolve(self, token_hash: str) -> StoredRefreshSession | None:
        return next(
            (
                session
                for session in self.sessions.values()
                if session.token_hash == token_hash
            ),
            None,
        )

    def rotate(
        self,
        session: StoredRefreshSession,
        replacement: StoredRefreshSession,
        when: datetime,
    ) -> bool:
        session = self.sessions[session.session_id]
        if session.rotated_at is not None or session.revoked_at is not None:
            return False
        if self.fail_creates:
            raise RuntimeError("simulated insert failure")
        self.sessions[session.session_id] = replace(session, rotated_at=when)
        self.sessions[replacement.session_id] = replacement
        return True

    def revoke_chain(
        self, root_session_id: UUID, organization_id: UUID, when: datetime
    ) -> None:
        for session_id, session in self.sessions.items():
            if (
                session.root_session_id == root_session_id
                and session.organization_id == organization_id
                and session.revoked_at is None
            ):
                self.sessions[session_id] = replace(session, revoked_at=when)


@dataclass(slots=True)
class StubLoginService:
    """Return one authenticated user so the HTTP boundary owns session issuance."""

    result: LoginResult

    def login(
        self,
        *,
        organization_slug: str,
        email: str,
        password: str,
        correlation_id: str,
    ) -> LoginResult | None:
        del organization_slug, email, password, correlation_id
        return self.result


@pytest.fixture
def access_tokens() -> AccessTokenService:
    """Build an isolated signer without committing private material."""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key = JwtKey(
        key_id="refresh-test-key",
        private_key_pem=private_key_pem,
        public_key_pem=public_key_pem,
    )
    return AccessTokenService(
        issuer="https://identity.openlibraryos.example",
        audience="openlibraryos-api",
        access_token_ttl=timedelta(minutes=15),
        signing_key=key,
        verification_keys={key.key_id: key.public_key_pem},
        now=lambda: NOW,
    )


@pytest.fixture
def store() -> MemoryRefreshSessionStore:
    return MemoryRefreshSessionStore()


@pytest.fixture
def refresh_sessions(
    store: MemoryRefreshSessionStore, access_tokens: AccessTokenService
) -> RefreshSessionService:
    return RefreshSessionService(
        store=store,
        access_tokens=access_tokens,
        refresh_token_ttl=timedelta(days=14),
        now=lambda: NOW,
        random_token=lambda: "token-" + str(uuid4()),
    )


@pytest.fixture
def client(
    access_tokens: AccessTokenService, refresh_sessions: RefreshSessionService
) -> FlaskClient:
    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            login_service=StubLoginService(LoginResult(uuid4(), uuid4())),
            access_tokens=access_tokens,
            refresh_sessions=refresh_sessions,
        )
    )
    return app.test_client()


def _login(client: FlaskClient) -> object:
    return client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "campus-a",
            "email": "librarian@example.test",
            "password": "correct-horse-battery-staple",
        },
    )


def _cookie_value(response: object, name: str) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError(f"Missing {name} cookie")


def test_refresh_rotation_is_single_use_and_replay_revokes_the_entire_chain(
    client: FlaskClient, store: MemoryRefreshSessionStore
) -> None:
    """A stolen pre-rotation cookie must invalidate both old and replacement sessions."""

    login = _login(client)
    original_refresh = _cookie_value(login, "refresh_token")
    original_csrf = _cookie_value(login, "csrf_token")
    assert login.status_code == 200
    assert original_refresh.encode() not in login.data
    assert all(
        original_refresh not in str(session) for session in store.sessions.values()
    )
    assert "Secure; HttpOnly; Path=/api/v1/auth; SameSite=Strict" in "\n".join(
        login.headers.getlist("Set-Cookie")
    )

    rotated = client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": original_csrf}
    )
    replacement_refresh = _cookie_value(rotated, "refresh_token")
    replacement_csrf = _cookie_value(rotated, "csrf_token")
    assert rotated.status_code == 200
    assert replacement_refresh != original_refresh
    assert replacement_csrf != original_csrf
    assert rotated.get_json()["token_type"] == "Bearer"

    client.set_cookie("refresh_token", original_refresh, path="/api/v1/auth")
    client.set_cookie("csrf_token", original_csrf, path="/api/v1/auth")
    replay = client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": original_csrf}
    )
    assert replay.status_code == 401
    assert all(session.revoked_at is not None for session in store.sessions.values())

    client.set_cookie("refresh_token", replacement_refresh, path="/api/v1/auth")
    client.set_cookie("csrf_token", replacement_csrf, path="/api/v1/auth")
    revoked_replacement = client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": replacement_csrf}
    )
    assert revoked_replacement.status_code == 401


def test_logout_revokes_the_active_chain_and_mutations_require_csrf(
    client: FlaskClient, store: MemoryRefreshSessionStore
) -> None:
    """Neither refresh nor logout accepts an ambient browser cookie without CSRF proof."""

    login = _login(client)
    csrf = _cookie_value(login, "csrf_token")
    refresh = _cookie_value(login, "refresh_token")
    access_token = login.get_json()["access_token"]

    missing_csrf = client.post("/api/v1/auth/refresh")
    invalid_csrf = client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": "not-the-cookie"}
    )
    missing_logout_csrf = client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert [response.status_code for response in (missing_csrf, invalid_csrf)] == [
        403,
        403,
    ]
    assert missing_logout_csrf.status_code == 403

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}", "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 204
    assert all(session.revoked_at is not None for session in store.sessions.values())
    client.set_cookie("refresh_token", refresh, path="/api/v1/auth")
    client.set_cookie("csrf_token", csrf, path="/api/v1/auth")
    assert (
        client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf}).status_code
        == 401
    )


def test_csrf_header_without_the_matching_csrf_cookie_is_rejected(
    client: FlaskClient,
) -> None:
    """The request must prove both browser cookie state and the server-bound secret."""

    login = _login(client)
    csrf = _cookie_value(login, "csrf_token")
    client.delete_cookie("csrf_token", path="/api/v1/auth")

    response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})

    assert response.status_code == 403


def test_failed_replacement_insert_does_not_consume_the_original_session(
    refresh_sessions: RefreshSessionService, store: MemoryRefreshSessionStore
) -> None:
    """Rotation must commit consumption and child creation together, or neither state."""

    initial = refresh_sessions.start(
        LoginResult(user_id=uuid4(), organization_id=uuid4())
    )
    original = next(iter(store.sessions.values()))
    store.fail_creates = True

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        refresh_sessions.rotate(initial.refresh_token, initial.csrf_token)

    assert store.sessions[original.session_id].rotated_at is None
