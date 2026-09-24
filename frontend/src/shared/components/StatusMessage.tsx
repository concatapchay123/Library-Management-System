import React from 'react';
import { useTokens, StatusVariant } from '../tokens';

export interface StatusMessageProps {
  status: StatusVariant;
  title?: string;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Accessible Status Message Component for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - Non-color status cues: every status state combines an icon identifier, textual label, and descriptive content
 * - ARIA live region support: role="alert" for danger, role="status" for success/warning/info
 * - Contrast-compliant background and typography
 */
export function StatusMessage({
  status,
  title,
  children,
  className,
  style,
}: StatusMessageProps) {
  const tokens = useTokens();
  const statusToken = tokens.colors.status[status];

  const role = status === 'danger' ? 'alert' : 'status';

  const iconSymbols: Record<StatusVariant, string> = {
    success: '✓',
    warning: '⚠',
    danger: '✕',
    info: 'ℹ',
  };

  return (
    <div
      role={role}
      className={className}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: tokens.spacing.md,
        padding: tokens.spacing.md,
        backgroundColor: statusToken.bg,
        border: `1px solid ${statusToken.border}`,
        borderRadius: tokens.radius.md,
        color: tokens.colors.textPrimary,
        boxSizing: 'border-box',
        ...style,
      }}
    >
      <div
        data-testid={`status-icon-${status}`}
        aria-hidden="true"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '24px',
          height: '24px',
          borderRadius: tokens.radius.full,
          backgroundColor: statusToken.color,
          color: tokens.colors.surface,
          fontWeight: tokens.typography.fontWeights.bold,
          fontSize: tokens.typography.fontSizes.sm,
          flexShrink: 0,
        }}
      >
        {iconSymbols[status]}
      </div>

      <div style={{ flex: 1 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: tokens.spacing.xs,
            marginBottom: title || children ? tokens.spacing.xs : 0,
          }}
        >
          <span
            style={{
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.xs,
              fontWeight: tokens.typography.fontWeights.bold,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: statusToken.color,
            }}
          >
            {statusToken.label}
          </span>
          {title && (
            <>
              <span style={{ color: tokens.colors.textMuted }}>•</span>
              <span
                style={{
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.sm,
                  fontWeight: tokens.typography.fontWeights.semibold,
                  color: tokens.colors.textPrimary,
                }}
              >
                {title}
              </span>
            </>
          )}
        </div>

        <div
          style={{
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
            lineHeight: tokens.typography.lineHeights.normal,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

export default StatusMessage;
