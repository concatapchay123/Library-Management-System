import { useState, useContext, FormEvent } from 'react';
import { useTokens } from '../../shared/tokens';
import {
  Loan,
  ProblemDetails,
  apiClient,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import {
  Button,
  Input,
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { CirculationDeskProps, CirculationTab } from './types';
import { DeskCheckoutPanel } from './DeskCheckoutPanel';
import { LoanRequestPanel } from './LoanRequestPanel';
import { LoanLifecycleActions } from './LoanLifecycleActions';
import { OperationResultView } from './OperationResultView';

/**
 * Core Circulation Desk Workspace (FE-007).
 *
 * Implements low-step staff circulation workflows for request, approval,
 * checkout, and return.
 *
 * Key Architecture & UI Invariants:
 * - One lifecycle action is visually primary at a time.
 * - User language clearly distinguishes request, approval, checkout, and return.
 * - UI strictly relies on server responses and does not calculate eligibility, due dates, or copy locks.
 * - Idempotency keys are safely generated and attached to checkout and return mutations.
 * - Conflict errors preserve the displayed state and explain the next safe action.
 */
export function CirculationDesk({
  initialLoan,
  initialTab = 'desk-checkout',
}: CirculationDeskProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [activeTab, setActiveTab] = useState<CirculationTab>(() => {
    if (initialLoan) return 'manage-loan';
    return initialTab;
  });

  const [currentLoan, setCurrentLoan] = useState<Loan | null>(initialLoan ?? null);
  const [lastCompletedOperation, setLastCompletedOperation] = useState<Loan | null>(null);

  // Loan lookup form state
  const [lookupLoanId, setLookupLoanId] = useState('');
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [lookupError, setLookupError] = useState<ProblemDetails | Error | null>(null);

  const handleLookupLoan = async (e: FormEvent) => {
    e.preventDefault();
    if (!lookupLoanId.trim() || isLookingUp) return;

    setIsLookingUp(true);
    setLookupError(null);
    try {
      const loan = await apiClient.loans.getById(lookupLoanId.trim(), { token });
      setCurrentLoan(loan);
      setLastCompletedOperation(null);
    } catch (err) {
      setLookupError(err as ProblemDetails | Error);
    } finally {
      setIsLookingUp(false);
    }
  };

  const handleOperationSuccess = (loan: Loan) => {
    setCurrentLoan(loan);
    setLastCompletedOperation(loan);
    setActiveTab('manage-loan');
  };

  return (
    <div
      data-testid="circulation-desk"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.semantic.groupToGroup,
        maxWidth: '780px',
      }}
    >
      {/* Header and Operational Status Cue */}
      {!lookupError ? (
        <StatusMessage status="info" title="Operational Status: Ready">
          Circulation subsystem active for rapid loan requests, approvals, desk checkouts, and returns.
        </StatusMessage>
      ) : (
        <StatusMessage status="warning" title="Operational Status: Attention Required">
          A circulation lookup or operational request encountered an issue. Review the diagnostic details below.
        </StatusMessage>
      )}

      <div>
        <h2
          style={{
            margin: 0,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes['2xl'],
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
          }}
        >
          Circulation Desk
        </h2>
        <p
          style={{
            margin: 0,
            marginTop: tokens.spacing.xs,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
          }}
        >
          Rapid circulation desk: manage patron requests, staff approvals, physical copy checkout, and book check-in.
        </p>
      </div>

      {/* Desk Navigation Tabs */}
      <div
        role="tablist"
        aria-label="Circulation desk workflow selection"
        style={{
          display: 'flex',
          gap: tokens.spacing.xs,
          backgroundColor: tokens.colors.surfaceAlt,
          padding: tokens.spacing.xs,
          borderRadius: tokens.radius.lg,
          border: `1px solid ${tokens.colors.border}`,
          overflowX: 'auto',
        }}
      >
        <button
          type="button"
          role="tab"
          id="tab-desk-checkout"
          aria-selected={activeTab === 'desk-checkout'}
          aria-controls="panel-desk-checkout"
          onClick={() => {
            setActiveTab('desk-checkout');
            setLastCompletedOperation(null);
          }}
          style={{
            padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
            borderRadius: tokens.radius.md,
            border: 'none',
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            fontWeight:
              activeTab === 'desk-checkout'
                ? tokens.typography.fontWeights.semibold
                : tokens.typography.fontWeights.normal,
            backgroundColor: activeTab === 'desk-checkout' ? tokens.colors.surface : 'transparent',
            color: activeTab === 'desk-checkout' ? tokens.colors.textPrimary : tokens.colors.textSecondary,
            boxShadow: activeTab === 'desk-checkout' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Direct Desk Checkout
        </button>

        <button
          type="button"
          role="tab"
          id="tab-loan-request"
          aria-selected={activeTab === 'loan-request'}
          aria-controls="panel-loan-request"
          onClick={() => {
            setActiveTab('loan-request');
            setLastCompletedOperation(null);
          }}
          style={{
            padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
            borderRadius: tokens.radius.md,
            border: 'none',
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            fontWeight:
              activeTab === 'loan-request'
                ? tokens.typography.fontWeights.semibold
                : tokens.typography.fontWeights.normal,
            backgroundColor: activeTab === 'loan-request' ? tokens.colors.surface : 'transparent',
            color: activeTab === 'loan-request' ? tokens.colors.textPrimary : tokens.colors.textSecondary,
            boxShadow: activeTab === 'loan-request' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Loan Request
        </button>

        <button
          type="button"
          role="tab"
          id="tab-manage-loan"
          aria-selected={activeTab === 'manage-loan'}
          aria-controls="panel-manage-loan"
          onClick={() => setActiveTab('manage-loan')}
          style={{
            padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
            borderRadius: tokens.radius.md,
            border: 'none',
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            fontWeight:
              activeTab === 'manage-loan'
                ? tokens.typography.fontWeights.semibold
                : tokens.typography.fontWeights.normal,
            backgroundColor: activeTab === 'manage-loan' ? tokens.colors.surface : 'transparent',
            color: activeTab === 'manage-loan' ? tokens.colors.textPrimary : tokens.colors.textSecondary,
            boxShadow: activeTab === 'manage-loan' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Lookup & Manage Loan
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'desk-checkout' && (
        <div id="panel-desk-checkout" role="tabpanel" aria-labelledby="tab-desk-checkout">
          <DeskCheckoutPanel onSuccess={handleOperationSuccess} />
        </div>
      )}

      {activeTab === 'loan-request' && (
        <div id="panel-loan-request" role="tabpanel" aria-labelledby="tab-loan-request">
          <LoanRequestPanel onSuccess={handleOperationSuccess} />
        </div>
      )}

      {activeTab === 'manage-loan' && (
        <div
          id="panel-manage-loan"
          role="tabpanel"
          aria-labelledby="tab-manage-loan"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.semantic.groupToGroup,
          }}
        >
          {/* Lookup Input Form when no loan is loaded or to lookup a different loan */}
          <div
            style={{
              backgroundColor: tokens.colors.surfaceAlt,
              borderRadius: tokens.radius.xl,
              border: `1px solid ${tokens.colors.border}`,
              padding: tokens.spacing.xl,
              boxSizing: 'border-box',
            }}
          >
            <h3
              style={{
                margin: 0,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xl,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              Loan Identifier Lookup
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
              Enter a loan UUID to inspect its current status and perform authorized transitions.
            </p>

            {lookupError && (
              <div style={{ marginTop: tokens.spacing.md }}>
                <ProblemDetailsRenderer error={lookupError} />
              </div>
            )}

            <form
              onSubmit={handleLookupLoan}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: tokens.spacing.semantic.groupToGroup,
                marginTop: tokens.spacing.md,
              }}
            >
              <Input
                id="lookup-loan-id"
                label="Loan Identifier (UUID)"
                description="Scan barcode on circulation receipt or enter 36-character UUID."
                placeholder="e.g. l1111111-1111-4111-8111-111111111111"
                value={lookupLoanId}
                onChange={(e) => setLookupLoanId(e.target.value)}
                disabled={isLookingUp}
              />

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: tokens.spacing.md,
                  marginTop: tokens.spacing.sm,
                  paddingTop: tokens.spacing.md,
                  borderTop: `1px solid ${tokens.colors.borderMuted}`,
                }}
              >
                {/* Lookup is a secondary action, preserving exactly 1 primary action for lifecycle transitions */}
                <Button
                  type="submit"
                  variant="secondary"
                  size="md"
                  disabled={isLookingUp}
                >
                  {isLookingUp ? 'Searching...' : 'Find Loan Record'}
                </Button>
              </div>
            </form>
          </div>

          {/* Operation Result Banner if an operation was just performed */}
          {lastCompletedOperation && (
            <OperationResultView
              loan={lastCompletedOperation}
              onReset={() => setLastCompletedOperation(null)}
            />
          )}

          {/* Active Loan Lifecycle Actions */}
          {currentLoan && !lastCompletedOperation && (
            <LoanLifecycleActions
              loan={currentLoan}
              onLoanUpdated={(updated) => {
                setCurrentLoan(updated);
                setLastCompletedOperation(updated);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
