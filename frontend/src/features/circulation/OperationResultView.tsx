import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { Loan } from '../../shared/api';
import { Button, StatusMessage } from '../../shared/components';

export interface OperationResultViewProps {
  loan: Loan;
  isReplayed?: boolean;
  onReset?: () => void;
}

/**
 * Operation Result View (FE-007).
 *
 * Renders distinct user language for request, approval, checkout, and return.
 * Strictly presents server-provided facts (e.g. server due date) without client-side calculation.
 */
export function OperationResultView({ loan, isReplayed = false, onReset }: OperationResultViewProps) {
  const tokens = useTokens();

  const outerRadius = 12;
  const padding = 24;
  const innerRadius = calcNestedRadius(outerRadius, padding);

  let title = 'Circulation Operation Completed';
  let statusVariant: 'success' | 'info' | 'warning' | 'danger' = 'success';
  let description = 'The loan lifecycle operation succeeded.';

  switch (loan.status) {
    case 'requested':
      title = 'Loan Request Created';
      statusVariant = 'info';
      description = 'Self-service request registered. Awaiting librarian review and approval.';
      break;
    case 'approved':
      title = 'Loan Approved';
      statusVariant = 'success';
      description = 'Librarian approval recorded. Physical copy is reserved and ready for patron checkout.';
      break;
    case 'checked_out':
      title = 'Loan Checked Out';
      statusVariant = 'success';
      description = 'Item checked out to borrower. Hand physical book to patron.';
      break;
    case 'returned':
      title = 'Book Returned Successfully';
      statusVariant = 'success';
      description = 'Physical item checked in. Copy status restored to available on shelf.';
      break;
    case 'rejected':
      title = 'Loan Rejected';
      statusVariant = 'warning';
      description = 'Loan request was declined by staff.';
      break;
    case 'overdue':
      title = 'Loan Overdue';
      statusVariant = 'danger';
      description = 'Loan has exceeded its scheduled due date.';
      break;
  }

  const formatTimestamp = (iso?: string | null) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toISOString().replace('T', ' ').substring(0, 19);
    } catch {
      return iso;
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.semantic.groupToGroup,
        backgroundColor: tokens.colors.surfaceAlt,
        borderRadius: tokens.radius.xl,
        border: `1px solid ${tokens.colors.border}`,
        padding: tokens.spacing.xl,
        boxSizing: 'border-box',
      }}
    >
      <StatusMessage status={statusVariant} title="Circulation Operation Succeeded">
        {description}
      </StatusMessage>

      {isReplayed && (
        <StatusMessage status="info" title="Idempotent Replay">
          This operation was previously executed. The original result was safely replayed without duplicate side effects.
        </StatusMessage>
      )}

      {/* Structured Details Card */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.md,
          backgroundColor: tokens.colors.surface,
          border: `1px solid ${tokens.colors.borderMuted}`,
          borderRadius: `${innerRadius}px`,
          padding: tokens.spacing.lg,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3
            style={{
              margin: 0,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            {title}
          </h3>
          <span
            data-testid="loan-status-badge"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '4px 10px',
              borderRadius: tokens.radius.full,
              fontSize: tokens.typography.fontSizes.xs,
              fontWeight: tokens.typography.fontWeights.semibold,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              backgroundColor:
                loan.status === 'checked_out' || loan.status === 'approved' || loan.status === 'returned'
                  ? tokens.colors.status.success.bg
                  : loan.status === 'requested'
                    ? tokens.colors.status.info.bg
                    : tokens.colors.status.warning.bg,
              color:
                loan.status === 'checked_out' || loan.status === 'approved' || loan.status === 'returned'
                  ? tokens.colors.status.success.color
                  : loan.status === 'requested'
                    ? tokens.colors.status.info.color
                    : tokens.colors.status.warning.color,
              border: `1px solid ${
                loan.status === 'checked_out' || loan.status === 'approved' || loan.status === 'returned'
                  ? tokens.colors.status.success.border
                  : loan.status === 'requested'
                    ? tokens.colors.status.info.border
                    : tokens.colors.status.warning.border
              }`,
            }}
          >
            {loan.status.replace('_', ' ')}
          </span>
        </div>

        <dl
          style={{
            margin: 0,
            display: 'grid',
            gridTemplateColumns: '160px 1fr',
            rowGap: tokens.spacing.sm,
            columnGap: tokens.spacing.md,
            fontSize: tokens.typography.fontSizes.sm,
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
            Loan ID:
          </dt>
          <dd
            style={{
              margin: 0,
              fontFamily: tokens.typography.monoFontFamily,
              color: tokens.colors.textPrimary,
              wordBreak: 'break-all',
            }}
          >
            {loan.loan_id}
          </dd>

          <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
            Copy ID:
          </dt>
          <dd
            style={{
              margin: 0,
              fontFamily: tokens.typography.monoFontFamily,
              color: tokens.colors.textPrimary,
              wordBreak: 'break-all',
            }}
          >
            {loan.copy_id}
          </dd>

          <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
            Borrower User ID:
          </dt>
          <dd
            style={{
              margin: 0,
              fontFamily: tokens.typography.monoFontFamily,
              color: tokens.colors.textPrimary,
              wordBreak: 'break-all',
            }}
          >
            {loan.borrower_user_id}
          </dd>

          <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
            Requested At:
          </dt>
          <dd style={{ margin: 0, color: tokens.colors.textPrimary }}>
            {formatTimestamp(loan.requested_at) || 'N/A'}
          </dd>

          {loan.approved_at && (
            <>
              <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
                Approved At:
              </dt>
              <dd style={{ margin: 0, color: tokens.colors.textPrimary }}>
                {formatTimestamp(loan.approved_at)}
              </dd>
            </>
          )}

          {loan.checked_out_at && (
            <>
              <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
                Checked Out At:
              </dt>
              <dd style={{ margin: 0, color: tokens.colors.textPrimary }}>
                {formatTimestamp(loan.checked_out_at)}
              </dd>
            </>
          )}

          {loan.due_at && (
            <>
              <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
                Due Date:
              </dt>
              <dd
                style={{
                  margin: 0,
                  color: tokens.colors.textPrimary,
                  fontWeight: tokens.typography.fontWeights.semibold,
                }}
              >
                {formatTimestamp(loan.due_at)}
              </dd>
            </>
          )}

          {loan.returned_at && (
            <>
              <dt style={{ color: tokens.colors.textSecondary, fontWeight: tokens.typography.fontWeights.medium }}>
                Returned At:
              </dt>
              <dd style={{ margin: 0, color: tokens.colors.textPrimary }}>
                {formatTimestamp(loan.returned_at)}
              </dd>
            </>
          )}
        </dl>
      </div>

      {onReset && (
        <div style={{ marginTop: tokens.spacing.sm }}>
          <Button variant="secondary" size="md" onClick={onReset}>
            Perform Another Operation
          </Button>
        </div>
      )}
    </div>
  );
}
