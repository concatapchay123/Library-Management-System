"""Argon2id password hashing and constant-work verification."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordService:
    """Keep password algorithm selection inside one domain boundary."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher(type=Type.ID)

    def hash(self, password: str) -> str:
        """Return an Argon2id encoded hash without retaining plaintext."""
        return self._hasher.hash(password)

    def verify(self, password: str, encoded_hash: str) -> bool:
        """Verify one password and treat malformed stored hashes as a failure."""
        try:
            return self._hasher.verify(encoded_hash, password)
        except (InvalidHashError, VerificationError):
            return False
