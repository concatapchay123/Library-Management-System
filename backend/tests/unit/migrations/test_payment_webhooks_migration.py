"""Static SQL contracts and unit tests for the BE-024 payment webhooks migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path


def test_payment_webhooks_migration_declares_tenant_controls_and_uniqueness() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0018_public_library_payment_webhooks.py"
    ).read_text(encoding="utf-8")

    # Payment status check constraint
    assert "CK_public_library_payments_status" in migration
    assert (
        "CHECK (status IN ('pending', 'authorized', 'succeeded', 'failed', 'refunded', 'partially_refunded', 'disputed'))"
        in migration
    )

    # Filtered unique index on (organization_id, provider, provider_reference)
    assert "UQ_public_library_payments_provider_ref" in migration
    assert "WHERE provider_reference IS NOT NULL" in migration

    # Table: payment_events
    assert "CREATE TABLE public_library.payment_events" in migration
    assert "CONSTRAINT PK_public_library_payment_events PRIMARY KEY" in migration
    assert "organization_id uniqueidentifier NOT NULL" in migration
    assert "provider varchar(64) NOT NULL" in migration
    assert "provider_event_id varchar(255) NOT NULL" in migration
    assert "event_type varchar(64) NOT NULL" in migration
    assert "payload_hash varchar(64) NOT NULL" in migration
    assert (
        "CONSTRAINT UQ_public_library_pe_event UNIQUE (organization_id, provider, provider_event_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_pe_org FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_pe_payment FOREIGN KEY (organization_id, payment_id) REFERENCES public_library.payments (organization_id, payment_id)"
        in migration
    )

    # RLS predicates
    assert '_add_tenant_predicates("public_library.payment_events")' in migration
    assert '_drop_tenant_predicates("public_library.payment_events")' in migration

    # Downgrade drops
    assert (
        "DROP INDEX IX_public_library_pe_payment ON public_library.payment_events"
        in migration
    )
    assert (
        "DROP INDEX IX_public_library_pe_provider ON public_library.payment_events"
        in migration
    )
    assert "DROP TABLE public_library.payment_events" in migration
    assert (
        "DROP INDEX UQ_public_library_payments_provider_ref ON public_library.payments"
        in migration
    )
    assert (
        "ALTER TABLE public_library.payments DROP CONSTRAINT CK_public_library_payments_status"
        in migration
    )


def test_payment_webhooks_migration_revisions_chain() -> None:
    module = import_module("migrations.versions.0018_public_library_payment_webhooks")
    assert module.revision == "0018_public_library_payment_webhooks"
    assert module.down_revision == "0017_public_library_fines_invoices"
