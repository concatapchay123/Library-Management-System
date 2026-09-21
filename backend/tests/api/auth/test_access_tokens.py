"""HTTP and cryptographic contracts for short-lived access JWTs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask.testing import FlaskClient
import jwt
import pytest

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    JwtKey,
    TokenVerificationError,
)
from openlibrary.modules.core.application.login import LoginResult


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
ISSUER = "https://identity.openlibraryos.example"
AUDIENCE = "openlibraryos-api"


@dataclass(slots=True)
class StubLoginService:
    """Return a fixed successful authentication result for HTTP tests."""

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
def signing_key() -> JwtKey:
    """Generate one deployment-like signing key without committing secret material."""

    return _jwt_key("current-2026-09")


def _jwt_key(key_id: str) -> JwtKey:
    """Create isolated key material for rotation-contract coverage."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return JwtKey(key_id=key_id, public_key_pem=public_pem, private_key_pem=private_pem)


@pytest.fixture
def access_tokens(signing_key: JwtKey) -> AccessTokenService:
    """Use a fixed clock so expiry behavior is deterministic."""

    return AccessTokenService(
        issuer=ISSUER,
        audience=AUDIENCE,
        access_token_ttl=timedelta(minutes=15),
        signing_key=signing_key,
        verification_keys={signing_key.key_id: signing_key.public_key_pem},
        now=lambda: NOW,
    )


@pytest.fixture
def login_result() -> LoginResult:
    """Represent the credential-verification output from BE-007."""

    return LoginResult(user_id=uuid4(), organization_id=uuid4())


def test_issued_access_token_is_rs256_bound_and_contains_only_identity_claims(
    access_tokens: AccessTokenService, login_result: LoginResult, signing_key: JwtKey
) -> None:
    """An access token carries verified identifiers, never profile or credential data."""

    token = access_tokens.issue(login_result)

    header = jwt.get_unverified_header(token)
    claims = jwt.decode(
        token,
        signing_key.public_key_pem,
        algorithms=["RS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={"verify_exp": False},
    )

    assert header == {"alg": "RS256", "kid": "current-2026-09", "typ": "JWT"}
    assert claims["sub"] == str(login_result.user_id)
    assert claims["organization_id"] == str(login_result.organization_id)
    assert UUID(claims["session_id"])
    assert claims["token_version"] == 1
    assert set(claims) == {
        "iss",
        "aud",
        "sub",
        "organization_id",
        "session_id",
        "iat",
        "nbf",
        "exp",
        "token_version",
    }


@pytest.mark.parametrize(
    ("claims", "header", "algorithm", "key"),
    [
        ({"iss": "https://other.example"}, None, "RS256", "private"),
        ({"aud": "other-api"}, None, "RS256", "private"),
        (
            {"exp": int((NOW - timedelta(seconds=1)).timestamp())},
            None,
            "RS256",
            "private",
        ),
        ({}, {"kid": "retired-key"}, "RS256", "private"),
        ({}, None, "HS256", "shared-secret-with-at-least-thirty-two-characters"),
        ({"token_version": 2}, None, "RS256", "private"),
    ],
    ids=[
        "issuer",
        "audience",
        "expiration",
        "unknown-kid",
        "algorithm",
        "token-version",
    ],
)
def test_verifier_rejects_each_untrusted_token_variant(
    access_tokens: AccessTokenService,
    login_result: LoginResult,
    signing_key: JwtKey,
    claims: dict[str, object],
    header: dict[str, str] | None,
    algorithm: str,
    key: str,
) -> None:
    """Verification fails closed for every security boundary independently."""

    base_claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(login_result.user_id),
        "organization_id": str(login_result.organization_id),
        "session_id": str(uuid4()),
        "iat": int(NOW.timestamp()),
        "nbf": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
        "token_version": 1,
    }
    base_claims.update(claims)
    token = jwt.encode(
        base_claims,
        signing_key.private_key_pem if key == "private" else key,
        algorithm=algorithm,
        headers={"kid": signing_key.key_id, **(header or {})},
    )

    with pytest.raises(TokenVerificationError):
        access_tokens.verify(token)


def test_rotation_keeps_a_previous_public_key_valid_until_old_tokens_expire(
    login_result: LoginResult, signing_key: JwtKey
) -> None:
    """A key ring verifies tokens issued before the active signing key changed."""

    prior = AccessTokenService(
        issuer=ISSUER,
        audience=AUDIENCE,
        access_token_ttl=timedelta(minutes=15),
        signing_key=signing_key,
        verification_keys={signing_key.key_id: signing_key.public_key_pem},
        now=lambda: NOW,
    )
    old_token = prior.issue(login_result)
    replacement = _jwt_key("current-2026-10")
    after_rotation = AccessTokenService(
        issuer=ISSUER,
        audience=AUDIENCE,
        access_token_ttl=timedelta(minutes=15),
        signing_key=replacement,
        verification_keys={
            signing_key.key_id: signing_key.public_key_pem,
            replacement.key_id: replacement.public_key_pem,
        },
        now=lambda: NOW,
    )

    principal = after_rotation.verify(old_token)

    assert principal.user_id == login_result.user_id
    assert principal.organization_id == login_result.organization_id


def test_login_issues_token_and_me_exposes_only_verified_principal(
    access_tokens: AccessTokenService, login_result: LoginResult
) -> None:
    """The protected endpoint derives tenant identity only from the bearer token."""

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            login_service=StubLoginService(login_result),
            access_tokens=access_tokens,
        )
    )
    client: FlaskClient = app.test_client()

    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "campus-a",
            "email": "librarian@example.test",
            "password": "correct-horse-battery-staple",
        },
    )
    token = login.get_json()["access_token"]
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert login.status_code == 200
    assert login.get_json()["token_type"] == "Bearer"
    assert response.status_code == 200
    assert response.get_json() == {
        "user_id": str(login_result.user_id),
        "organization_id": str(login_result.organization_id),
        "session_id": str(access_tokens.verify(token).session_id),
    }


def test_me_rejects_missing_or_untrusted_bearer_tokens(
    access_tokens: AccessTokenService, login_result: LoginResult
) -> None:
    """A protected route never creates a principal from request-supplied identity."""

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            login_service=StubLoginService(login_result),
            access_tokens=access_tokens,
        )
    )
    client: FlaskClient = app.test_client()

    missing = client.get("/api/v1/auth/me")
    untrusted = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer malformed.token.value"}
    )

    assert missing.status_code == untrusted.status_code == 401
    assert missing.mimetype == untrusted.mimetype == "application/problem+json"
