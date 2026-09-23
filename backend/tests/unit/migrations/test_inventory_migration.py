"""Static SQL contracts for the BE-013 locations and copies migration."""

from __future__ import annotations

from pathlib import Path


def test_inventory_migration_declares_tenant_controls_and_composite_fks() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0009_locations_and_book_copies.py"
    ).read_text(encoding="utf-8")

    # Locations table & constraints
    assert "CREATE TABLE core.locations" in migration
    assert "CONSTRAINT PK_core_locations PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_core_locations_organization_location UNIQUE (organization_id, location_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_core_locations_organization_code UNIQUE (organization_id, code)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_locations_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_locations_parent FOREIGN KEY (organization_id, parent_location_id) REFERENCES core.locations (organization_id, location_id)"
        in migration
    )
    assert '_add_tenant_predicates("core.locations")' in migration

    # Book copies table & constraints
    assert "CREATE TABLE core.book_copies" in migration
    assert "CONSTRAINT PK_core_book_copies PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_core_book_copies_organization_copy UNIQUE (organization_id, copy_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_core_book_copies_organization_barcode UNIQUE (organization_id, barcode)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_book_copies_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_book_copies_book FOREIGN KEY (organization_id, book_id) REFERENCES core.books (organization_id, book_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_book_copies_location FOREIGN KEY (organization_id, location_id) REFERENCES core.locations (organization_id, location_id)"
        in migration
    )
    assert "IX_core_book_copies_tenant_book_status" in migration
    assert "IX_core_book_copies_tenant_location" in migration
    assert '_add_tenant_predicates("core.book_copies")' in migration
