"""The platform bootstrap path must remain outside ordinary tenant HTTP flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from openlibrary.modules.core.infrastructure.organization_bootstrap import (
    PrivilegedOrganizationBootstrapper,
)


@dataclass
class _Connection:
    statements: list[str] = field(default_factory=list)
    parameters: list[dict[str, object]] = field(default_factory=list)

    def execute(self, statement: object, parameters: dict[str, object]) -> None:
        self.statements.append(str(statement))
        self.parameters.append(parameters)

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def commit(self) -> None:
        return None


def test_bootstrap_calls_only_the_privileged_stored_procedure() -> None:
    connection = _Connection()
    bootstrapper = PrivilegedOrganizationBootstrapper(lambda: connection)

    organization_id = bootstrapper.create(
        name="Campus A",
        slug="campus-a",
        organization_type="education",
        timezone="Asia/Bangkok",
        settings={"locale": "vi"},
    )

    assert isinstance(organization_id, UUID)
    assert "EXEC core.bootstrap_organization" in connection.statements[0]
    assert connection.parameters[0]["organization_id"] == str(organization_id)
    assert connection.parameters[0]["settings_json"] == '{"locale":"vi"}'
