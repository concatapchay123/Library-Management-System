import React, { useState } from 'react';
import { useTokens } from '../tokens';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  id: string;
  label: string;
  description?: string;
  errorMessage?: string;
  optional?: boolean;
  isFullWidth?: boolean;
  options?: SelectOption[];
  children?: React.ReactNode;
}

/**
 * Accessible Labeled Select Dropdown for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - Single-column vertical stacking (Label above Select)
 * - 12px Label-to-Input semantic spacing
 * - Programmatic accessibility: id, htmlFor, aria-describedby, aria-invalid, role="alert"
 * - "(Optional)" badge instead of distracting red asterisks
 * - High-contrast visible focus outline
 */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    id,
    label,
    description,
    errorMessage,
    optional = false,
    isFullWidth = true,
    disabled = false,
    options,
    children,
    style,
    onFocus,
    onBlur,
    ...props
  },
  ref,
) {
  const tokens = useTokens();
  const [isFocused, setIsFocused] = useState(false);

  const descriptionId = description ? `${id}-description` : undefined;
  const errorId = errorMessage ? `${id}-error` : undefined;

  const describedBy = [descriptionId, errorId].filter(Boolean).join(' ') || undefined;
  const isInvalid = Boolean(errorMessage);

  let borderColor = tokens.colors.border;
  if (isInvalid) {
    borderColor = tokens.colors.status.danger.color;
  } else if (isFocused) {
    borderColor = tokens.colors.borderFocus;
  }

  const selectStyle: React.CSSProperties = {
    display: 'block',
    width: '100%',
    boxSizing: 'border-box',
    fontFamily: tokens.typography.fontFamily,
    fontSize: tokens.typography.fontSizes.md,
    lineHeight: tokens.typography.lineHeights.normal,
    color: tokens.colors.textPrimary,
    backgroundColor: tokens.colors.surface,
    border: `1px solid ${borderColor}`,
    borderRadius: tokens.radius.md,
    paddingTop: tokens.spacing.sm,
    paddingBottom: tokens.spacing.sm,
    paddingLeft: tokens.spacing.md,
    paddingRight: tokens.spacing.xl,
    outline: isFocused ? tokens.focus.cssString : 'none',
    outlineOffset: isFocused ? tokens.focus.outlineOffset : undefined,
    opacity: disabled ? 0.6 : 1,
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'border-color 150ms ease, box-shadow 150ms ease',
    appearance: 'auto',
    ...style,
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: isFullWidth ? '100%' : 'auto',
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: tokens.spacing.xs,
        }}
      >
        <label
          htmlFor={id}
          style={{
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            fontWeight: tokens.typography.fontWeights.semibold,
            color: tokens.colors.textPrimary,
            lineHeight: tokens.typography.lineHeights.tight,
          }}
        >
          {label}
          {optional && (
            <span
              style={{
                marginLeft: tokens.spacing.xs,
                fontSize: tokens.typography.fontSizes.xs,
                fontWeight: tokens.typography.fontWeights.normal,
                color: tokens.colors.textMuted,
              }}
            >
              (Optional)
            </span>
          )}
        </label>
      </div>

      {description && (
        <span
          id={descriptionId}
          style={{
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.xs,
            color: tokens.colors.textSecondary,
            lineHeight: tokens.typography.lineHeights.normal,
            marginBottom: tokens.spacing.xs,
          }}
        >
          {description}
        </span>
      )}

      <div style={{ marginTop: tokens.spacing.xs }}>
        <select
          ref={ref}
          id={id}
          disabled={disabled}
          aria-invalid={isInvalid ? 'true' : 'false'}
          aria-describedby={describedBy}
          style={selectStyle}
          onFocus={(e) => {
            setIsFocused(true);
            if (onFocus) onFocus(e);
          }}
          onBlur={(e) => {
            setIsFocused(false);
            if (onBlur) onBlur(e);
          }}
          {...props}
        >
          {options
            ? options.map((opt) => (
                <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                </option>
              ))
            : children}
        </select>
      </div>

      {errorMessage && (
        <div
          id={errorId}
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: tokens.spacing.xs,
            marginTop: tokens.spacing.xs,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.xs,
            color: tokens.colors.status.danger.color,
            lineHeight: tokens.typography.lineHeights.normal,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              fontWeight: tokens.typography.fontWeights.bold,
            }}
          >
            ✕
          </span>
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
});

export default Select;
