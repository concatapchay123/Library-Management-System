import { useState, useContext, FormEvent } from 'react';
import { useTokens } from '../../shared/tokens';
import {
  Loan,
  ProblemDetails,
  apiClient,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import {
  Button,
  Input,
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { LoanRequestFormValues, getNextSafeActionRecommendation } from './types';

export interface LoanRequestPanelProps {
  onSuccess: (loan: Loan) => void;
  initialValues?: Partial<LoanRequestFormValues>;
}

/**
 * Self-Service and Staff Loan Request Panel (FE-007).
 *
 * Invariants:
 * - Single-column layout with explicit labels and helper text.
 * - Exactly ONE primary CTA ("Submit Loan Request").
 * - Form state preserved on error.
 * - Explains safe resolution advice when conflict or validation error occurs.
 */
export function LoanRequestPanel({ onSuccess, initialValues }: LoanRequestPanelProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [copyId, setCopyId] = useState(initialValues?.copy_id || '');
  const [borrowerUserId, setBorrowerUserId] = useState(initialValues?.borrower_user_id || '');
  const [durationDays, setDurationDays] = useState(
    initialValues?.duration_days ? String(initialValues.duration_days) : '',
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ProblemDetails | Error | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    if (!copyId.trim()) {
      setError(new Error('Physical Copy ID is required to request a loan.'));
      return;
    }

    setIsSubmitting(true);
    setError(null);

    const durationNum = durationDays.trim() ? parseInt(durationDays.trim(), 10) : undefined;

    try {
      const loan = await apiClient.loans.request(
        {
          copy_id: copyId.trim(),
          borrower_user_id: borrowerUserId.trim() || undefined,
          duration_days: durationNum && !isNaN(durationNum) ? durationNum : undefined,
        },
        { token },
      );
      onSuccess(loan);
    } catch (err) {
      setError(err as ProblemDetails | Error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const problemDetailsObj =
    error && typeof error === 'object' && 'type' in error ? (error as ProblemDetails) : null;
  const safeActionExplanation = getNextSafeActionRecommendation(
    problemDetailsObj?.type,
    problemDetailsObj?.detail,
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
          Submit Loan Request
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
          Initiate a loan request for an available physical copy. Staff approval is required before checkout.
        </p>
      </div>

      {error && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
          <ProblemDetailsRenderer error={error} />
          <StatusMessage status="warning" title="Next safe action:">
            {safeActionExplanation}
          </StatusMessage>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.semantic.groupToGroup,
        }}
      >
        <Input
          id="request-copy-id"
          label="Physical Copy ID / Barcode UUID"
          description="Enter or scan the physical book copy identifier."
          placeholder="e.g. c1111111-1111-4111-8111-111111111111"
          value={copyId}
          onChange={(e) => setCopyId(e.target.value)}
          disabled={isSubmitting}
        />

        <Input
          id="request-borrower-id"
          label="Borrower User ID"
          optional
          description="Borrower user UUID. When omitted, the authenticated user is recorded as borrower."
          placeholder="e.g. u1111111-1111-4111-8111-111111111111"
          value={borrowerUserId}
          onChange={(e) => setBorrowerUserId(e.target.value)}
          disabled={isSubmitting}
        />

        <Input
          id="request-duration"
          label="Custom Duration in Days"
          optional
          description="Requested duration. Server organization policies govern final approved loan terms."
          placeholder="e.g. 14"
          value={durationDays}
          onChange={(e) => setDurationDays(e.target.value)}
          disabled={isSubmitting}
        />

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: tokens.spacing.md,
            marginTop: tokens.spacing.sm,
            paddingTop: tokens.spacing.md,
            borderTop: `1px solid ${tokens.colors.borderMuted}`,
          }}
        >
          {/* Exactly ONE visually primary action */}
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Submitting Request...' : 'Submit Loan Request'}
          </Button>
        </div>
      </form>
    </div>
  );
}
