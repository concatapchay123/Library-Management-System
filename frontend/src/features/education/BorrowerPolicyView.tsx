import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { BorrowerPolicyViewProps } from './types';
import { LoadingSkeleton, EmptyState } from '../../shared/components';

/**
 * Borrower Policy View (FE-009).
 *
 * Implements acceptance criteria and architectural invariants:
 * - Renders configured borrower policy values and their effect in plain language.
 * - Describes server configuration rather than asserting a client-calculated entitlement.
 * - Strictly avoids duplicating education policy logic or calculating remaining balances in the browser.
 * - Informs staff that authorization and checkout limits are evaluated authoritatively by the backend server.
 */
export function BorrowerPolicyView({
  policies,
  isLoading = false,
}: BorrowerPolicyViewProps) {
  const tokens = useTokens();

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.md }}>
        <LoadingSkeleton height={120} />
        <LoadingSkeleton height={120} />
      </div>
    );
  }

  const studentPolicy = policies.find((p) => p.borrower_type.toLowerCase() === 'student');
  const teacherPolicy = policies.find((p) => p.borrower_type.toLowerCase() === 'teacher');

  const cardRadius = 10;
  const cardPadding = 20;
  const innerRadius = calcNestedRadius(cardRadius, cardPadding);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}>
      <header>
        <h3
          style={{
            margin: 0,
            fontSize: tokens.typography.fontSizes.lg,
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
          }}
        >
          Configured Borrower Policies
        </h3>
        <p
          style={{
            margin: `${tokens.spacing.xs} 0 0`,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
          }}
        >
          Review active organization loan quotas and checkout windows for academic patrons.
        </p>
      </header>

      {/* Authoritative Server Policy Explanation Notice */}
      <aside
        aria-label="Server Policy Context"
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: `${tokens.radius.md}`,
          padding: tokens.spacing.md,
          fontSize: tokens.typography.fontSizes.sm,
          color: tokens.colors.textSecondary,
          lineHeight: tokens.typography.lineHeights.normal,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, marginBottom: tokens.spacing.xs }}>
          <span aria-hidden="true" style={{ color: tokens.colors.primary, fontWeight: 'bold' }}>
            ℹ
          </span>
          <strong style={{ color: tokens.colors.textPrimary }}>Authoritative Server Circulation Port</strong>
        </div>
        Checkout eligibility and due dates are determined authoritatively by the library server during checkout
        based on active organization policy records. The client does not compute or predict entitlement balances.
      </aside>

      {/* Policy Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: tokens.spacing.lg,
        }}
      >
        {/* Student Policy Card */}
        <section
          aria-labelledby="student-policy-heading"
          style={{
            backgroundColor: tokens.colors.surface,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: `${cardRadius}px`,
            padding: `${cardPadding}px`,
            boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.md,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h4
              id="student-policy-heading"
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.md,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              Student Borrower Policy
            </h4>
            <span
              style={{
                fontSize: tokens.typography.fontSizes.xs,
                fontWeight: tokens.typography.fontWeights.semibold,
                padding: '2px 8px',
                borderRadius: `${innerRadius}px`,
                backgroundColor: tokens.colors.status.info.bg,
                color: tokens.colors.status.info.color,
                border: `1px solid ${tokens.colors.status.info.border}`,
              }}
            >
              Role: Student
            </span>
          </div>

          <div
            style={{
              backgroundColor: tokens.colors.surfaceAlt,
              borderRadius: `${innerRadius}px`,
              padding: tokens.spacing.md,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: tokens.spacing.sm,
            }}
          >
            <div>
              <span style={{ display: 'block', fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>
                Active Loan Limit
              </span>
              <span
                style={{
                  display: 'block',
                  fontSize: tokens.typography.fontSizes.xl,
                  fontWeight: tokens.typography.fontWeights.bold,
                  color: tokens.colors.textPrimary,
                  marginTop: '2px',
                }}
              >
                {studentPolicy ? `${studentPolicy.max_active_loans} Active Loans` : '5 Active Loans (Default)'}
              </span>
            </div>

            <div>
              <span style={{ display: 'block', fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>
                Standard Loan Window
              </span>
              <span
                style={{
                  display: 'block',
                  fontSize: tokens.typography.fontSizes.xl,
                  fontWeight: tokens.typography.fontWeights.bold,
                  color: tokens.colors.textPrimary,
                  marginTop: '2px',
                }}
              >
                {studentPolicy ? `${studentPolicy.duration_days} Days` : '14 Days (Default)'}
              </span>
            </div>
          </div>

          <div style={{ fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textSecondary, lineHeight: tokens.typography.lineHeights.normal }}>
            <strong>Operational Effect:</strong> When an enrolled student requests a book loan at the circulation desk,
            the backend loan service snapshots this policy, applying a {studentPolicy ? studentPolicy.duration_days : 14}-day return period and capping concurrent active checkouts at {studentPolicy ? studentPolicy.max_active_loans : 5}.
          </div>
        </section>

        {/* Teacher / Faculty Policy Card */}
        <section
          aria-labelledby="teacher-policy-heading"
          style={{
            backgroundColor: tokens.colors.surface,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: `${cardRadius}px`,
            padding: `${cardPadding}px`,
            boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.md,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h4
              id="teacher-policy-heading"
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.md,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              Faculty / Teacher Borrower Policy
            </h4>
            <span
              style={{
                fontSize: tokens.typography.fontSizes.xs,
                fontWeight: tokens.typography.fontWeights.semibold,
                padding: '2px 8px',
                borderRadius: `${innerRadius}px`,
                backgroundColor: tokens.colors.surfaceElevated,
                color: tokens.colors.primary,
                border: `1px solid ${tokens.colors.primary}`,
              }}
            >
              Role: Faculty
            </span>
          </div>

          <div
            style={{
              backgroundColor: tokens.colors.surfaceAlt,
              borderRadius: `${innerRadius}px`,
              padding: tokens.spacing.md,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: tokens.spacing.sm,
            }}
          >
            <div>
              <span style={{ display: 'block', fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>
                Active Loan Limit
              </span>
              <span
                style={{
                  display: 'block',
                  fontSize: tokens.typography.fontSizes.xl,
                  fontWeight: tokens.typography.fontWeights.bold,
                  color: tokens.colors.textPrimary,
                  marginTop: '2px',
                }}
              >
                {teacherPolicy ? `${teacherPolicy.max_active_loans} Active Loans` : '20 Active Loans (Default)'}
              </span>
            </div>

            <div>
              <span style={{ display: 'block', fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>
                Standard Loan Window
              </span>
              <span
                style={{
                  display: 'block',
                  fontSize: tokens.typography.fontSizes.xl,
                  fontWeight: tokens.typography.fontWeights.bold,
                  color: tokens.colors.textPrimary,
                  marginTop: '2px',
                }}
              >
                {teacherPolicy ? `${teacherPolicy.duration_days} Days` : '90 Days (Default)'}
              </span>
            </div>
          </div>

          <div style={{ fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textSecondary, lineHeight: tokens.typography.lineHeights.normal }}>
            <strong>Operational Effect:</strong> Faculty members receive extended academic quarters ({teacherPolicy ? teacherPolicy.duration_days : 90} days)
            and a higher borrowing volume ({teacherPolicy ? teacherPolicy.max_active_loans : 20} items) to support classroom curricula and ongoing academic research.
          </div>
        </section>
      </div>

      {policies.length === 0 && !isLoading && (
        <EmptyState
          title="Default Education Policies In Effect"
          description="Your organization is operating under standard defaults (Student: 5 loans / 14 days; Faculty: 20 loans / 90 days)."
        />
      )}
    </div>
  );
}
