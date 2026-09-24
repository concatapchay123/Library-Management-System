import React, { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { Button, ProblemDetailsRenderer } from '../../shared/components';
import { ProblemDetails } from '../../shared/api';
import { NotificationCardProps } from './types';

/**
 * Renders an in-app notification item with read-state workflow (FE-008).
 *
 * Adheres strictly to architectural & UI invariants:
 * - Unread/read distinction with prominent visual cue and text badge.
 * - Marking a notification read updates ONLY after a successful server response.
 * - Read-state control is keyboard accessible and WCAG AA contrast compliant.
 * - Dominant action: Open Relevant Record (does not treat notification as authorization truth).
 * - Inline error handling if read-state mutation fails on server.
 */
export function NotificationCard({
  notification,
  onMarkRead,
  onOpenRecord,
  isMarkingRead = false,
}: NotificationCardProps) {
  const tokens = useTokens();
  const [internalMarkingRead, setInternalMarkingRead] = useState(false);
  const [markReadError, setMarkReadError] = useState<ProblemDetails | Error | null>(null);

  const isUnread = notification.status === 'unread';

  const handleMarkReadClick = async () => {
    if (!onMarkRead || internalMarkingRead || isMarkingRead) return;
    setInternalMarkingRead(true);
    setMarkReadError(null);
    try {
      await onMarkRead(notification.notification_id);
    } catch (err) {
      setMarkReadError(err as ProblemDetails | Error);
    } finally {
      setInternalMarkingRead(false);
    }
  };

  const handleKeyDownMarkRead = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleMarkReadClick();
    }
  };

  const handleOpenRecordClick = () => {
    if (!onOpenRecord) return;
    const payload = notification.payload || {};
    if (payload.reservation_id) {
      onOpenRecord('reservation', String(payload.reservation_id));
    } else if (payload.loan_id) {
      onOpenRecord('loan', String(payload.loan_id));
    } else if (payload.book_id) {
      onOpenRecord('book', String(payload.book_id));
    } else {
      onOpenRecord('notification', notification.notification_id);
    }
  };

  // Safe extraction of message and title from sanitized payload
  const payload = notification.payload || {};
  const message =
    typeof payload.message === 'string'
      ? payload.message
      : `Notification event: ${notification.type}`;
  const bookTitle = typeof payload.book_title === 'string' ? payload.book_title : null;
  const holdExpiresAt = typeof payload.hold_expires_at === 'string' ? payload.hold_expires_at : null;
  const dueAt = typeof payload.due_at === 'string' ? payload.due_at : null;

  return (
    <article
      data-testid={`notification-item-${notification.notification_id}`}
      style={{
        backgroundColor: isUnread ? tokens.colors.surface : tokens.colors.surfaceAlt,
        border: `1px solid ${isUnread ? tokens.colors.borderFocus : tokens.colors.border}`,
        borderRadius: tokens.radius.md,
        padding: tokens.spacing.md,
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.sm,
        boxShadow: isUnread ? '0 1px 2px rgba(0, 0, 0, 0.05)' : 'none',
        position: 'relative',
      }}
    >
      {/* Header with Type, Timestamp, and Read Status Badge */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: tokens.spacing.xs,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.xs }}>
          {isUnread && (
            <span
              aria-hidden="true"
              style={{
                width: '8px',
                height: '8px',
                borderRadius: tokens.radius.full,
                backgroundColor: tokens.colors.primary,
                display: 'inline-block',
              }}
            />
          )}
          <span
            style={{
              fontSize: tokens.typography.fontSizes.xs,
              fontFamily: tokens.typography.monoFontFamily,
              color: tokens.colors.textMuted,
              textTransform: 'uppercase',
            }}
          >
            {notification.type}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.xs }}>
          <time
            dateTime={notification.created_at}
            style={{
              fontSize: tokens.typography.fontSizes.xs,
              color: tokens.colors.textMuted,
              fontFamily: tokens.typography.monoFontFamily,
            }}
          >
            {notification.created_at}
          </time>

          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '2px 8px',
              borderRadius: tokens.radius.full,
              backgroundColor: isUnread
                ? tokens.colors.status.warning.bg
                : tokens.colors.surfaceAlt,
              color: isUnread
                ? tokens.colors.status.warning.color
                : tokens.colors.textMuted,
              border: `1px solid ${isUnread ? tokens.colors.status.warning.border : tokens.colors.border}`,
              fontSize: tokens.typography.fontSizes.xs,
              fontWeight: tokens.typography.fontWeights.semibold,
            }}
          >
            {isUnread ? 'Unread' : 'Read'}
          </span>
        </div>
      </div>

      {/* Book Title context when present */}
      {bookTitle && (
        <h4
          style={{
            margin: 0,
            fontSize: tokens.typography.fontSizes.sm,
            fontWeight: tokens.typography.fontWeights.semibold,
            color: tokens.colors.textPrimary,
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          {bookTitle}
        </h4>
      )}

      {/* Main message */}
      <p
        style={{
          margin: 0,
          fontSize: tokens.typography.fontSizes.sm,
          color: tokens.colors.textPrimary,
          lineHeight: tokens.typography.lineHeights.normal,
        }}
      >
        {message}
      </p>

      {/* Contextual time-sensitive facts from server */}
      {(holdExpiresAt || dueAt) && (
        <div
          style={{
            fontSize: tokens.typography.fontSizes.xs,
            color: tokens.colors.textSecondary,
            fontFamily: tokens.typography.monoFontFamily,
            backgroundColor: tokens.colors.surface,
            padding: tokens.spacing.xs,
            borderRadius: tokens.radius.sm,
            border: `1px solid ${tokens.colors.border}`,
          }}
        >
          {holdExpiresAt && <span>Hold Expiration: {holdExpiresAt}</span>}
          {dueAt && <span>Loan Due Date: {dueAt}</span>}
        </div>
      )}

      {/* Inline error if mark-as-read mutation failed on server */}
      {markReadError && (
        <ProblemDetailsRenderer
          error={markReadError}
          isSafeToRetry={true}
          onRetry={handleMarkReadClick}
        />
      )}

      {/* Actions: Exactly 1 dominant action (Open Record) + Mark as Read */}
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
          data-testid={`open-record-notif-${notification.notification_id}`}
          variant="primary"
          onClick={handleOpenRecordClick}
        >
          Open Relevant Record
        </Button>

        {isUnread && onMarkRead && (
          <Button
            variant="outline"
            onClick={handleMarkReadClick}
            onKeyDown={handleKeyDownMarkRead}
            disabled={internalMarkingRead || isMarkingRead}
            aria-label="Mark as Read"
          >
            {internalMarkingRead || isMarkingRead ? 'Saving...' : 'Mark as Read'}
          </Button>
        )}
      </div>
    </article>
  );
}
