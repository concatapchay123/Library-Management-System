"""HTTP contract coverage for tenant-scoped credential validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

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
from openlibrary.modules.core.application.refresh_sessions import RefreshResult


@dataclass(frozen=True, slots=True)
class LoginCall:
    """One credential handoff observed at the application boundary."""

    organization_slug: str
    email: str
    password: str
    correlation_id: str


@dataclass(slots=True)
class StubLoginService:
    """Deterministic application boundary used by HTTP contract tests."""

    results: dict[tuple[str, str, str], LoginResult]
    calls: list[LoginCall] = field(default_factory=list)

    def login(
        self,
        *,
        organization_slug: str,
        email: str,
        password: str,
        correlation_id: str,
    ) -> LoginResult | None:
        self.calls.append(LoginCall(organization_slug, email, password, correlation_id))
        return self.results.get((organization_slug, email, password))

    def change_password(
        self,
        *,
        actor: object,
        current_password: str,
        new_password: str,
        correlation_id: str,
    ) -> None:
        del actor, correlation_id
        if current_password == "wrong-password":
            raise ValueError("Current password is incorrect")
        if len(new_password) < 12:
            raise ValueError("new_password must be at least 12 characters")
        if new_password == current_password:
            raise ValueError("new_password must be different from current_password")


@dataclass(slots=True)
class StubRefreshSessions:
    """Provide browser-session issuance without changing login credential contracts."""

    access_tokens: AccessTokenService

    def start(self, result: LoginResult) -> RefreshResult:
        return RefreshResult(
            access_token=self.access_tokens.issue(result),
            refresh_token="refresh-test-value",
            csrf_token="csrf-test-value",
        )


@pytest.fixture
def login_service() -> StubLoginService:
    """Provide two tenant-local users with an intentionally duplicate email."""
    duplicate_email = "librarian@example.test"
    password = "correct-horse-battery-staple"
    return StubLoginService(
        {
            ("campus-a", duplicate_email, password): LoginResult(
                user_id=uuid4(), organization_id=uuid4()
            ),
            ("campus-b", duplicate_email, password): LoginResult(
                user_id=uuid4(), organization_id=uuid4()
            ),
        }
    )


@pytest.fixture
def access_tokens() -> AccessTokenService:
    """Create an ephemeral RS256 signer for the login response contract."""
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
        key_id="test-key",
        private_key_pem=private_key_pem,
        public_key_pem=public_key_pem,
    )
    return AccessTokenService(
        issuer="https://identity.openlibraryos.example",
        audience="openlibraryos-api",
        access_token_ttl=timedelta(minutes=15),
        signing_key=key,
        verification_keys={key.key_id: key.public_key_pem},
    )


@pytest.fixture
def client(
    login_service: StubLoginService, access_tokens: AccessTokenService
) -> FlaskClient:
    """Create the HTTP adapter with a controlled login application service."""
    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            login_service=login_service,
            access_tokens=access_tokens,
            refresh_sessions=StubRefreshSessions(access_tokens),
        )
    )
    return app.test_client()


def _login(client: FlaskClient, payload: dict[str, str]) -> object:
    return client.post(
        "/api/v1/auth/login",
        headers={"X-Request-ID": "login-contract-test"},
        json=payload,
    )


def test_login_issues_an_access_token_without_returning_credential_material(
    client: FlaskClient,
) -> None:
    """A successful credential check returns an access token, never credentials."""
    response = _login(
        client,
        {
            "organization_slug": "campus-a",
            "email": "librarian@example.test",
            "password": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 200
    assert set(response.get_json()) == {"access_token", "token_type", "expires_in"}
    assert response.get_json()["token_type"] == "Bearer"
    assert response.get_json()["expires_in"] == 900
    assert b"correct-horse-battery-staple" not in response.data


def test_wrong_slug_disabled_slug_and_wrong_password_share_one_public_failure(
    client: FlaskClient,
) -> None:
    """Changing one failure path must not restore tenant or credential enumeration."""
    payloads = (
        {
            "organization_slug": "missing-campus",
            "email": "librarian@example.test",
            "password": "wrong-password",
        },
        {
            "organization_slug": "disabled-campus",
            "email": "librarian@example.test",
            "password": "wrong-password",
        },
        {
            "organization_slug": "campus-a",
            "email": "librarian@example.test",
            "password": "wrong-password",
        },
    )

    responses = [_login(client, payload) for payload in payloads]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert [response.mimetype for response in responses] == [
        "application/problem+json",
        "application/problem+json",
        "application/problem+json",
    ]
    assert responses[0].get_json() == responses[1].get_json() == responses[2].get_json()


def test_missing_slug_reaches_the_service_for_dummy_verification(
    client: FlaskClient, login_service: StubLoginService
) -> None:
    """Rejecting before the service would skip the required dummy Argon2 work."""
    response = _login(
        client,
        {
            "email": "librarian@example.test",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert login_service.calls[-1] == LoginCall(
        organization_slug="",
        email="librarian@example.test",
        password="wrong-password",
        correlation_id="login-contract-test",
    )


def test_duplicate_email_authenticates_against_the_organization_slug(
    client: FlaskClient, login_service: StubLoginService
) -> None:
    """A tenant-local identity lookup must use the resolved organization boundary."""
    password = "correct-horse-battery-staple"

    first = _login(
        client,
        {
            "organization_slug": "campus-a",
            "email": "librarian@example.test",
            "password": password,
        },
    )
    second = _login(
        client,
        {
            "organization_slug": "campus-b",
            "email": "librarian@example.test",
            "password": password,
        },
    )

    assert first.status_code == second.status_code == 200
    assert [call.organization_slug for call in login_service.calls] == [
        "campus-a",
        "campus-b",
    ]
    assert (
        len({result.organization_id for result in login_service.results.values()}) == 2
    )


def test_change_password_requires_authenticated_principal(
    client: FlaskClient,
) -> None:
    """Unauthenticated calls to /password/change must return 401."""
    response = client.post(
        "/api/v1/auth/password/change",
        json={
            "current_password": "OldPassword123!",
            "new_password": "NewSecurePassword123!",
        },
    )
    assert response.status_code == 401


def test_change_password_requires_csrf_double_submit(
    client: FlaskClient, access_tokens: AccessTokenService
) -> None:
    """Calling /password/change without matching CSRF header and cookie returns 403."""
    token = access_tokens.issue(LoginResult(user_id=uuid4(), organization_id=uuid4()))
    response = client.post(
        "/api/v1/auth/password/change",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "OldPassword123!",
            "new_password": "NewSecurePassword123!",
        },
    )
    assert response.status_code == 403
    assert response.mimetype == "application/problem+json"


def test_change_password_success(
    client: FlaskClient, access_tokens: AccessTokenService
) -> None:
    """Valid bearer token, matching CSRF header/cookie, and valid payload returns 204."""
    token = access_tokens.issue(LoginResult(user_id=uuid4(), organization_id=uuid4()))
    client.set_cookie("csrf_token", "csrf-token-123", path="/api/v1/auth")
    response = client.post(
        "/api/v1/auth/password/change",
        headers={
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "csrf-token-123",
        },
        json={
            "current_password": "OldPassword123!",
            "new_password": "NewSecurePassword123!",
        },
    )
    assert response.status_code == 204


def test_change_password_validation_error(
    client: FlaskClient, access_tokens: AccessTokenService
) -> None:
    """Invalid passwords (short, wrong, or missing) return 400 ProblemDetails."""
    token = access_tokens.issue(LoginResult(user_id=uuid4(), organization_id=uuid4()))
    client.set_cookie("csrf_token", "csrf-token-123", path="/api/v1/auth")

    # Short password
    response = client.post(
        "/api/v1/auth/password/change",
        headers={
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "csrf-token-123",
        },
        json={"current_password": "OldPassword123!", "new_password": "short"},
    )
    assert response.status_code == 400
    assert response.mimetype == "application/problem+json"
    assert "at least 12 characters" in response.get_json()["detail"]

    # Wrong current password
    response = client.post(
        "/api/v1/auth/password/change",
        headers={
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "csrf-token-123",
        },
        json={
            "current_password": "wrong-password",
            "new_password": "NewSecurePassword123!",
        },
    )
    assert response.status_code == 400
    assert response.mimetype == "application/problem+json"
    assert "Current password is incorrect" in response.get_json()["detail"]
