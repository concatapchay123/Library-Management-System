import React, { useState, useEffect } from 'react';
import { useTokens } from '../../shared/tokens';
import { Button, Input, Select, ProblemDetailsRenderer, StatusMessage } from '../../shared/components';
import { BookCopy, Location, ProblemDetails } from '../../shared/api';
import { LocationAssignmentFormValues } from './types';

export interface LocationAssignmentFormProps {
  copy: BookCopy;
  locations: Location[];
  onCopyUpdated?: (copy: BookCopy) => void;
  onSubmitUpdate: (copyId: string, values: LocationAssignmentFormValues) => Promise<BookCopy>;
  isSubmitting?: boolean;
}

/**
 * Single-column accessible form for assigning shelf location and condition to an existing copy.
 *
 * Enforces design invariants:
 * - Single-column vertical layout.
 * - Semantic spacing and accessible labels.
 * - Single primary action ("Update Location") per panel.
 * - RFC Problem Details surfaced beside form if operation fails.
 */
export function LocationAssignmentForm({
  copy,
  locations,
  onCopyUpdated,
  onSubmitUpdate,
  isSubmitting = false,
}: LocationAssignmentFormProps) {
  const tokens = useTokens();

  const [formValues, setFormValues] = useState<LocationAssignmentFormValues>({
    location_id: copy.location_id,
    condition_code: copy.condition_code || '',
  });

  const [error, setError] = useState<string | undefined>(undefined);
  const [serverError, setServerError] = useState<ProblemDetails | Error | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    setFormValues({
      location_id: copy.location_id,
      condition_code: copy.condition_code || '',
    });
    setError(undefined);
    setServerError(null);
    setSuccessMessage(null);
  }, [copy.copy_id, copy.location_id, copy.condition_code]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMessage(null);
    setServerError(null);

    if (!formValues.location_id) {
      setError('Please select a shelving location');
      return;
    }

    if (formValues.condition_code.trim().length > 32) {
      setError('Condition code cannot exceed 32 characters');
      return;
    }

    try {
      const updated = await onSubmitUpdate(copy.copy_id, {
        location_id: formValues.location_id,
        condition_code: formValues.condition_code.trim() || 'good',
      });

      setSuccessMessage(`Location and condition for barcode ${copy.barcode} updated successfully.`);
      setError(undefined);
      onCopyUpdated?.(updated);
    } catch (err) {
      setServerError(err as ProblemDetails | Error);
    }
  };

  const locationOptions = [
    { value: '', label: '-- Select shelving location --' },
    ...locations.map((loc) => ({
      value: loc.location_id,
      label: `${loc.name} (${loc.code})`,
    })),
  ];

  return (
    <div
      data-testid="location-assignment-panel"
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
          Assign Shelf Location & Condition
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
          Move copy to another shelving tier, holding shelf, or record physical condition updates.
        </p>
      </div>

      {successMessage && (
        <StatusMessage status="success" title="Location Updated">
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

      <form
        onSubmit={handleSubmit}
        noValidate
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.semantic.groupToGroup,
        }}
      >
        {/* Field 1: Shelving Location */}
        <Select
          id="assign-location"
          label="New Shelf Location"
          description="Select the updated physical shelving or holding location."
          options={locationOptions}
          value={formValues.location_id}
          errorMessage={error}
          onChange={(e) => {
            setFormValues((prev) => ({ ...prev, location_id: e.target.value }));
            if (error) setError(undefined);
          }}
          disabled={isSubmitting}
        />

        {/* Field 2: Condition Code */}
        <Input
          id="update-condition"
          label="Condition Assessment"
          optional
          description="Update condition assessment (e.g. good, fair, worn, minor cover defect)."
          placeholder="e.g. good"
          value={formValues.condition_code}
          onChange={(e) => {
            setFormValues((prev) => ({ ...prev, condition_code: e.target.value }));
          }}
          disabled={isSubmitting}
        />

        {/* Action Button: single primary per panel */}
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
            {isSubmitting ? 'Updating...' : 'Update Location'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default LocationAssignmentForm;
