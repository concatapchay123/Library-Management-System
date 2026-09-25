import { useState, useEffect, useCallback, useRef, useContext } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { ProblemDetailsRenderer, LoadingSkeleton } from '../../shared/components';
import {
  apiClient,
  ProblemDetails,
  ProblemDetailsError,
  PublicLibraryMember,
  PublicLibraryMembershipPlan,
  PublicLibrarySubscription,
  PublicLibraryFine,
  PublicLibraryInvoice,
  PublicLibraryPayment,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import { PublicLibraryTab, PublicLibraryWorkspaceProps } from './types';
import { EditionUnavailableState } from './EditionUnavailableState';
import { MembershipSummaryView } from './MembershipSummaryView';
import { FinesView } from './FinesView';
import { InvoicesView } from './InvoicesView';
import { PaymentsView } from './PaymentsView';

function parseProblem(err: unknown): { isUnavailable: boolean; detail?: string; problem: ProblemDetails } {
  if (err instanceof ProblemDetailsError) {
    const isUnavailable =
      err.status === 403 &&
      (err.problem.type.includes('edition-unavailable') ||
        err.problem.detail.toLowerCase().includes('not enabled'));
    return { isUnavailable, detail: err.problem.detail, problem: err.problem };
  }

  if (err && typeof err === 'object') {
    const problem = (err as { problem?: ProblemDetails }).problem;
    if (problem) {
      const isUnavailable =
        problem.status === 403 &&
        (problem.type?.includes('edition-unavailable') ||
          problem.detail?.toLowerCase().includes('not enabled'));
      return { isUnavailable, detail: problem.detail, problem };
    }
    if ('status' in err && (err as { status: number }).status === 403) {
      return {
        isUnavailable: true,
        problem: {
          type: 'edition-unavailable',
          title: 'Forbidden',
          status: 403,
          detail: 'Public library edition is unavailable.',
          instance: '/public-library',
          request_id: 'local-fallback',
        },
      };
    }
  }

  return {
    isUnavailable: false,
    problem: {
      type: 'https://openlibraryos.example/problems/client-error',
      title: 'Request Failed',
      status: 500,
      detail: err instanceof Error ? err.message : 'An unexpected error occurred while communicating with the server.',
      instance: '/public-library',
      request_id: 'local-err',
    },
  };
}

export function PublicLibraryWorkspace({
  initialTab = 'memberships',
  className,
  style,
}: PublicLibraryWorkspaceProps) {
  const tokens = useTokens();
  const [activeTab, setActiveTab] = useState<PublicLibraryTab>(initialTab);
  const [isEditionUnavailable, setIsEditionUnavailable] = useState(false);
  const [unavailableDetail, setUnavailableDetail] = useState<string | undefined>();
  const [problemDetails, setProblemDetails] = useState<ProblemDetails | null>(null);
  const [initialLoadError, setInitialLoadError] = useState<ProblemDetails | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [members, setMembers] = useState<PublicLibraryMember[]>([]);
  const [plans, setPlans] = useState<PublicLibraryMembershipPlan[]>([]);
  const [subscriptions, setSubscriptions] = useState<PublicLibrarySubscription[]>([]);
  const [fines, setFines] = useState<PublicLibraryFine[]>([]);
  const [invoices, setInvoices] = useState<PublicLibraryInvoice[]>([]);
  const [payments, setPayments] = useState<PublicLibraryPayment[]>([]);

  const tabListRef = useRef<HTMLDivElement>(null);

  const handleError = useCallback((err: unknown) => {
    const parsed = parseProblem(err);
    if (parsed.isUnavailable) {
      setIsEditionUnavailable(true);
      setUnavailableDetail(parsed.detail);
      return;
    }
    setProblemDetails(parsed.problem);
  }, []);

  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setInitialLoadError(null);
    setProblemDetails(null);
    try {
      const [membersRes, plansRes, subsRes, finesRes, invoicesRes, paymentsRes] = await Promise.all([
        apiClient.publicLibrary.members.list(undefined, { token }),
        apiClient.publicLibrary.plans.list({ token }),
        apiClient.publicLibrary.subscriptions.list(undefined, { token }),
        apiClient.publicLibrary.fines.list(undefined, { token }),
        apiClient.publicLibrary.invoices.list(undefined, { token }),
        apiClient.publicLibrary.payments.list(undefined, { token }),
      ]);

      setMembers(membersRes.items);
      setPlans(plansRes.items);
      setSubscriptions(subsRes.items);
      setFines(finesRes.items);
      setInvoices(invoicesRes.items);
      setPayments(paymentsRes.items);
    } catch (err) {
      const parsed = parseProblem(err);
      if (parsed.isUnavailable) {
        setIsEditionUnavailable(true);
        setUnavailableDetail(parsed.detail);
        return;
      }
      setInitialLoadError(parsed.problem);
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Keyboard navigation for accessible tabs
  function handleKeyDown(e: React.KeyboardEvent, currentTab: PublicLibraryTab) {
    const tabs: PublicLibraryTab[] = ['memberships', 'fines', 'invoices', 'payments'];
    const idx = tabs.indexOf(currentTab);
    let nextIdx = idx;

    if (e.key === 'ArrowRight') {
      nextIdx = (idx + 1) % tabs.length;
    } else if (e.key === 'ArrowLeft') {
      nextIdx = (idx - 1 + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      nextIdx = 0;
    } else if (e.key === 'End') {
      nextIdx = tabs.length - 1;
    } else {
      return;
    }

    e.preventDefault();
    const targetTab = tabs[nextIdx];
    if (targetTab) {
      setActiveTab(targetTab);
    }
    const buttons = tabListRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[nextIdx]?.focus();
  }

  if (isEditionUnavailable) {
    return <EditionUnavailableState detail={unavailableDetail} className={className} style={style} />;
  }

  const outerRadius = 12;
  const paddingVal = 24;
  calcNestedRadius(outerRadius, paddingVal);

  const tabs: Array<{ id: PublicLibraryTab; label: string; count?: number }> = [
    { id: 'memberships', label: 'Memberships & Plans', count: members.length },
    { id: 'fines', label: 'Fines', count: fines.length },
    { id: 'invoices', label: 'Invoices', count: invoices.length },
    { id: 'payments', label: 'Payments', count: payments.length },
  ];

  return (
    <div
      className={className}
      style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: `${tokens.spacing.xl} ${tokens.spacing.lg}`,
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.xl,
        ...style,
      }}
    >
      {/* Page Header */}
      <div>
        <h2
          style={{
            margin: `0 0 ${tokens.spacing.xs} 0`,
            fontSize: tokens.typography.fontSizes['2xl'],
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
          }}
        >
          Public Library & Finance
        </h2>
        <p
          style={{
            margin: 0,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
          }}
        >
          Public membership plans, subscription policies, fine assessments, invoices, and safe payment tracking.
        </p>
      </div>

      {/* Accessible Tab Navigation (hidden on initial load failure) */}
      {!initialLoadError && (
        <div
          ref={tabListRef}
          role="tablist"
          aria-label="Public Library Workspaces"
          style={{
            display: 'flex',
            gap: tokens.spacing.xs,
            borderBottom: `1px solid ${tokens.colors.border}`,
            overflowX: 'auto',
          }}
        >
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={isActive}
                aria-controls={`panel-${tab.id}`}
                tabIndex={isActive ? 0 : -1}
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(e) => handleKeyDown(e, tab.id)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: tokens.spacing.sm,
                  padding: `${tokens.spacing.sm} ${tokens.spacing.lg}`,
                  fontSize: tokens.typography.fontSizes.sm,
                  fontWeight: isActive
                    ? tokens.typography.fontWeights.semibold
                    : tokens.typography.fontWeights.medium,
                  color: isActive ? tokens.colors.primary : tokens.colors.textSecondary,
                  backgroundColor: 'transparent',
                  border: 'none',
                  borderBottom: isActive
                    ? `2px solid ${tokens.colors.primary}`
                    : '2px solid transparent',
                  marginBottom: '-1px',
                  cursor: 'pointer',
                  borderRadius: `${tokens.radius.sm} ${tokens.radius.sm} 0 0`,
                  outline: 'none',
                  whiteSpace: 'nowrap',
                }}
              >
                <span>{tab.label}</span>
                {!isLoading && !problemDetails && tab.count !== undefined && (
                  <span
                    style={{
                      fontSize: tokens.typography.fontSizes.xs,
                      padding: '2px 6px',
                      borderRadius: tokens.radius.full,
                      backgroundColor: isActive
                        ? tokens.colors.surfaceElevated
                        : tokens.colors.surfaceAlt,
                      color: tokens.colors.textSecondary,
                    }}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Main Content Area */}
      {isLoading ? (
        <LoadingSkeleton lines={3} />
      ) : initialLoadError ? (
        <ProblemDetailsRenderer
          error={initialLoadError}
          isSafeToRetry={true}
          onRetry={loadData}
        />
      ) : (
        <div>
          {/* Action-level Problem Details Banner */}
          {problemDetails && <ProblemDetailsRenderer error={problemDetails} />}

          <div
            role="tabpanel"
            id="panel-memberships"
            aria-labelledby="tab-memberships"
            hidden={activeTab !== 'memberships'}
          >
            {activeTab === 'memberships' && (
              <MembershipSummaryView
                members={members}
                plans={plans}
                subscriptions={subscriptions}
                isLoading={isLoading}
                onRefresh={loadData}
                onError={handleError}
              />
            )}
          </div>

          <div
            role="tabpanel"
            id="panel-fines"
            aria-labelledby="tab-fines"
            hidden={activeTab !== 'fines'}
          >
            {activeTab === 'fines' && (
              <FinesView
                fines={fines}
                isLoading={isLoading}
                onRefresh={loadData}
                onError={handleError}
              />
            )}
          </div>

          <div
            role="tabpanel"
            id="panel-invoices"
            aria-labelledby="tab-invoices"
            hidden={activeTab !== 'invoices'}
          >
            {activeTab === 'invoices' && (
              <InvoicesView
                invoices={invoices}
                isLoading={isLoading}
                onRefresh={loadData}
                onError={handleError}
              />
            )}
          </div>

          <div
            role="tabpanel"
            id="panel-payments"
            aria-labelledby="tab-payments"
            hidden={activeTab !== 'payments'}
          >
            {activeTab === 'payments' && (
              <PaymentsView
                payments={payments}
                isLoading={isLoading}
                onRefresh={loadData}
                onError={handleError}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
