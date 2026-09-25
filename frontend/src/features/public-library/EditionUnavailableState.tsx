import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { EditionUnavailableStateProps } from './types';

/**
 * Explanatory view rendered when the public library edition is disabled for the organization.
 *
 * Requirements & Invariants:
 * - Leaks NO tenant database configuration, connection strings, or internal infrastructure details.
 * - Provides clear, actionable language explaining why public library features are disabled.
 * - Preserves a predictable, accessible return path back to standard library circulation operations.
 */
export function EditionUnavailableState({
  detail = 'The public library edition is not enabled for this organization.',
  className,
  style,
}: EditionUnavailableStateProps) {
  const tokens = useTokens();

  const outerRadius = 12;
  const paddingVal = 24;
  const innerRadius = calcNestedRadius(outerRadius, paddingVal);

  return (
    <section
      role="region"
      aria-label="Public Library Edition Unavailable"
      className={className}
      style={{
        backgroundColor: tokens.colors.surfaceAlt,
        border: `1px solid ${tokens.colors.border}`,
        borderRadius: `${outerRadius}px`,
        padding: `${paddingVal}px`,
        maxWidth: '680px',
        margin: `${tokens.spacing.xl} auto`,
        boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: tokens.spacing.md,
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: '44px',
            height: '44px',
            borderRadius: `${innerRadius}px`,
            backgroundColor: tokens.colors.status.warning.bg,
            color: tokens.colors.status.warning.color,
            border: `1px solid ${tokens.colors.status.warning.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: tokens.typography.fontSizes.xl,
            fontWeight: tokens.typography.fontWeights.bold,
            flexShrink: 0,
          }}
        >
          ⊘
        </div>

        <div style={{ flex: 1 }}>
          <h3
            style={{
              margin: `0 0 ${tokens.spacing.xs} 0`,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.semibold,
              color: tokens.colors.textPrimary,
            }}
          >
            Public Library Edition Unavailable
          </h3>

          <p
            style={{
              margin: `0 0 ${tokens.spacing.md} 0`,
              fontSize: tokens.typography.fontSizes.sm,
              lineHeight: tokens.typography.lineHeights.normal,
              color: tokens.colors.textSecondary,
            }}
          >
            {detail}
          </p>

          <p
            style={{
              margin: `0 0 ${tokens.spacing.lg} 0`,
              fontSize: tokens.typography.fontSizes.sm,
              lineHeight: tokens.typography.lineHeights.normal,
              color: tokens.colors.textMuted,
            }}
          >
            Public memberships, subscription policies, fine assessments, and invoice tracking require the Public Library edition to be enabled in your organization profile. Contact your system administrator or return to core library workflows.
          </p>

          <div
            style={{
              display: 'flex',
              gap: tokens.spacing.md,
              alignItems: 'center',
            }}
          >
            <a
              href="#/circulation"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                paddingTop: '8px',
                paddingBottom: '8px',
                paddingLeft: '16px',
                paddingRight: '16px',
                borderRadius: tokens.radius.md,
                backgroundColor: tokens.colors.primary,
                color: tokens.colors.primaryContrastText,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.medium,
                textDecoration: 'none',
              }}
            >
              Return to Circulation Desk
            </a>
            <a
              href="#/catalog"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                paddingTop: '8px',
                paddingBottom: '8px',
                paddingLeft: '16px',
                paddingRight: '16px',
                borderRadius: tokens.radius.md,
                backgroundColor: tokens.colors.surfaceElevated,
                color: tokens.colors.textPrimary,
                border: `1px solid ${tokens.colors.border}`,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.medium,
                textDecoration: 'none',
              }}
            >
              Browse Catalog
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
