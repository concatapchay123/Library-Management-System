"""Issue and verify the deliberately small access-token principal."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
import jwt
from jwt import InvalidTokenError

from openlibrary.modules.core.application.login import LoginResult


class TokenVerificationError(ValueError):
    """Raised when a bearer token cannot establish a trustworthy principal."""


@dataclass(frozen=True, slots=True)
class JwtKey:
    """One configured signing key and its public verification material."""

    key_id: str
    public_key_pem: bytes
    private_key_pem: bytes | None = None


@dataclass(frozen=True, slots=True)
class Principal:
    """The complete identity surface available to protected application code."""

    user_id: UUID
    organization_id: UUID
    session_id: UUID


Clock = Callable[[], datetime]


class AccessTokenService:
    """Pin JWT verification to one algorithm, issuer, audience, and configured keys."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        access_token_ttl: timedelta,
        signing_key: JwtKey,
        verification_keys: Mapping[str, bytes],
        now: Clock | None = None,
    ) -> None:
        if signing_key.private_key_pem is None:
            raise ValueError("The active JWT signing key requires private material")
        if not issuer or not audience:
            raise ValueError("JWT issuer and audience are required")
        if access_token_ttl <= timedelta(0):
            raise ValueError("Access-token lifetime must be positive")
        if signing_key.key_id not in verification_keys:
            raise ValueError(
                "The active JWT signing key requires public verification material"
            )
        private_key = _rsa_private_key(signing_key.private_key_pem)
        active_public_key = _rsa_public_key(verification_keys[signing_key.key_id])
        for public_key_pem in verification_keys.values():
            _rsa_public_key(public_key_pem)
        if (
            private_key.public_key().public_numbers()
            != active_public_key.public_numbers()
        ):
            raise ValueError("The active JWT private and public keys do not match")
        self._issuer = issuer
        self._audience = audience
        self._access_token_ttl = access_token_ttl
        self._signing_key = signing_key
        self._verification_keys = dict(verification_keys)
        self._now = now or _utc_now

    @property
    def expires_in(self) -> int:
        """Return the token lifetime for the OAuth-compatible response envelope."""
        return int(self._access_token_ttl.total_seconds())

    def issue(self, result: LoginResult, *, session_id: UUID | None = None) -> str:
        """Sign one short-lived token using only server-derived identity values."""
        issued_at = self._now()
        if issued_at.tzinfo is None:
            raise ValueError("The JWT clock must return an aware datetime")
        claims = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(result.user_id),
            "organization_id": str(result.organization_id),
            "session_id": str(session_id or uuid4()),
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + self._access_token_ttl,
            "token_version": 1,
        }
        private_key = self._signing_key.private_key_pem
        assert private_key is not None
        return jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": self._signing_key.key_id},
        )

    def verify(self, token: str) -> Principal:
        """Verify all trust boundaries before converting claims into identifiers."""
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise TokenVerificationError("Unsupported JWT algorithm")
            key_id = header.get("kid")
            if not isinstance(key_id, str) or not key_id:
                raise TokenVerificationError("JWT key identifier is invalid")
            public_key = self._verification_keys.get(key_id)
            if public_key is None:
                raise TokenVerificationError("JWT key identifier is unknown")
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "organization_id",
                        "session_id",
                        "iat",
                        "nbf",
                        "exp",
                        "token_version",
                    ],
                },
            )
            self._verify_time_claims(claims)
            token_version = claims["token_version"]
            if (
                isinstance(token_version, bool)
                or not isinstance(token_version, int)
                or token_version != 1
            ):
                raise TokenVerificationError("JWT token version is invalid")
            return Principal(
                user_id=UUID(_claim_string(claims, "sub")),
                organization_id=UUID(_claim_string(claims, "organization_id")),
                session_id=UUID(_claim_string(claims, "session_id")),
            )
        except (InvalidTokenError, TypeError, ValueError) as error:
            raise TokenVerificationError("Access token verification failed") from error

    def _verify_time_claims(self, claims: Mapping[str, object]) -> None:
        """Validate JWT time claims against the injectable UTC clock."""
        now = int(self._now().timestamp())
        if _timestamp(claims, "exp") <= now:
            raise TokenVerificationError("JWT has expired")
        if _timestamp(claims, "nbf") > now:
            raise TokenVerificationError("JWT is not active")
        if _timestamp(claims, "iat") > now:
            raise TokenVerificationError("JWT was issued in the future")


def _claim_string(claims: Mapping[str, object], name: str) -> str:
    value = claims[name]
    if not isinstance(value, str):
        raise TokenVerificationError(f"JWT {name} claim is invalid")
    return value


def _timestamp(claims: Mapping[str, object], name: str) -> int:
    value = claims[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TokenVerificationError(f"JWT {name} claim is invalid")
    return value


def _rsa_private_key(key_pem: bytes) -> RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(key_pem, password=None)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "The active JWT private key is not valid RSA material"
        ) from error
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("The active JWT private key is not RSA material")
    return key


def _rsa_public_key(key_pem: bytes) -> RSAPublicKey:
    try:
        key = serialization.load_pem_public_key(key_pem)
    except (TypeError, ValueError) as error:
        raise ValueError("A JWT public key is not valid RSA material") from error
    if not isinstance(key, RSAPublicKey):
        raise ValueError("A JWT public key is not RSA material")
    return key


def _utc_now() -> datetime:
    return datetime.now(UTC)
