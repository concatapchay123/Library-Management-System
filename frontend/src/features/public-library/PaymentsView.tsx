import { useState, useMemo, useEffect, useContext } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { Button, Input, LoadingSkeleton } from '../../shared/components';
import { PaymentsViewProps } from './types';
import { PublicLibraryPayment, apiClient } from '../../shared/api';
import { AuthContext } from '../auth/context';

export function PaymentsView({
  payments,
  isLoading,
  onRefresh,
  onError,
}: PaymentsViewProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [searchQuery, setSearchQuery] = useState('');
  const [reconcilingId, setReconcilingId] = useState<string | null>(null);
  const [localPayments, setLocalPayments] = useState<PublicLibraryPayment[]>(payments);

  useEffect(() => {
    setLocalPayments(payments);
  }, [payments]);

  const filteredPayments = useMemo(() => {
    if (!searchQuery.trim()) return localPayments;
    const q = searchQuery.toLowerCase().trim();
    return localPayments.filter((p) =>
      p.provider.toLowerCase().includes(q) ||
      (p.provider_reference && p.provider_reference.toLowerCase().includes(q)) ||
      p.member_id.toLowerCase().includes(q) ||
      p.status.toLowerCase().includes(q)
    );
  }, [localPayments, searchQuery]);

  async function handleReconcile(payment: PublicLibraryPayment) {
    setReconcilingId(payment.payment_id);
    try {
      const reconciled = await apiClient.publicLibrary.payments.reconcile(payment.payment_id, { token });
      setLocalPayments((prev) =>
        prev.map((p) => (p.payment_id === reconciled.payment_id ? reconciled : p))
      );
    } catch (err) {
      onError(err);
    } finally {
      setReconcilingId(null);
    }
  }

  const outerRadius = 12;
  const paddingVal = 20;
  const innerRadius = calcNestedRadius(outerRadius, paddingVal);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xl }}>
      {/* Information Header on Payment Integrity */}
      <section
        role="region"
        aria-label="Payment Gateway Security & State Decisions"
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: `${outerRadius}px`,
          padding: `${paddingVal}px`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: tokens.spacing.md }}>
          <div
            aria-hidden="true"
            style={{
              width: '36px',
              height: '36px',
              borderRadius: `${innerRadius}px`,
              backgroundColor: tokens.colors.status.info.bg,
              color: tokens.colors.status.info.color,
              border: `1px solid ${tokens.colors.status.info.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: tokens.typography.fontWeights.bold,
              flexShrink: 0,
            }}
          >
            🛡
          </div>
          <div>
            <h3
              style={{
                margin: `0 0 ${tokens.spacing.xs} 0`,
                fontSize: tokens.typography.fontSizes.md,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textPrimary,
              }}
            >
              Payment Processing & Integrity Policy
            </h3>
            <p
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.sm,
                lineHeight: tokens.typography.lineHeights.normal,
                color: tokens.colors.textSecondary,
              }}
            >
              All payment states, signature verifications, and settlement decisions are made exclusively by the backend service. Card data, provider secret keys, and raw webhook materials are never processed or retained in the frontend.
            </p>
          </div>
        </div>
      </section>

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
            id="payment-search"
            label="Filter Payments"
            placeholder="Filter payments by provider, reference, or member ID..."
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

      {/* Payments List */}
      {isLoading ? (
        <LoadingSkeleton lines={3} />
      ) : filteredPayments.length === 0 ? (
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
          No payment records found.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}>
          {filteredPayments.map((payment) => {
            const isPending = payment.status === 'pending';
            const isSettled = payment.status === 'succeeded';
            const isFailed = payment.status === 'failed';
            const isPartiallyRefunded = payment.status === 'partially_refunded';
            const isRefunded = payment.status === 'refunded';
            const isDisputed = payment.status === 'disputed';

            return (
              <article
                key={payment.payment_id}
                style={{
                  backgroundColor: tokens.colors.surface,
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: `${outerRadius}px`,
                  padding: `${paddingVal}px`,
                  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.04)',
                }}
              >
                {/* Payment Header */}
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
                      {payment.currency} {payment.amount}
                    </span>
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        fontFamily: tokens.typography.monoFontFamily,
                        color: tokens.colors.textMuted,
                      }}
                    >
                      Member ID: {payment.member_id}
                    </span>
                  </div>

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
                      backgroundColor: isSettled
                        ? tokens.colors.status.success.bg
                        : isPending
                        ? tokens.colors.status.warning.bg
                        : isFailed
                        ? tokens.colors.status.danger.bg
                        : isRefunded || isPartiallyRefunded
                        ? tokens.colors.surfaceElevated
                        : tokens.colors.status.info.bg,
                      color: isSettled
                        ? tokens.colors.status.success.color
                        : isPending
                        ? tokens.colors.status.warning.color
                        : isFailed
                        ? tokens.colors.status.danger.color
                        : isRefunded || isPartiallyRefunded
                        ? tokens.colors.textSecondary
                        : tokens.colors.status.info.color,
                      border: `1px solid ${
                        isSettled
                          ? tokens.colors.status.success.border
                          : isPending
                          ? tokens.colors.status.warning.border
                          : isFailed
                          ? tokens.colors.status.danger.border
                          : isRefunded || isPartiallyRefunded
                          ? tokens.colors.border
                          : tokens.colors.status.info.border
                      }`,
                    }}
                  >
                    {isPending && '⏱ Pending'}
                    {isSettled && '✓ Settled'}
                    {isFailed && '✕ Failed'}
                    {isPartiallyRefunded && '◒ Partial Refund'}
                    {isRefunded && '↺ Refunded'}
                    {isDisputed && '⚠ Disputed'}
                    {!isPending && !isSettled && !isFailed && !isPartiallyRefunded && !isRefunded && !isDisputed && `● ${payment.status}`}
                  </span>
                </div>

                {/* Plain-Language Payment Details */}
                <div
                  style={{
                    backgroundColor: tokens.colors.surfaceAlt,
                    borderRadius: `${innerRadius}px`,
                    padding: tokens.spacing.md,
                    border: `1px solid ${tokens.colors.borderMuted}`,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: tokens.spacing.xs,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: tokens.spacing.md,
                      fontSize: tokens.typography.fontSizes.sm,
                      color: tokens.colors.textSecondary,
                    }}
                  >
                    <span>
                      <strong>Gateway Provider:</strong> {payment.provider}
                    </span>
                    {payment.provider_reference && (
                      <span>
                        <strong>Reference:</strong>{' '}
                        <code style={{ fontFamily: tokens.typography.monoFontFamily, fontSize: tokens.typography.fontSizes.xs }}>
                          {payment.provider_reference}
                        </code>
                      </span>
                    )}
                  </div>

                  {/* Explicit Explanation for Pending Payments */}
                  {isPending && (
                    <div
                      style={{
                        marginTop: tokens.spacing.xs,
                        padding: tokens.spacing.sm,
                        borderRadius: tokens.radius.sm,
                        backgroundColor: tokens.colors.status.warning.bg,
                        border: `1px solid ${tokens.colors.status.warning.border}`,
                        fontSize: tokens.typography.fontSizes.xs,
                        color: tokens.colors.status.warning.color,
                        display: 'flex',
                        alignItems: 'center',
                        gap: tokens.spacing.xs,
                      }}
                    >
                      <span>⏱</span>
                      <span>
                        Awaiting provider settlement or webhook confirmation. Status will update once reconciled by the payment gateway.
                      </span>
                    </div>
                  )}

                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: tokens.spacing.lg,
                      fontSize: tokens.typography.fontSizes.xs,
                      color: tokens.colors.textMuted,
                      marginTop: tokens.spacing.xs,
                    }}
                  >
                    <span>Created: {new Date(payment.created_at).toLocaleString()}</span>
                    {payment.paid_at && <span>Settled: {new Date(payment.paid_at).toLocaleString()}</span>}
                    <span>Payment ID: {payment.payment_id}</span>
                  </div>
                </div>

                {/* Reconcile action for pending payments */}
                {isPending && (
                  <div
                    style={{
                      marginTop: tokens.spacing.md,
                      display: 'flex',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleReconcile(payment)}
                      disabled={reconcilingId === payment.payment_id}
                    >
                      {reconcilingId === payment.payment_id ? 'Reconciling...' : 'Reconcile Payment'}
                    </Button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
