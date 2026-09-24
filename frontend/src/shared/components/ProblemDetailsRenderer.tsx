import React, { useState } from 'react';
import { useTokens } from '../tokens';
import { Button } from './Button';
import { ProblemDetailsError, normalizeProblemDetails } from '../api/problemDetails';
import { ProblemDetails } from '../api/types';

export interface ProblemDetailsRendererProps {
  error: ProblemDetailsError | Error | ProblemDetails | unknown;
  onRetry?: () => void | Promise<void>;
  isSafeToRetry?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Problem Details Renderer for OpenLibraryOS.
 *
 * Implements strict architectural & UI/UX invariants:
 * - Non-color status cues: combines status icon, 'ERROR' badge, and descriptive text.
 * - Prominent support request_id: visible citation element with a 1-click copy action.
 * - WCAG AA contrast compliance and zero pure black/white usage.
 * - Safe error handling: never renders raw SQL, stack traces, or credentials.
 * - Safe retry controls: only exposes retry action for safe documented requests.
 */
export function ProblemDetailsRenderer({
  error,
  onRetry,
  isSafeToRetry = false,
  className,
  style,
}: ProblemDetailsRendererProps) {
  const tokens = useTokens();
  const [copySuccess, setCopySuccess] = useState(false);

  const normalizedError: ProblemDetailsError =
    error instanceof ProblemDetailsError
      ? error
      : normalizeProblemDetails(error);

  const dangerToken = tokens.colors.status.danger;

  const handleCopyRequestId = async () => {
    if (!normalizedError.requestId) return;
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(normalizedError.requestId);
        setCopySuccess(true);
        setTimeout(() => setCopySuccess(false), 2000);
      }
    } catch {
      // Clipboard access may fail in non-secure or restricted contexts
    }
  };

  return (
    <div
      role="alert"
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.md,
        padding: tokens.spacing.lg,
        backgroundColor: dangerToken.bg,
        border: `1px solid ${dangerToken.border}`,
        borderRadius: tokens.radius.md,
        color: tokens.colors.textPrimary,
        boxSizing: 'border-box',
        ...style,
      }}
    >
      {/* Header section with icon, badge, and title */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: tokens.spacing.md }}>
        <div
          data-testid="status-icon-danger"
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '28px',
            height: '28px',
            borderRadius: tokens.radius.full,
            backgroundColor: dangerToken.color,
            color: tokens.colors.surface,
            fontWeight: tokens.typography.fontWeights.bold,
            fontSize: tokens.typography.fontSizes.sm,
            flexShrink: 0,
          }}
        >
          ✕
        </div>

        <div style={{ flex: 1 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: tokens.spacing.xs,
              marginBottom: tokens.spacing.xs,
            }}
          >
            <span
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xs,
                fontWeight: tokens.typography.fontWeights.bold,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: dangerToken.color,
              }}
            >
              ERROR
            </span>
            <span style={{ color: tokens.colors.textMuted }}>•</span>
            <span
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.medium,
                color: tokens.colors.textSecondary,
              }}
            >
              Status {normalizedError.status}
            </span>
          </div>

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
            {normalizedError.title}
          </h3>

          <p
            style={{
              margin: `${tokens.spacing.sm} 0 0 0`,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
              lineHeight: tokens.typography.lineHeights.normal,
            }}
          >
            {normalizedError.detail}
          </p>

          {normalizedError.helpfulAction && (
            <p
              style={{
                margin: `${tokens.spacing.xs} 0 0 0`,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.medium,
                color: tokens.colors.textPrimary,
                lineHeight: tokens.typography.lineHeights.normal,
              }}
            >
              {normalizedError.helpfulAction}
            </p>
          )}
        </div>
      </div>

      {/* Support Request ID display container */}
      <div
        data-testid="support-request-id"
        role="note"
        aria-label="Support correlation identifier"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: tokens.spacing.sm,
          padding: `${tokens.spacing.xs} ${tokens.spacing.md}`,
          backgroundColor: tokens.colors.surface,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: tokens.radius.sm,
          fontSize: tokens.typography.fontSizes.xs,
          fontFamily: tokens.typography.fontFamily,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.xs }}>
          <span style={{ color: tokens.colors.textMuted, fontWeight: tokens.typography.fontWeights.medium }}>
            Support Request ID:
          </span>
          <code
            style={{
              fontFamily: 'monospace',
              fontSize: tokens.typography.fontSizes.xs,
              color: tokens.colors.textPrimary,
              fontWeight: tokens.typography.fontWeights.bold,
              userSelect: 'all',
            }}
          >
            {normalizedError.requestId}
          </code>
        </div>

        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleCopyRequestId}
          aria-label="Copy Request ID"
          style={{ fontSize: tokens.typography.fontSizes.xs, padding: '4px 8px' }}
        >
          {copySuccess ? 'Copied ID' : 'Copy ID'}
        </Button>
      </div>

      {/* Retry controls (strictly limited to safe requests) */}
      {onRetry && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: tokens.spacing.md,
            marginTop: tokens.spacing.xs,
          }}
        >
          {isSafeToRetry ? (
            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={onRetry}
            >
              Retry Request
            </Button>
          ) : (
            <span
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xs,
                color: tokens.colors.textMuted,
                fontStyle: 'italic',
              }}
            >
              This action cannot be automatically repeated. Please review before repeating.
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default ProblemDetailsRenderer;
