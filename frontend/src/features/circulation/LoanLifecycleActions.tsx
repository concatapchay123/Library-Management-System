import { useState, useContext, useRef } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import {
  Loan,
  ProblemDetails,
  apiClient,
  generateIdempotencyKey,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import {
  Button,
  Input,
  Dialog,
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { getNextSafeActionRecommendation, extractProblemDetails } from './types';

export interface LoanLifecycleActionsProps {
  loan: Loan;
  onLoanUpdated: (loan: Loan) => void;
}

/**
 * Loan Lifecycle Actions Panel (FE-007).
 *
 * Enforces strict core circulation invariants:
 * - Presents the current loan state and ONLY the next server-permitted action.
 * - Exactly ONE lifecycle action is visually primary at a time.
 * - User language clearly distinguishes request, approval, checkout, and return.
 * - The UI does not calculate eligibility, due date, or copy locking.
 * - Idempotency keys are safely generated and attached to checkout and return mutations.
 * - Errors (such as 409 Conflict) preserve the displayed loan state and explain the next safe action.
 */
export function LoanLifecycleActions({ loan, onLoanUpdated }: LoanLifecycleActionsProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ProblemDetails | Error | null>(null);

  // Dialog state for rejection
  const [isRejectDialogOpen, setIsRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const rejectTriggerRef = useRef<HTMLButtonElement>(null);

  const outerRadius = 12;
  const padding = 24;
  const innerRadius = calcNestedRadius(outerRadius, padding);

  const formatTimestamp = (iso?: string | null) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toISOString().replace('T', ' ').substring(0, 19);
    } catch {
      return iso;
    }
  };

  // Handler: Approve Loan
  const handleApprove = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await apiClient.loans.approve(loan.loan_id, { token });
      onLoanUpdated(updated);
    } catch (err) {
      setError(err as ProblemDetails | Error);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handler: Reject Loan
  const handleConfirmReject = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await apiClient.loans.reject(
        loan.loan_id,
        { reason: rejectReason.trim() || undefined },
        { token },
      );
      setIsRejectDialogOpen(false);
      setRejectReason('');
      onLoanUpdated(updated);
    } catch (err) {
      setError(err as ProblemDetails | Error);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handler: Complete Checkout
  const handleCheckout = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    const idempotencyKey = generateIdempotencyKey();
    try {
      const updated = await apiClient.loans.checkout(
        loan.loan_id,
        undefined,
        { token, idempotencyKey },
      );
      onLoanUpdated(updated);
    } catch (err) {
      setError(err as ProblemDetails | Error);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handler: Process Return
  const handleReturn = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    const idempotencyKey = generateIdempotencyKey();
    try {
      const updated = await apiClient.loans.return(
        loan.loan_id,
        { token, idempotencyKey },
      );
      onLoanUpdated(updated);
    } catch (err) {
      setError(err as ProblemDetails | Error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isTerminal =
    loan.status === 'returned' || loan.status === 'rejected' || loan.status === 'cancelled';

  const { type: problemType, detail: problemDetail } = extractProblemDetails(error);
  const safeActionExplanation = getNextSafeActionRecommendation(
    problemType,
    problemDetail,
  );

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
      <div>
        <h3
          style={{
            margin: 0,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.xl,
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
          }}
        >
          Active Loan Lifecycle Management
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
          Inspect current loan state and execute the next authorized lifecycle transition.
        </p>
      </div>

      {/* Loan Metadata Card: State is strictly preserved on error */}
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
          <span
            style={{
              fontSize: tokens.typography.fontSizes.sm,
              fontWeight: tokens.typography.fontWeights.semibold,
              color: tokens.colors.textSecondary,
            }}
          >
            Loan Details
          </span>
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

      {/* Error state with safe resolution advice */}
      {error && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
          <ProblemDetailsRenderer error={error} />
          <StatusMessage status="warning" title="Next safe action:">
            {safeActionExplanation}
          </StatusMessage>
        </div>
      )}

      {/* Permitted Action Buttons: Exactly ONE primary button at a time */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: tokens.spacing.md,
          marginTop: tokens.spacing.sm,
          paddingTop: tokens.spacing.md,
          borderTop: `1px solid ${tokens.colors.borderMuted}`,
          flexWrap: 'wrap',
        }}
      >
        {loan.status === 'requested' && (
          <>
            {/* Exactly ONE primary action */}
            <Button
              variant="primary"
              size="md"
              disabled={isSubmitting}
              onClick={handleApprove}
            >
              {isSubmitting ? 'Approving Loan...' : 'Approve Loan'}
            </Button>

            {/* Secondary action */}
            <Button
              ref={rejectTriggerRef}
              variant="secondary"
              size="md"
              disabled={isSubmitting}
              onClick={() => setIsRejectDialogOpen(true)}
            >
              Reject Loan
            </Button>
          </>
        )}

        {loan.status === 'approved' && (
          <Button
            variant="primary"
            size="md"
            disabled={isSubmitting}
            onClick={handleCheckout}
          >
            {isSubmitting ? 'Checking Out...' : 'Complete Checkout'}
          </Button>
        )}

        {(loan.status === 'checked_out' || loan.status === 'overdue') && (
          <Button
            variant="primary"
            size="md"
            disabled={isSubmitting}
            onClick={handleReturn}
          >
            {isSubmitting ? 'Processing Return...' : 'Process Return'}
          </Button>
        )}

        {isTerminal && (
          <StatusMessage status="info" title="Terminal Loan State">
            This loan has reached its final state and cannot undergo further lifecycle mutations.
          </StatusMessage>
        )}
      </div>

      {/* Rejection Reason Dialog */}
      <Dialog
        isOpen={isRejectDialogOpen}
        onClose={() => setIsRejectDialogOpen(false)}
        title="Reject Loan Request"
        description="Provide a justification reason for declining the patron's loan request."
        triggerRef={rejectTriggerRef}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.semantic.groupToGroup,
          }}
        >
          <Input
            id="rejection-reason"
            label="Rejection Reason"
            description="Optional explanation recorded in the audit event log."
            placeholder="e.g. Patron has overdue loans or copy reserved for course..."
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
          />

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: tokens.spacing.md,
              marginTop: tokens.spacing.sm,
            }}
          >
            <Button
              variant="secondary"
              size="sm"
              disabled={isSubmitting}
              onClick={() => setIsRejectDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              disabled={isSubmitting}
              onClick={handleConfirmReject}
            >
              {isSubmitting ? 'Rejecting...' : 'Confirm Rejection'}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
