import { useState, useMemo } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { Button, Input, LoadingSkeleton } from '../../shared/components';
import { MembershipSummaryViewProps } from './types';
import { PublicLibraryMembershipPlan, PublicLibrarySubscription } from '../../shared/api';

export function MembershipSummaryView({
  members,
  plans,
  subscriptions,
  isLoading,
  onRefresh,
}: MembershipSummaryViewProps) {
  const tokens = useTokens();
  const [searchQuery, setSearchQuery] = useState('');

  // Map plans by plan_id
  const planMap = useMemo(() => {
    const map = new Map<string, PublicLibraryMembershipPlan>();
    for (const p of plans) {
      map.set(p.plan_id, p);
    }
    return map;
  }, [plans]);

  // Map active subscription by member_id
  const subscriptionMap = useMemo(() => {
    const map = new Map<string, PublicLibrarySubscription>();
    for (const s of subscriptions) {
      if (s.status === 'active') {
        map.set(s.member_id, s);
      }
    }
    return map;
  }, [subscriptions]);

  const filteredMembers = useMemo(() => {
    if (!searchQuery.trim()) return members;
    const q = searchQuery.toLowerCase().trim();
    return members.filter((m) =>
      m.member_number.toLowerCase().includes(q) ||
      m.user_id.toLowerCase().includes(q) ||
      m.status.toLowerCase().includes(q)
    );
  }, [members, searchQuery]);

  const outerRadius = 12;
  const paddingVal = 20;
  const innerRadius = calcNestedRadius(outerRadius, paddingVal);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xl }}>
      {/* Information Header & Server Policy Rule Explanation */}
      <section
        role="region"
        aria-label="Server Borrowing Policy Configuration"
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: `${outerRadius}px`,
          padding: `${paddingVal}px`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: tokens.spacing.md }}>
          <div
            aria-hidden="true"
            style={{
              width: '36px',
              height: '36px',
              borderRadius: `${innerRadius}px`,
              backgroundColor: tokens.colors.status.info.bg,
              color: tokens.colors.status.info.color,
              border: `1px solid ${tokens.colors.status.info.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: tokens.typography.fontWeights.bold,
              flexShrink: 0,
            }}
          >
            ℹ
          </div>
          <div>
            <h3
              style={{
                margin: `0 0 ${tokens.spacing.xs} 0`,
                fontSize: tokens.typography.fontSizes.md,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textPrimary,
              }}
            >
              Public Library Membership & Policy Enforcement
            </h3>
            <p
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.sm,
                lineHeight: tokens.typography.lineHeights.normal,
                color: tokens.colors.textSecondary,
              }}
            >
              Borrowing policy is enforced authoritatively by the backend server; borrow limits and active loan checks are resolved on loan checkout without client-side entitlement math.
            </p>
          </div>
        </div>
      </section>

      {/* Search & Actions Bar */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.md,
        }}
      >
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'flex-end',
            gap: tokens.spacing.md,
          }}
        >
          <div style={{ flex: '1 1 300px' }}>
            <Input
              id="member-search"
              label="Find Members"
              placeholder="Search by member number, user ID, or status..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Button
            variant="secondary"
            onClick={onRefresh}
            style={{ height: '40px' }}
          >
            Refresh Records
          </Button>
        </div>
      </div>

      {/* Member Directory List */}
      {isLoading ? (
        <LoadingSkeleton lines={3} />
      ) : filteredMembers.length === 0 ? (
        <div
          style={{
            padding: `${tokens.spacing['2xl']}`,
            textAlign: 'center',
            backgroundColor: tokens.colors.surfaceAlt,
            borderRadius: tokens.radius.lg,
            border: `1px dashed ${tokens.colors.border}`,
            color: tokens.colors.textMuted,
          }}
        >
          No public library members found matching your search.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}>
          {filteredMembers.map((member) => {
            const sub = subscriptionMap.get(member.member_id);
            const plan = sub ? planMap.get(sub.plan_id) : undefined;

            return (
              <article
                key={member.member_id}
                style={{
                  backgroundColor: tokens.colors.surface,
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: `${outerRadius}px`,
                  padding: `${paddingVal}px`,
                  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.04)',
                }}
              >
                {/* Header row: Member number, status badge */}
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: tokens.spacing.sm,
                    marginBottom: tokens.spacing.md,
                    paddingBottom: tokens.spacing.sm,
                    borderBottom: `1px solid ${tokens.colors.borderMuted}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.md }}>
                    <span
                      style={{
                        fontFamily: tokens.typography.monoFontFamily,
                        fontSize: tokens.typography.fontSizes.lg,
                        fontWeight: tokens.typography.fontWeights.bold,
                        color: tokens.colors.textPrimary,
                      }}
                    >
                      {member.member_number}
                    </span>
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        fontFamily: tokens.typography.monoFontFamily,
                        color: tokens.colors.textMuted,
                      }}
                    >
                      User ID: {member.user_id}
                    </span>
                  </div>

                  {/* Status badge with text and non-color cue */}
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: tokens.spacing.xs,
                      padding: '4px 10px',
                      borderRadius: tokens.radius.sm,
                      fontSize: tokens.typography.fontSizes.xs,
                      fontWeight: tokens.typography.fontWeights.semibold,
                      backgroundColor:
                        member.status === 'active'
                          ? tokens.colors.status.success.bg
                          : member.status === 'suspended'
                          ? tokens.colors.status.warning.bg
                          : tokens.colors.status.danger.bg,
                      color:
                        member.status === 'active'
                          ? tokens.colors.status.success.color
                          : member.status === 'suspended'
                          ? tokens.colors.status.warning.color
                          : tokens.colors.status.danger.color,
                      border: `1px solid ${
                        member.status === 'active'
                          ? tokens.colors.status.success.border
                          : member.status === 'suspended'
                          ? tokens.colors.status.warning.border
                          : tokens.colors.status.danger.border
                      }`,
                    }}
                  >
                    {member.status === 'active' && '● Active'}
                    {member.status === 'suspended' && '⊘ Suspended'}
                    {member.status !== 'active' && member.status !== 'suspended' && `✕ ${member.status}`}
                  </span>
                </div>

                {/* Subscription and Server Borrowing Policy Summary */}
                <div
                  style={{
                    backgroundColor: tokens.colors.surfaceAlt,
                    borderRadius: `${innerRadius}px`,
                    padding: tokens.spacing.md,
                    border: `1px solid ${tokens.colors.borderMuted}`,
                  }}
                >
                  <h4
                    style={{
                      margin: `0 0 ${tokens.spacing.xs} 0`,
                      fontSize: tokens.typography.fontSizes.sm,
                      fontWeight: tokens.typography.fontWeights.semibold,
                      color: tokens.colors.textSecondary,
                    }}
                  >
                    Subscription & Borrowing Policy Summary
                  </h4>

                  {plan ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
                        <span style={{ fontWeight: tokens.typography.fontWeights.medium, color: tokens.colors.textPrimary }}>
                          {plan.name}
                        </span>
                        <span
                          style={{
                            fontSize: tokens.typography.fontSizes.xs,
                            backgroundColor: tokens.colors.surfaceElevated,
                            padding: '2px 8px',
                            borderRadius: tokens.radius.sm,
                            border: `1px solid ${tokens.colors.border}`,
                          }}
                        >
                          Code: {plan.code}
                        </span>
                      </div>

                      <div
                        style={{
                          fontSize: tokens.typography.fontSizes.sm,
                          color: tokens.colors.textSecondary,
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: tokens.spacing.md,
                        }}
                      >
                        <span>
                          <strong>Allowance:</strong> {plan.max_active_loans} active loans
                        </span>
                        <span>
                          <strong>Duration:</strong> {plan.duration_days}-day borrowing duration
                        </span>
                        <span>
                          <strong>Rate:</strong> {plan.currency} {plan.price}
                        </span>
                      </div>

                      {sub && (
                        <div
                          style={{
                            fontSize: tokens.typography.fontSizes.xs,
                            color: tokens.colors.textMuted,
                            marginTop: tokens.spacing.xs,
                          }}
                        >
                          Active Period: {new Date(sub.starts_at).toLocaleDateString()} to{' '}
                          {new Date(sub.ends_at).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p
                      style={{
                        margin: 0,
                        fontSize: tokens.typography.fontSizes.sm,
                        color: tokens.colors.textMuted,
                        fontStyle: 'italic',
                      }}
                    >
                      No active subscription configured. Default organization policy applies on checkout.
                    </p>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
