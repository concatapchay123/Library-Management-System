import { useTokens } from '../../shared/tokens';
import { CopyStatusHistoryRecord, ProblemDetails } from '../../shared/api';
import { LoadingSkeleton, EmptyState, ProblemDetailsRenderer } from '../../shared/components';

export interface StatusHistoryViewProps {
  history: CopyStatusHistoryRecord[];
  isLoading?: boolean;
  error?: ProblemDetails | Error | null;
  onRetry?: () => void;
}

/**
 * Visibly read-only status history view.
 *
 * Adheres strictly to evidence checkpoints and invariants:
 * - History is visibly read-only and immutable.
 * - Explicitly identifies actor, reason, and time for every transition.
 * - Pure append-only audit trail; no edit or delete controls are ever rendered.
 */
export function StatusHistoryView({
  history,
  isLoading = false,
  error = null,
  onRetry,
}: StatusHistoryViewProps) {
  const tokens = useTokens();

  if (isLoading) {
    return (
      <div
        data-testid="status-history-panel"
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          borderRadius: tokens.radius.xl,
          border: `1px solid ${tokens.colors.border}`,
          padding: tokens.spacing.xl,
        }}
      >
        <LoadingSkeleton lines={4} ariaLabel="Loading status history..." />
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="status-history-panel"
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          borderRadius: tokens.radius.xl,
          border: `1px solid ${tokens.colors.border}`,
          padding: tokens.spacing.xl,
        }}
      >
        <ProblemDetailsRenderer error={error} onRetry={onRetry} isSafeToRetry={true} />
      </div>
    );
  }

  return (
    <div
      data-testid="status-history-panel"
      style={{
        backgroundColor: tokens.colors.surfaceAlt,
        borderRadius: tokens.radius.xl,
        border: `1px solid ${tokens.colors.border}`,
        padding: tokens.spacing.xl,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.lg,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: tokens.spacing.md,
        }}
      >
        <div>
          <h3
            style={{
              margin: 0,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Status Transition History
          </h3>
          <p
            style={{
              margin: 0,
              marginTop: tokens.spacing.xs,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
            }}
          >
            Chronological audit log of physical copy lifecycle state changes.
          </p>
        </div>

        {/* Read-only audit cue */}
        <div
          role="status"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: tokens.spacing.xs,
            padding: `${tokens.spacing.xs} ${tokens.spacing.md}`,
            backgroundColor: tokens.colors.surfaceElevated,
            borderRadius: tokens.radius.full,
            border: `1px solid ${tokens.colors.border}`,
            fontSize: tokens.typography.fontSizes.xs,
            fontWeight: tokens.typography.fontWeights.semibold,
            color: tokens.colors.textSecondary,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: tokens.colors.primary,
            }}
          />
          <span>Immutable Audit Log: Read-Only Status History</span>
        </div>
      </div>

      {history.length === 0 ? (
        <EmptyState
          title="No Status History Recorded"
          description="This copy has remained in its initial status since registration without any manual transitions."
        />
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.md,
          }}
        >
          {history.map((record, index) => {
            const formattedDate = new Date(record.created_at).toLocaleString(undefined, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
              timeZoneName: 'short',
            });

            return (
              <div
                key={record.history_id || `history-item-${index}`}
                data-testid="history-record-item"
                style={{
                  backgroundColor: tokens.colors.surface,
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: tokens.radius.lg,
                  padding: tokens.spacing.md,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: tokens.spacing.sm,
                }}
              >
                {/* Header row: Status transition + Timestamp */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: tokens.spacing.sm,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: tokens.spacing.sm,
                      fontFamily: tokens.typography.fontFamily,
                      fontSize: tokens.typography.fontSizes.sm,
                      fontWeight: tokens.typography.fontWeights.semibold,
                    }}
                  >
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: tokens.radius.sm,
                        backgroundColor: tokens.colors.surfaceElevated,
                        border: `1px solid ${tokens.colors.border}`,
                        color: tokens.colors.textSecondary,
                        textTransform: 'capitalize',
                      }}
                    >
                      {record.from_status}
                    </span>
                    <span style={{ color: tokens.colors.textMuted }}>➔</span>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: tokens.radius.sm,
                        backgroundColor: tokens.colors.surfaceAlt,
                        border: `1px solid ${tokens.colors.primary}`,
                        color: tokens.colors.textPrimary,
                        fontWeight: tokens.typography.fontWeights.bold,
                        textTransform: 'capitalize',
                      }}
                    >
                      {record.to_status}
                    </span>
                  </div>

                  <time
                    dateTime={record.created_at}
                    style={{
                      fontFamily: tokens.typography.fontFamily,
                      fontSize: tokens.typography.fontSizes.xs,
                      color: tokens.colors.textMuted,
                    }}
                  >
                    {formattedDate}
                  </time>
                </div>

                {/* Reason description */}
                <div
                  style={{
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.sm,
                    color: tokens.colors.textPrimary,
                    lineHeight: tokens.typography.lineHeights.normal,
                    backgroundColor: tokens.colors.surfaceAlt,
                    padding: tokens.spacing.sm,
                    borderRadius: tokens.radius.sm,
                    borderLeft: `3px solid ${tokens.colors.borderFocus}`,
                  }}
                >
                  <span
                    style={{
                      display: 'block',
                      fontSize: tokens.typography.fontSizes.xs,
                      fontWeight: tokens.typography.fontWeights.semibold,
                      color: tokens.colors.textMuted,
                      textTransform: 'uppercase',
                      marginBottom: '2px',
                    }}
                  >
                    Librarian Reason:
                  </span>
                  <span>{record.reason}</span>
                </div>

                {/* Actor ID metadata */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: tokens.spacing.xs,
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.xs,
                    color: tokens.colors.textSecondary,
                  }}
                >
                  <span style={{ fontWeight: tokens.typography.fontWeights.medium }}>
                    Recorded By Actor:
                  </span>
                  <code
                    style={{
                      fontFamily: 'monospace',
                      fontSize: tokens.typography.fontSizes.xs,
                      backgroundColor: tokens.colors.surfaceElevated,
                      padding: '2px 6px',
                      borderRadius: tokens.radius.sm,
                      color: tokens.colors.textPrimary,
                    }}
                  >
                    {record.actor_id}
                  </code>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default StatusHistoryView;
