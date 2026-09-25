import React, { useState, useMemo, useEffect } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { Button, Input, Dialog, LoadingSkeleton } from '../../shared/components';
import { InvoicesViewProps } from './types';
import { PublicLibraryInvoice, apiClient } from '../../shared/api';

export function InvoicesView({
  invoices,
  isLoading,
  onRefresh,
  onError,
}: InvoicesViewProps) {
  const tokens = useTokens();
  const [searchQuery, setSearchQuery] = useState('');
  const [voidTargetInvoice, setVoidTargetInvoice] = useState<PublicLibraryInvoice | null>(null);
  const [voidReason, setVoidReason] = useState('');
  const [isSubmittingVoid, setIsSubmittingVoid] = useState(false);
  const [localInvoices, setLocalInvoices] = useState<PublicLibraryInvoice[]>(invoices);

  useEffect(() => {
    setLocalInvoices(invoices);
  }, [invoices]);

  const filteredInvoices = useMemo(() => {
    if (!searchQuery.trim()) return localInvoices;
    const q = searchQuery.toLowerCase().trim();
    return localInvoices.filter((inv) =>
      inv.invoice_number.toLowerCase().includes(q) ||
      inv.member_id.toLowerCase().includes(q) ||
      inv.status.toLowerCase().includes(q)
    );
  }, [localInvoices, searchQuery]);

  async function handleConfirmVoid(e: React.FormEvent) {
    e.preventDefault();
    if (!voidTargetInvoice) return;
    if (!voidReason.trim()) return;

    setIsSubmittingVoid(true);
    try {
      const updated = await apiClient.publicLibrary.invoices.void(voidTargetInvoice.invoice_id, {
        reason: voidReason.trim(),
      });
      setLocalInvoices((prev) =>
        prev.map((inv) => (inv.invoice_id === updated.invoice_id ? updated : inv))
      );
      setVoidTargetInvoice(null);
      setVoidReason('');
      onRefresh();
    } catch (err) {
      setVoidTargetInvoice(null);
      setVoidReason('');
      onError(err);
    } finally {
      setIsSubmittingVoid(false);
    }
  }

  const outerRadius = 12;
  const paddingVal = 20;
  const innerRadius = calcNestedRadius(outerRadius, paddingVal);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xl }}>
      {/* Search and Header Controls */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-end',
          gap: tokens.spacing.md,
        }}
      >
        <div style={{ flex: '1 1 300px' }}>
          <Input
            id="invoice-search"
            label="Filter Invoices"
            placeholder="Filter invoices by number, member ID, or status..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <Button
          variant="secondary"
          onClick={onRefresh}
          style={{ height: '40px' }}
        >
          Refresh Records
        </Button>
      </div>

      {/* Invoices List */}
      {isLoading ? (
        <LoadingSkeleton lines={3} />
      ) : filteredInvoices.length === 0 ? (
        <div
          style={{
            padding: `${tokens.spacing['2xl']}`,
            textAlign: 'center',
            backgroundColor: tokens.colors.surfaceAlt,
            borderRadius: tokens.radius.lg,
            border: `1px dashed ${tokens.colors.border}`,
            color: tokens.colors.textMuted,
          }}
        >
          No library invoice records found.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}>
          {filteredInvoices.map((invoice) => {
            const canVoid = invoice.status === 'issued' || invoice.status === 'partially_paid';

            return (
              <article
                key={invoice.invoice_id}
                style={{
                  backgroundColor: tokens.colors.surface,
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: `${outerRadius}px`,
                  padding: `${paddingVal}px`,
                  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.04)',
                }}
              >
                {/* Invoice Header */}
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: tokens.spacing.sm,
                    marginBottom: tokens.spacing.md,
                    paddingBottom: tokens.spacing.sm,
                    borderBottom: `1px solid ${tokens.colors.borderMuted}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.md }}>
                    <span
                      style={{
                        fontFamily: tokens.typography.monoFontFamily,
                        fontSize: tokens.typography.fontSizes.lg,
                        fontWeight: tokens.typography.fontWeights.bold,
                        color: tokens.colors.textPrimary,
                      }}
                    >
                      {invoice.invoice_number}
                    </span>
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        fontFamily: tokens.typography.monoFontFamily,
                        color: tokens.colors.textMuted,
                      }}
                    >
                      Member ID: {invoice.member_id}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
                    {/* Immutable Issued Invoice Badge */}
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: tokens.spacing.xs,
                        padding: '4px 8px',
                        borderRadius: tokens.radius.sm,
                        fontSize: tokens.typography.fontSizes.xs,
                        fontWeight: tokens.typography.fontWeights.medium,
                        backgroundColor: tokens.colors.surfaceElevated,
                        color: tokens.colors.textSecondary,
                        border: `1px solid ${tokens.colors.border}`,
                      }}
                    >
                      🔒 Immutable Issued Invoice
                    </span>

                    {/* Status badge with text and non-color cues */}
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: tokens.spacing.xs,
                        padding: '4px 10px',
                        borderRadius: tokens.radius.sm,
                        fontSize: tokens.typography.fontSizes.xs,
                        fontWeight: tokens.typography.fontWeights.semibold,
                        backgroundColor:
                          invoice.status === 'paid'
                            ? tokens.colors.status.success.bg
                            : invoice.status === 'void'
                            ? tokens.colors.status.danger.bg
                            : invoice.status === 'issued'
                            ? tokens.colors.status.info.bg
                            : tokens.colors.status.warning.bg,
                        color:
                          invoice.status === 'paid'
                            ? tokens.colors.status.success.color
                            : invoice.status === 'void'
                            ? tokens.colors.status.danger.color
                            : invoice.status === 'issued'
                            ? tokens.colors.status.info.color
                            : tokens.colors.status.warning.color,
                        border: `1px solid ${
                          invoice.status === 'paid'
                            ? tokens.colors.status.success.border
                            : invoice.status === 'void'
                            ? tokens.colors.status.danger.border
                            : invoice.status === 'issued'
                            ? tokens.colors.status.info.border
                            : tokens.colors.status.warning.border
                        }`,
                      }}
                    >
                      {invoice.status === 'issued' && '● Issued'}
                      {invoice.status === 'paid' && '✓ Paid'}
                      {invoice.status === 'void' && '⊘ Void'}
                      {invoice.status === 'partially_paid' && '◒ Partially Paid'}
                      {invoice.status === 'cancelled' && '✕ Cancelled'}
                    </span>
                  </div>
                </div>

                {/* Line Items Table */}
                <div style={{ marginBottom: tokens.spacing.md }}>
                  <h4
                    style={{
                      margin: `0 0 ${tokens.spacing.xs} 0`,
                      fontSize: tokens.typography.fontSizes.sm,
                      fontWeight: tokens.typography.fontWeights.semibold,
                      color: tokens.colors.textSecondary,
                    }}
                  >
                    Billed Line Items
                  </h4>

                  <div
                    style={{
                      overflowX: 'auto',
                      border: `1px solid ${tokens.colors.borderMuted}`,
                      borderRadius: `${innerRadius}px`,
                      backgroundColor: tokens.colors.surfaceAlt,
                    }}
                  >
                    <table
                      style={{
                        width: '100%',
                        borderCollapse: 'collapse',
                        fontSize: tokens.typography.fontSizes.sm,
                      }}
                    >
                      <thead>
                        <tr
                          style={{
                            borderBottom: `1px solid ${tokens.colors.borderMuted}`,
                            backgroundColor: tokens.colors.surfaceElevated,
                            color: tokens.colors.textSecondary,
                            textAlign: 'left',
                          }}
                        >
                          <th style={{ padding: '8px 12px', width: '50px' }}>#</th>
                          <th style={{ padding: '8px 12px' }}>Description</th>
                          <th style={{ padding: '8px 12px', width: '70px', textAlign: 'right' }}>Qty</th>
                          <th style={{ padding: '8px 12px', width: '120px', textAlign: 'right' }}>Unit Price</th>
                          <th style={{ padding: '8px 12px', width: '120px', textAlign: 'right' }}>Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {invoice.lines.map((line) => (
                          <tr
                            key={line.invoice_line_id}
                            style={{
                              borderBottom: `1px solid ${tokens.colors.borderMuted}`,
                            }}
                          >
                            <td style={{ padding: '8px 12px', color: tokens.colors.textMuted }}>
                              {line.line_number}
                            </td>
                            <td style={{ padding: '8px 12px', color: tokens.colors.textPrimary }}>
                              {line.description}
                            </td>
                            <td style={{ padding: '8px 12px', textAlign: 'right', color: tokens.colors.textPrimary }}>
                              {line.quantity}
                            </td>
                            <td
                              style={{
                                padding: '8px 12px',
                                textAlign: 'right',
                                fontFamily: tokens.typography.monoFontFamily,
                                color: tokens.colors.textSecondary,
                              }}
                            >
                              {invoice.currency} {line.unit_price}
                            </td>
                            <td
                              style={{
                                padding: '8px 12px',
                                textAlign: 'right',
                                fontFamily: tokens.typography.monoFontFamily,
                                fontWeight: tokens.typography.fontWeights.medium,
                                color: tokens.colors.textPrimary,
                              }}
                            >
                              {invoice.currency} {line.amount}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Read-Only Totals & Breakdown */}
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: tokens.spacing.md,
                    paddingTop: tokens.spacing.sm,
                    borderTop: `1px solid ${tokens.colors.borderMuted}`,
                  }}
                >
                  <div
                    style={{
                      fontSize: tokens.typography.fontSizes.xs,
                      color: tokens.colors.textMuted,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: tokens.spacing.xs,
                    }}
                  >
                    <span>Issued: {new Date(invoice.issued_at).toLocaleString()}</span>
                    {invoice.due_at && <span>Due Date: {new Date(invoice.due_at).toLocaleDateString()}</span>}
                    <span>Invoice ID: {invoice.invoice_id}</span>
                  </div>

                  {/* Strictly Read-Only Formatted Financial Totals */}
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: tokens.spacing.xs,
                      minWidth: '220px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: tokens.typography.fontSizes.sm }}>
                      <span style={{ color: tokens.colors.textSecondary }}>Subtotal:</span>
                      <span style={{ fontFamily: tokens.typography.monoFontFamily, color: tokens.colors.textPrimary }}>
                        {invoice.currency} {invoice.subtotal}
                      </span>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: tokens.typography.fontSizes.sm }}>
                      <span style={{ color: tokens.colors.textSecondary }}>Tax:</span>
                      <span style={{ fontFamily: tokens.typography.monoFontFamily, color: tokens.colors.textPrimary }}>
                        {invoice.currency} {invoice.tax}
                      </span>
                    </div>

                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: tokens.typography.fontSizes.md,
                        fontWeight: tokens.typography.fontWeights.bold,
                        paddingTop: tokens.spacing.xs,
                        borderTop: `1px solid ${tokens.colors.border}`,
                      }}
                    >
                      <span style={{ color: tokens.colors.textPrimary }}>Total:</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.xs }}>
                        <span style={{ fontFamily: tokens.typography.monoFontFamily, color: tokens.colors.primary }}>
                          {invoice.currency}
                        </span>
                        <input
                          id={`invoice-${invoice.invoice_id}-total`}
                          aria-label={`Total for invoice ${invoice.invoice_number}`}
                          readOnly
                          value={invoice.total}
                          style={{
                            width: '100px',
                            fontFamily: tokens.typography.monoFontFamily,
                            fontWeight: tokens.typography.fontWeights.bold,
                            fontSize: tokens.typography.fontSizes.md,
                            color: tokens.colors.textPrimary,
                            backgroundColor: tokens.colors.surfaceAlt,
                            border: `1px solid ${tokens.colors.border}`,
                            borderRadius: tokens.radius.sm,
                            padding: '2px 6px',
                            textAlign: 'right',
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {canVoid && (
                  <div
                    style={{
                      marginTop: tokens.spacing.md,
                      display: 'flex',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => {
                        setVoidTargetInvoice(invoice);
                        setVoidReason('');
                      }}
                    >
                      Void Invoice
                    </Button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      {/* Void Invoice Dialog */}
      <Dialog
        isOpen={Boolean(voidTargetInvoice)}
        onClose={() => {
          if (!isSubmittingVoid) {
            setVoidTargetInvoice(null);
            setVoidReason('');
          }
        }}
        title="Void Invoice"
      >
        {voidTargetInvoice && (
          <form
            onSubmit={handleConfirmVoid}
            style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}
          >
            <p
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.sm,
                color: tokens.colors.textSecondary,
              }}
            >
              Are you sure you want to void invoice{' '}
              <strong>{voidTargetInvoice.invoice_number}</strong> with total of{' '}
              <strong>
                {voidTargetInvoice.currency} {voidTargetInvoice.total}
              </strong>
              ? Voiding is irreversible.
            </p>

            <Input
              id="void-reason"
              label="Reason for voiding"
              placeholder="e.g. Billed to incorrect patron account, clerical error..."
              value={voidReason}
              onChange={(e) => setVoidReason(e.target.value)}
              required
            />

            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: tokens.spacing.md,
                marginTop: tokens.spacing.md,
              }}
            >
              <Button
                type="button"
                variant="ghost"
                onClick={() => setVoidTargetInvoice(null)}
                disabled={isSubmittingVoid}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="danger"
                disabled={isSubmittingVoid || !voidReason.trim()}
              >
                {isSubmittingVoid ? 'Voiding...' : 'Confirm Void'}
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  );
}
