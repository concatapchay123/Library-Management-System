import React from 'react';
import { useTokens } from '../tokens';
import { Button, ButtonVariant } from './Button';

export interface EmptyStateAction {
  label: string;
  onAction: () => void;
  variant?: ButtonVariant;
}

export interface EmptyStateProps {
  title: string;
  description: string;
  action?: EmptyStateAction;
  icon?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Reusable Empty State Component for OpenLibraryOS.
 *
 * Implements Acceptance Criteria:
 * "Empty states state what is absent and the one next action when one is permitted."
 *
 * Invariants:
 * - Hick's Law: exactly ONE primary action permitted per empty view.
 * - Title Case action labels.
 * - 2:1 Whitespace ratio on buttons.
 * - WCAG AA contrast compliance and zero pure black/white usage.
 */
export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
  style,
}: EmptyStateProps) {
  const tokens = useTokens();

  const defaultIcon = (
    <div
      aria-hidden="true"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '48px',
        height: '48px',
        borderRadius: tokens.radius.full,
        backgroundColor: tokens.colors.surfaceAlt,
        color: tokens.colors.textMuted,
        fontSize: tokens.typography.fontSizes.xl,
        fontWeight: tokens.typography.fontWeights.bold,
        border: `1px dashed ${tokens.colors.border}`,
      }}
    >
      ∅
    </div>
  );

  return (
    <div
      role="region"
      aria-label={title}
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: tokens.spacing.xl,
        border: `1px dashed ${tokens.colors.border}`,
        borderRadius: tokens.radius.lg,
        backgroundColor: tokens.colors.surface,
        boxSizing: 'border-box',
        gap: tokens.spacing.md,
        ...style,
      }}
    >
      {icon ?? defaultIcon}

      <div style={{ maxWidth: '420px' }}>
        <h3
          style={{
            margin: 0,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.lg,
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
            lineHeight: tokens.typography.lineHeights.tight,
          }}
        >
          {title}
        </h3>

        <p
          style={{
            margin: `${tokens.spacing.xs} 0 0 0`,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
            lineHeight: tokens.typography.lineHeights.normal,
          }}
        >
          {description}
        </p>
      </div>

      {action && (
        <div style={{ marginTop: tokens.spacing.sm }}>
          <Button
            type="button"
            variant={action.variant || 'primary'}
            size="md"
            onClick={action.onAction}
          >
            {action.label}
          </Button>
        </div>
      )}
    </div>
  );
}

export default EmptyState;
