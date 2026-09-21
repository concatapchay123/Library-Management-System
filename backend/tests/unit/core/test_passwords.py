"""Argon2id password-value behavior."""

from openlibrary.modules.core.domain.passwords import PasswordService


def test_password_service_hashes_and_verifies_only_with_argon2id() -> None:
    """Changing the algorithm or accepting the wrong secret must break login safety."""
    service = PasswordService()

    encoded_hash = service.hash("correct-horse-battery-staple")

    assert encoded_hash.startswith("$argon2id$")
    assert service.verify("correct-horse-battery-staple", encoded_hash)
    assert not service.verify("wrong-password", encoded_hash)
