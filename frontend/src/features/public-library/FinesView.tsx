import React, { useState, useMemo, useEffect } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { Button, Input, Dialog, LoadingSkeleton } from '../../shared/components';
import { FinesViewProps } from './types';
import { PublicLibraryFine, apiClient } from '../../shared/api';

export function FinesView({
  fines,
  isLoading,
  onRefresh,
  onError,
}: FinesViewProps) {
  const tokens = useTokens();
  const [searchQuery, setSearchQuery] = useState('');
  const [waiveTargetFine, setWaiveTargetFine] = useState<PublicLibraryFine | null>(null);
  const [waiveReason, setWaiveReason] = useState('');
  const [isSubmittingWaive, setIsSubmittingWaive] = useState(false);
  const [localFines, setLocalFines] = useState<PublicLibraryFine[]>(fines);

  useEffect(() => {
    setLocalFines(fines);
  }, [fines]);

  const filteredFines = useMemo(() => {
    if (!searchQuery.trim()) return localFines;
    const q = searchQuery.toLowerCase().trim();
    return localFines.filter((f) =>
      f.reason.toLowerCase().includes(q) ||
      f.member_id.toLowerCase().includes(q) ||
      f.status.toLowerCase().includes(q) ||
      (f.loan_id && f.loan_id.toLowerCase().includes(q))
    );
  }, [localFines, searchQuery]);

  async function handleConfirmWaive(e: React.FormEvent) {
    e.preventDefault();
    if (!waiveTargetFine) return;
    if (!waiveReason.trim()) return;

    setIsSubmittingWaive(true);
    try {
      const updated = await apiClient.publicLibrary.fines.waive(waiveTargetFine.fine_id, {
        reason: waiveReason.trim(),
      });
      setLocalFines((prev) =>
        prev.map((f) => (f.fine_id === updated.fine_id ? updated : f))
      );
      setWaiveTargetFine(null);
      setWaiveReason('');
      onRefresh();
    } catch (err) {
      setWaiveTargetFine(null);
      setWaiveReason('');
      onError(err);
    } finally {
      setIsSubmittingWaive(false);
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
            id="fine-search"
            label="Filter Fines"
            placeholder="Filter fines by reason, member ID, or status..."
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

      {/* Fines List */}
      {isLoading ? (
        <LoadingSkeleton lines={3} />
      ) : filteredFines.length === 0 ? (
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
          No library fine records found.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}>
          {filteredFines.map((fine) => {
            const canWaive = fine.status === 'assessed' || fine.status === 'invoiced' || fine.status === 'partially_paid';

            return (
              <article
                key={fine.fine_id}
                style={{
                  backgroundColor: tokens.colors.surface,
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: `${outerRadius}px`,
                  padding: `${paddingVal}px`,
                  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.04)',
                }}
              >
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
                      {fine.currency} {fine.amount}
                    </span>
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        fontFamily: tokens.typography.monoFontFamily,
                        color: tokens.colors.textMuted,
                      }}
                    >
                      Member ID: {fine.member_id}
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
                      backgroundColor:
                        fine.status === 'paid'
                          ? tokens.colors.status.success.bg
                          : fine.status === 'waived'
                          ? tokens.colors.surfaceElevated
                          : fine.status === 'assessed'
                          ? tokens.colors.status.warning.bg
                          : tokens.colors.status.info.bg,
                      color:
                        fine.status === 'paid'
                          ? tokens.colors.status.success.color
                          : fine.status === 'waived'
                          ? tokens.colors.textSecondary
                          : fine.status === 'assessed'
                          ? tokens.colors.status.warning.color
                          : tokens.colors.status.info.color,
                      border: `1px solid ${
                        fine.status === 'paid'
                          ? tokens.colors.status.success.border
                          : fine.status === 'waived'
                          ? tokens.colors.border
                          : fine.status === 'assessed'
                          ? tokens.colors.status.warning.border
                          : tokens.colors.status.info.border
                      }`,
                    }}
                  >
                    {fine.status === 'assessed' && '● Assessed'}
                    {fine.status === 'waived' && '— Waived'}
                    {fine.status === 'paid' && '✓ Paid'}
                    {fine.status === 'partially_paid' && '◒ Partially Paid'}
                    {fine.status === 'invoiced' && '📄 Invoiced'}
                    {fine.status === 'cancelled' && '✕ Cancelled'}
                  </span>
                </div>

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
                  <p
                    style={{
                      margin: 0,
                      fontSize: tokens.typography.fontSizes.sm,
                      color: tokens.colors.textPrimary,
                    }}
                  >
                    <strong>Reason:</strong> {fine.reason}
                  </p>

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
                    <span>Assessed: {new Date(fine.assessed_at).toLocaleString()}</span>
                    {fine.loan_id && <span>Loan ID: {fine.loan_id}</span>}
                    <span>Fine ID: {fine.fine_id}</span>
                  </div>
                </div>

                {canWaive && (
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
                      onClick={() => {
                        setWaiveTargetFine(fine);
                        setWaiveReason('');
                      }}
                    >
                      Waive Fine
                    </Button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      {/* Waive Fine Dialog */}
      <Dialog
        isOpen={Boolean(waiveTargetFine)}
        onClose={() => {
          if (!isSubmittingWaive) {
            setWaiveTargetFine(null);
            setWaiveReason('');
          }
        }}
        title="Waive Fine"
      >
        {waiveTargetFine && (
          <form
            onSubmit={handleConfirmWaive}
            style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}
          >
            <p
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.sm,
                color: tokens.colors.textSecondary,
              }}
            >
              Waiving fine of{' '}
              <strong>
                {waiveTargetFine.currency} {waiveTargetFine.amount}
              </strong>{' '}
              assessed for &ldquo;{waiveTargetFine.reason}&rdquo;.
            </p>

            <Input
              id="waive-reason"
              label="Reason for waiver"
              placeholder="e.g. Patron medical emergency, forgiven by administrator..."
              value={waiveReason}
              onChange={(e) => setWaiveReason(e.target.value)}
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
                onClick={() => setWaiveTargetFine(null)}
                disabled={isSubmittingWaive}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={isSubmittingWaive || !waiveReason.trim()}
              >
                {isSubmittingWaive ? 'Waiving...' : 'Confirm Waiver'}
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  );
}
