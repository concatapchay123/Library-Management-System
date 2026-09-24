import { useState, useContext, FormEvent } from 'react';
import { useTokens } from '../../shared/tokens';
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
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { DeskCheckoutFormValues, getNextSafeActionRecommendation, extractProblemDetails } from './types';

export interface DeskCheckoutPanelProps {
  onSuccess: (loan: Loan) => void;
  initialValues?: Partial<DeskCheckoutFormValues>;
}

/**
 * Direct Desk Checkout Panel (FE-007).
 *
 * Staff direct checkout flow that issues a loan with explicit approval action.
 * Strict invariants:
 * - Single-column layout with explicit labels and actionable placeholders.
 * - Exactly ONE primary CTA ("Direct Desk Checkout").
 * - Repeat click suppression and Idempotency-Key header inclusion.
 * - Form values are strictly preserved upon conflict or server validation error.
 * - Problem Details accompanied by safe next action guidance.
 */
export function DeskCheckoutPanel({ onSuccess, initialValues }: DeskCheckoutPanelProps) {
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

    if (!copyId.trim() || !borrowerUserId.trim()) {
      setError(new Error('Physical Copy ID and Borrower User ID are required.'));
      return;
    }

    setIsSubmitting(true);
    setError(null);

    const idempotencyKey = generateIdempotencyKey();
    const durationNum = durationDays.trim() ? parseInt(durationDays.trim(), 10) : undefined;

    try {
      const loan = await apiClient.loans.deskCheckout(
        {
          copy_id: copyId.trim(),
          borrower_user_id: borrowerUserId.trim(),
          duration_days: durationNum && !isNaN(durationNum) ? durationNum : undefined,
        },
        { token, idempotencyKey },
      );
      onSuccess(loan);
    } catch (err) {
      // INVARIANT: copyId, borrowerUserId, and durationDays remain preserved in state!
      setError(err as ProblemDetails | Error);
    } finally {
      setIsSubmitting(false);
    }
  };

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
          Direct Desk Checkout
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
          Staff circulation flow: directly check out an available physical copy to an eligible borrower.
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
          id="desk-checkout-copy-id"
          label="Physical Copy ID / Barcode UUID"
          description="Enter or scan the unique physical book copy identifier."
          placeholder="e.g. c1111111-1111-4111-8111-111111111111"
          value={copyId}
          onChange={(e) => setCopyId(e.target.value)}
          disabled={isSubmitting}
        />

        <Input
          id="desk-checkout-borrower-id"
          label="Borrower User ID"
          description="Enter borrower patron UUID or library card identifier."
          placeholder="e.g. u1111111-1111-4111-8111-111111111111"
          value={borrowerUserId}
          onChange={(e) => setBorrowerUserId(e.target.value)}
          disabled={isSubmitting}
        />

        <Input
          id="desk-checkout-duration"
          label="Custom Duration in Days"
          optional
          description="Optional custom loan duration. When omitted, default policy rules apply."
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
            {isSubmitting ? 'Processing Checkout...' : 'Direct Desk Checkout'}
          </Button>
        </div>
      </form>
    </div>
  );
}
