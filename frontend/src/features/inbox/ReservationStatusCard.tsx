import { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { Button } from '../../shared/components';
import { ReservationStatusCardProps } from './types';

/**
 * Renders an individual reservation progression card (FE-008).
 *
 * Adheres strictly to architectural & UI invariants:
 * - Does not promise a pickup or allocation date beyond server facts.
 * - Queue position and hold expiration are rendered verbatim from backend data.
 * - Exactly one dominant action: Open Relevant Record.
 * - Destructive action (Cancel Reservation) uses danger color psychology.
 * - Nested border radius and WCAG AA contrast compliance.
 */
export function ReservationStatusCard({
  reservation,
  onCancel,
  onOpenRecord,
  isCancelling = false,
}: ReservationStatusCardProps) {
  const tokens = useTokens();
  const [internalCancelling, setInternalCancelling] = useState(false);

  const isPending = reservation.status === 'pending';
  const isHeld = reservation.status === 'held';
  const isFulfilled = reservation.status === 'fulfilled';
  const isCancelled = reservation.status === 'cancelled';
  const isExpired = reservation.status === 'expired';

  const handleCancelClick = async () => {
    if (!onCancel || internalCancelling || isCancelling) return;
    setInternalCancelling(true);
    try {
      await onCancel(reservation.reservation_id);
    } finally {
      setInternalCancelling(false);
    }
  };

  const handleOpenRecordClick = () => {
    if (onOpenRecord) {
      onOpenRecord('book', reservation.book_id);
    } else if (typeof window !== 'undefined') {
      window.location.hash = '#/catalog';
    }
  };

  // Status badge styling and label
  let statusBadgeBg = tokens.colors.surfaceAlt;
  let statusBadgeColor = tokens.colors.textSecondary;
  let statusLabel = 'Reservation Active';
  let statusDescription = 'Waiting for copy allocation';

  if (isPending) {
    statusBadgeBg = tokens.colors.status.warning.bg;
    statusBadgeColor = tokens.colors.status.warning.color;
    statusLabel = `Queue Position #${reservation.queue_position}`;
    statusDescription = 'In Queue — Waiting for Copy Allocation';
  } else if (isHeld) {
    statusBadgeBg = tokens.colors.status.success.bg;
    statusBadgeColor = tokens.colors.status.success.color;
    statusLabel = 'Ready for Pickup (Held)';
    statusDescription = 'A physical copy has been allocated and held for you at the library desk.';
  } else if (isFulfilled) {
    statusBadgeBg = tokens.colors.surfaceAlt;
    statusBadgeColor = tokens.colors.textSecondary;
    statusLabel = 'Fulfilled / Checked Out';
    statusDescription = 'This reservation has been fulfilled into an active loan.';
  } else if (isCancelled) {
    statusBadgeBg = tokens.colors.surfaceAlt;
    statusBadgeColor = tokens.colors.textMuted;
    statusLabel = 'Reservation Cancelled';
    statusDescription = 'This hold reservation was cancelled and will not be allocated.';
  } else if (isExpired) {
    statusBadgeBg = tokens.colors.status.danger.bg;
    statusBadgeColor = tokens.colors.status.danger.color;
    statusLabel = 'Hold Expired';
    statusDescription = 'The pickup window for this held copy expired before checkout.';
  }

  return (
    <article
      data-testid={`reservation-item-${reservation.reservation_id}`}
      style={{
        backgroundColor: tokens.colors.surface,
        border: `1px solid ${isHeld ? tokens.colors.status.success.border : tokens.colors.border}`,
        borderRadius: tokens.radius.md,
        padding: tokens.spacing.md,
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.sm,
        boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
      }}
    >
      {/* Header with Title and Server Status Badge */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: tokens.spacing.xs,
        }}
      >
        <div>
          <span
            style={{
              fontSize: tokens.typography.fontSizes.xs,
              color: tokens.colors.textMuted,
              fontFamily: tokens.typography.monoFontFamily,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
            }}
          >
            Reservation #{reservation.reservation_id.slice(0, 8)}
          </span>
          <h3
            style={{
              margin: '4px 0 0 0',
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.md,
              fontWeight: tokens.typography.fontWeights.semibold,
              color: tokens.colors.textPrimary,
            }}
          >
            Book Reference: {reservation.book_id}
          </h3>
        </div>

        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '4px 10px',
            borderRadius: tokens.radius.full,
            backgroundColor: statusBadgeBg,
            color: statusBadgeColor,
            fontSize: tokens.typography.fontSizes.xs,
            fontWeight: tokens.typography.fontWeights.semibold,
          }}
        >
          {statusLabel}
        </span>
      </div>

      {/* Progression details strictly reflecting server facts */}
      <p
        style={{
          margin: 0,
          fontSize: tokens.typography.fontSizes.sm,
          color: tokens.colors.textSecondary,
          lineHeight: tokens.typography.lineHeights.normal,
        }}
      >
        {statusDescription}
      </p>

      {/* Server-provided timestamps and details */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          padding: tokens.spacing.xs,
          backgroundColor: tokens.colors.surfaceAlt,
          borderRadius: tokens.radius.sm,
          fontSize: tokens.typography.fontSizes.xs,
          color: tokens.colors.textSecondary,
          fontFamily: tokens.typography.monoFontFamily,
        }}
      >
        <div>
          <span>Requested At: {reservation.created_at}</span>
        </div>

        {reservation.copy_id && (
          <div>
            <span>Copy ID: {reservation.copy_id}</span>
          </div>
        )}

        {isHeld && reservation.hold_expires_at && (
          <div style={{ color: tokens.colors.status.warning.color, fontWeight: tokens.typography.fontWeights.semibold }}>
            <span>Hold Expires: {reservation.hold_expires_at}</span>
          </div>
        )}

        {isCancelled && reservation.cancelled_at && (
          <div>
            <span>Cancelled At: {reservation.cancelled_at}</span>
          </div>
        )}
      </div>

      {/* Action area: exactly 1 dominant action (Open Record) and optional secondary/destructive action */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: tokens.spacing.xs,
          gap: tokens.spacing.sm,
          flexWrap: 'wrap',
        }}
      >
        <Button
          data-testid={`open-record-res-${reservation.reservation_id}`}
          variant="primary"
          onClick={handleOpenRecordClick}
        >
          Open Relevant Record
        </Button>

        {(isPending || isHeld) && onCancel && (
          <Button
            variant="danger"
            onClick={handleCancelClick}
            disabled={internalCancelling || isCancelling}
          >
            {internalCancelling || isCancelling ? 'Cancelling...' : 'Cancel Reservation'}
          </Button>
        )}
      </div>
    </article>
  );
}
