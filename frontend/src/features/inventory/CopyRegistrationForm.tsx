import React, { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { Button, Input, Select, ProblemDetailsRenderer, StatusMessage } from '../../shared/components';
import { BookCopy, Location, ProblemDetails } from '../../shared/api';
import { CopyRegistrationFormValues, CopyRegistrationValidationErrors } from './types';

export interface CopyRegistrationFormProps {
  locations: Location[];
  onCopyCreated?: (copy: BookCopy) => void;
  onSubmitCopy: (values: CopyRegistrationFormValues) => Promise<BookCopy>;
  isSubmitting?: boolean;
}

/**
 * Single-column accessible form for registering new physical book copies.
 *
 * Enforces design & architectural invariants:
 * - Single-column vertical layout.
 * - Semantic spacing (label-to-input 12px, group-to-group 24px, form-to-submit 32px).
 * - Immediate client-side validation for barcode and location before server requests.
 * - Single primary action ("Register Copy") per panel (Von Restorff / Hick's Law).
 * - Surfaces stable RFC Problem Details beside form fields upon conflict or error.
 */
export function CopyRegistrationForm({
  locations,
  onCopyCreated,
  onSubmitCopy,
  isSubmitting = false,
}: CopyRegistrationFormProps) {
  const tokens = useTokens();

  const [formValues, setFormValues] = useState<CopyRegistrationFormValues>({
    barcode: '',
    location_id: '',
    condition_code: '',
  });

  const [errors, setErrors] = useState<CopyRegistrationValidationErrors>({});
  const [serverError, setServerError] = useState<ProblemDetails | Error | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function validate(values: CopyRegistrationFormValues): boolean {
    const newErrors: CopyRegistrationValidationErrors = {};

    const cleanBarcode = values.barcode.trim();
    if (!cleanBarcode) {
      newErrors.barcode = 'Barcode is required';
    } else if (cleanBarcode.length > 64) {
      newErrors.barcode = 'Barcode cannot exceed 64 characters';
    }

    if (!values.location_id) {
      newErrors.location_id = 'Please select a shelving location';
    }

    if (values.condition_code.trim().length > 32) {
      newErrors.condition_code = 'Condition code cannot exceed 32 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMessage(null);
    setServerError(null);

    const isValid = validate(formValues);
    if (!isValid) {
      return;
    }

    try {
      const created = await onSubmitCopy({
        barcode: formValues.barcode.trim(),
        location_id: formValues.location_id,
        condition_code: formValues.condition_code.trim() || 'good',
      });

      setSuccessMessage(`Copy with barcode ${created.barcode} registered successfully.`);
      setFormValues({
        barcode: '',
        location_id: formValues.location_id, // preserve location for repeated scanning convenience
        condition_code: '',
      });
      setErrors({});
      onCopyCreated?.(created);
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
      data-testid="copy-registration-panel"
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
          Register Physical Copy
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
          Add an individually tracked physical item to inventory with unique barcode and location.
        </p>
      </div>

      {successMessage && (
        <StatusMessage status="success" title="Copy Registered">
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
        {/* Field 1: Barcode */}
        <Input
          id="copy-barcode"
          label="Copy Barcode"
          description="Scan or enter physical barcode label (1-64 characters)."
          placeholder="e.g. BC-9781449373320-001 or scan label..."
          value={formValues.barcode}
          errorMessage={errors.barcode}
          onChange={(e) => {
            setFormValues((prev) => ({ ...prev, barcode: e.target.value }));
            if (errors.barcode) {
              setErrors((prev) => ({ ...prev, barcode: undefined }));
            }
          }}
          disabled={isSubmitting}
        />

        {/* Field 2: Shelving Location */}
        <Select
          id="copy-location"
          label="Shelf Location"
          description="Select the physical shelving or holding location."
          options={locationOptions}
          value={formValues.location_id}
          errorMessage={errors.location_id}
          onChange={(e) => {
            setFormValues((prev) => ({ ...prev, location_id: e.target.value }));
            if (errors.location_id) {
              setErrors((prev) => ({ ...prev, location_id: undefined }));
            }
          }}
          disabled={isSubmitting}
        />

        {/* Field 3: Copy Condition */}
        <Input
          id="copy-condition"
          label="Copy Condition"
          optional
          description="Current physical condition assessment (e.g. good, worn, minor cover defect)."
          placeholder="e.g. good"
          value={formValues.condition_code}
          errorMessage={errors.condition_code}
          onChange={(e) => {
            setFormValues((prev) => ({ ...prev, condition_code: e.target.value }));
            if (errors.condition_code) {
              setErrors((prev) => ({ ...prev, condition_code: undefined }));
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
            {isSubmitting ? 'Registering Copy...' : 'Register Copy'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default CopyRegistrationForm;
