import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { EditionUnavailableStateProps } from './types';

/**
 * Explanatory view rendered when the education edition is disabled for the organization.
 *
 * Requirements & Invariants:
 * - Leaks NO tenant database configuration, connection strings, or internal infrastructure details.
 * - Provides clear, actionable language explaining why education features are disabled.
 * - Preserves a predictable, accessible return path back to standard library circulation operations.
 */
export function EditionUnavailableState({
  detail = 'The education edition is not enabled for this organization.',
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
      aria-label="Edition Unavailable"
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
          ℹ
        </div>

        <div style={{ flex: 1 }}>
          <h2
            style={{
              margin: 0,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
              lineHeight: tokens.typography.lineHeights.tight,
            }}
          >
            Education Edition Unavailable
          </h2>

          <p
            style={{
              marginTop: tokens.spacing.sm,
              marginBottom: tokens.spacing.md,
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
              lineHeight: tokens.typography.lineHeights.normal,
            }}
          >
            {detail} Student and teacher management, class rosters, and academic borrower loan policies
            are only accessible when the Education module is activated for your library organization.
          </p>

          <p
            style={{
              margin: 0,
              marginBottom: tokens.spacing.lg,
              fontSize: tokens.typography.fontSizes.xs,
              color: tokens.colors.textMuted,
              lineHeight: tokens.typography.lineHeights.normal,
            }}
          >
            If your institution requires academic tracking, please contact your OpenLibraryOS system administrator
            to enable the Education edition for this organization.
          </p>

          <div style={{ display: 'flex', gap: tokens.spacing.sm, flexWrap: 'wrap' }}>
            <a
              href="#/circulation"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                backgroundColor: tokens.colors.primary,
                color: tokens.colors.primaryContrastText,
                borderRadius: tokens.radius.md,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.semibold,
                textDecoration: 'none',
                outline: 'none',
                transition: 'background-color 150ms ease',
              }}
            >
              Return to Circulation
            </a>

            <a
              href="#/catalog"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                backgroundColor: tokens.colors.surface,
                color: tokens.colors.textPrimary,
                border: `1px solid ${tokens.colors.border}`,
                borderRadius: tokens.radius.md,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.medium,
                textDecoration: 'none',
                outline: 'none',
              }}
            >
              Explore Catalog
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
