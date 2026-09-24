import React, { useState, useEffect } from 'react';
import { useTokens } from '../../shared/tokens';
import { Button, Input, Select, ProblemDetailsRenderer, StatusMessage } from '../../shared/components';
import { BookCopy, CopyStatus, CopyStatusTransition, ProblemDetails, ALLOWED_STATUS_TRANSITIONS } from '../../shared/api';
import { CopyStatusValidationErrors } from './types';

export interface CopyStatusControlsProps {
  copy: BookCopy;
  onStatusChanged?: (updatedCopy: BookCopy) => void;
  onSubmitTransition: (copyId: string, transition: CopyStatusTransition) => Promise<BookCopy>;
  isSubmitting?: boolean;
}

/**
 * Permitted copy status transition controller.
 *
 * Adheres strictly to task acceptance criteria:
 * - The UI shows ONLY status actions returned or permitted by the backend domain rules.
 * - Single-column form with explicit labels and help text.
 * - Mandatory transition reason attribution (1-500 chars).
 * - Exactly ONE primary action per panel ("Change Status").
 * - Invalid server transition displays stable RFC Problem Details without modifying local history.
 */
export function CopyStatusControls({
  copy,
  onStatusChanged,
  onSubmitTransition,
  isSubmitting = false,
}: CopyStatusControlsProps) {
  const tokens = useTokens();

  const [toStatus, setToStatus] = useState<string>('');
  const [reason, setReason] = useState<string>('');
  const [errors, setErrors] = useState<CopyStatusValidationErrors>({});
  const [serverError, setServerError] = useState<ProblemDetails | Error | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Compute allowed transitions strictly based on backend domain policy (BE-014)
  const allowedTransitions: readonly CopyStatus[] =
    ALLOWED_STATUS_TRANSITIONS[copy.status] || [];

  useEffect(() => {
    setToStatus('');
    setReason('');
    setErrors({});
    setServerError(null);
    setSuccessMessage(null);
  }, [copy.copy_id, copy.status]);

  function validate(): boolean {
    const newErrors: CopyStatusValidationErrors = {};

    if (!toStatus) {
      newErrors.to_status = 'Please select a permitted target status';
    }

    const cleanReason = reason.trim();
    if (!cleanReason) {
      newErrors.reason = 'Reason is required (1-500 characters)';
    } else if (cleanReason.length > 500) {
      newErrors.reason = 'Reason cannot exceed 500 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMessage(null);
    setServerError(null);

    const isValid = validate();
    if (!isValid) {
      return;
    }

    try {
      const updated = await onSubmitTransition(copy.copy_id, {
        to_status: toStatus as CopyStatus,
        reason: reason.trim(),
      });

      setSuccessMessage(
        `Status transitioned from '${copy.status}' to '${updated.status}' successfully.`,
      );
      setToStatus('');
      setReason('');
      setErrors({});
      onStatusChanged?.(updated);
    } catch (err) {
      // Surfacing Problem Details error without altering local state/history
      setServerError(err as ProblemDetails | Error);
    }
  };

  const statusOptions = [
    { value: '', label: '-- Select permitted target status --' },
    ...allowedTransitions.map((status) => ({
      value: status,
      label: status.charAt(0).toUpperCase() + status.slice(1),
    })),
  ];

  let statusTextColor = tokens.colors.status.warning.color;
  if (copy.status === 'available') {
    statusTextColor = tokens.colors.status.success.color;
  } else if (copy.status === 'borrowed') {
    statusTextColor = tokens.colors.primary;
  }

  return (
    <div
      data-testid="copy-status-panel"
      style={{
        backgroundColor: tokens.colors.surfaceAlt,
        borderRadius: tokens.radius.xl,
        border: `1px solid ${tokens.colors.border}`,
        padding: tokens.spacing.xl,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.semantic.groupToGroup,
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
          Manage Copy Status
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
          Execute atomic lifecycle status changes with required librarian reason attribution.
        </p>
      </div>

      {/* Current Status Badge Indicator */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: tokens.spacing.sm,
          padding: `${tokens.spacing.xs} ${tokens.spacing.md}`,
          backgroundColor: tokens.colors.surface,
          borderRadius: tokens.radius.md,
          border: `1px solid ${tokens.colors.borderMuted}`,
          width: 'fit-content',
        }}
      >
        <span
          style={{
            fontSize: tokens.typography.fontSizes.xs,
            color: tokens.colors.textMuted,
            fontWeight: tokens.typography.fontWeights.semibold,
            textTransform: 'uppercase',
          }}
        >
          Current Copy Status:
        </span>
        <span
          style={{
            fontSize: tokens.typography.fontSizes.sm,
            fontWeight: tokens.typography.fontWeights.bold,
            color: statusTextColor,
            textTransform: 'capitalize',
          }}
        >
          {copy.status}
        </span>
      </div>

      {successMessage && (
        <StatusMessage status="success" title="Status Updated">
          {successMessage}
        </StatusMessage>
      )}

      {serverError && (
        <ProblemDetailsRenderer
          error={serverError}
          isSafeToRetry={false}
          style={{ marginBottom: tokens.spacing.sm }}
        />
      )}

      {allowedTransitions.length === 0 ? (
        <p
          style={{
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textMuted,
          }}
        >
          No transitions permitted from current status.
        </p>
      ) : (
        <form
          onSubmit={handleSubmit}
          noValidate
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.semantic.groupToGroup,
          }}
        >
          {/* Field 1: Target Status (Strictly server-permitted options only) */}
          <Select
            id="copy-target-status"
            label="Target Status"
            description="Permitted lifecycle state change defined by library policy."
            options={statusOptions}
            value={toStatus}
            errorMessage={errors.to_status}
            onChange={(e) => {
              setToStatus(e.target.value);
              if (errors.to_status) {
                setErrors((prev) => ({ ...prev, to_status: undefined }));
              }
            }}
            disabled={isSubmitting}
          />

          {/* Field 2: Mandatory Reason */}
          <Input
            id="copy-transition-reason"
            label="Transition Reason"
            description="Librarian note explaining why the status changed (1-500 characters)."
            placeholder="e.g. Returned with damaged binding, sent to conservation lab..."
            value={reason}
            errorMessage={errors.reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (errors.reason) {
                setErrors((prev) => ({ ...prev, reason: undefined }));
              }
            }}
            disabled={isSubmitting}
          />

          {/* Single primary button per panel */}
          <div
            style={{
              marginTop: tokens.spacing.sm,
              paddingTop: tokens.spacing.md,
              borderTop: `1px solid ${tokens.colors.borderMuted}`,
              display: 'flex',
              justifyContent: 'flex-start',
            }}
          >
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={isSubmitting}
              data-variant="primary"
            >
              {isSubmitting ? 'Updating Status...' : 'Change Status'}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

export default CopyStatusControls;
