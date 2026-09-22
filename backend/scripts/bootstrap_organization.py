"""Create an organization through the deployment-only migration identity."""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine

from openlibrary.modules.core.infrastructure.organization_bootstrap import (
    PrivilegedOrganizationBootstrapper,
)


def main() -> None:
    """Run a deliberately non-HTTP bootstrap with operator-provided metadata."""
    parser = argparse.ArgumentParser(
        description="Bootstrap an OpenLibraryOS organization"
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--organization-type", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--settings-json", default="{}")
    arguments = parser.parse_args()
    try:
        settings = json.loads(arguments.settings_json)
    except json.JSONDecodeError as error:
        raise SystemExit("--settings-json must be valid JSON") from error
    if not isinstance(settings, dict):
        raise SystemExit("--settings-json must be a JSON object")
    migration_url = _required("DATABASE_MIGRATION_URL")
    engine = create_engine(migration_url)
    try:
        organization_id = PrivilegedOrganizationBootstrapper(engine.connect).create(
            name=arguments.name,
            slug=arguments.slug,
            organization_type=arguments.organization_type,
            timezone=arguments.timezone,
            settings=settings,
        )
    finally:
        engine.dispose()
    print(f"Organization bootstrapped: {organization_id}")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


if __name__ == "__main__":
    main()
