"""Static SQL contracts and unit tests for the BE-023 public library fines and invoices migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_fines_invoices_migration_declares_tenant_controls_and_composite_fks() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0017_public_library_fines_invoices.py"
    ).read_text(encoding="utf-8")

    # Table 1: fines
    assert "CREATE TABLE public_library.fines" in migration
    assert "CONSTRAINT PK_public_library_fines PRIMARY KEY" in migration
    assert "amount decimal(19,4) NOT NULL" in migration
    assert "CONSTRAINT CK_public_library_fines_amount CHECK (amount >= 0)" in migration
    assert (
        "CONSTRAINT UQ_public_library_fines_org_fine UNIQUE (organization_id, fine_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_fines_organization FOREIGN KEY (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_fines_member FOREIGN KEY (organization_id, member_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_fines_loan FOREIGN KEY (organization_id, loan_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.fines")' in migration

    # Table 2: payments
    assert "CREATE TABLE public_library.payments" in migration
    assert "CONSTRAINT PK_public_library_payments PRIMARY KEY" in migration
    assert "amount decimal(19,4) NOT NULL" in migration
    assert (
        "CONSTRAINT UQ_public_library_payments_org_payment UNIQUE (organization_id, payment_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_payments_organization FOREIGN KEY (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_payments_member FOREIGN KEY (organization_id, member_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.payments")' in migration

    # Table 3: invoices
    assert "CREATE TABLE public_library.invoices" in migration
    assert "CONSTRAINT PK_public_library_invoices PRIMARY KEY" in migration
    assert "subtotal decimal(19,4) NOT NULL" in migration
    assert "total decimal(19,4) NOT NULL" in migration
    assert (
        "CONSTRAINT UQ_public_library_invoices_org_invoice UNIQUE (organization_id, invoice_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_public_library_invoices_org_number UNIQUE (organization_id, invoice_number)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_invoices_organization FOREIGN KEY (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_invoices_member FOREIGN KEY (organization_id, member_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.invoices")' in migration

    # Table 4: invoice_lines
    assert "CREATE TABLE public_library.invoice_lines" in migration
    assert "CONSTRAINT PK_public_library_invoice_lines PRIMARY KEY" in migration
    assert "quantity int NOT NULL" in migration
    assert "unit_price decimal(19,4) NOT NULL" in migration
    assert "amount decimal(19,4) NOT NULL" in migration
    assert (
        "CONSTRAINT UQ_public_library_inv_lines_org_line UNIQUE (organization_id, invoice_line_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_public_library_inv_lines_org_inv_line UNIQUE (organization_id, invoice_id, line_number)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_inv_lines_invoice FOREIGN KEY (organization_id, invoice_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.invoice_lines")' in migration

    # Table 5: payment_allocations
    assert "CREATE TABLE public_library.payment_allocations" in migration
    assert "CONSTRAINT PK_public_library_payment_allocations PRIMARY KEY" in migration
    assert "amount decimal(19,4) NOT NULL" in migration
    assert (
        "CONSTRAINT UQ_public_library_alloc_org_alloc UNIQUE (organization_id, allocation_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_alloc_payment FOREIGN KEY (organization_id, payment_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_alloc_fine FOREIGN KEY (organization_id, fine_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.payment_allocations")' in migration


def test_fines_invoices_downgrade_removes_predicates_and_drops_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0017_public_library_fines_invoices")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    # Drops indexes first
    assert (
        "DROP INDEX IX_public_library_alloc_payment ON public_library.payment_allocations"
        in statements
    )
    assert (
        "DROP INDEX IX_public_library_alloc_fine ON public_library.payment_allocations"
        in statements
    )
    assert (
        "DROP INDEX IX_public_library_inv_lines_invoice ON public_library.invoice_lines"
        in statements
    )
    assert (
        "DROP INDEX IX_public_library_invoices_member_status ON public_library.invoices"
        in statements
    )
    assert (
        "DROP INDEX IX_public_library_payments_member_status ON public_library.payments"
        in statements
    )
    assert (
        "DROP INDEX IX_public_library_fines_loan ON public_library.fines" in statements
    )
    assert (
        "DROP INDEX IX_public_library_fines_member_status ON public_library.fines"
        in statements
    )

    # Drops tables in reverse order
    assert "DROP TABLE public_library.payment_allocations" in statements
    assert "DROP TABLE public_library.invoice_lines" in statements
    assert "DROP TABLE public_library.invoices" in statements
    assert "DROP TABLE public_library.payments" in statements
    assert "DROP TABLE public_library.fines" in statements
