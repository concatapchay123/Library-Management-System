import { Loan, LoanStatus } from '../../shared/api';

export type CirculationTab = 'desk-checkout' | 'loan-request' | 'manage-loan';

export interface DeskCheckoutFormValues {
  copy_id: string;
  borrower_user_id: string;
  duration_days?: number;
}

export interface LoanRequestFormValues {
  copy_id: string;
  borrower_user_id?: string;
  duration_days?: number;
}

export interface CirculationDeskProps {
  initialLoan?: Loan;
  initialTab?: CirculationTab;
}

/**
 * Permitted next actions for each loan lifecycle status, strictly mirroring
 * the backend state machine policy in BE-016.
 */
export const PERMITTED_LOAN_ACTIONS: Record<LoanStatus, readonly string[]> = {
  requested: ['approve', 'reject'],
  approved: ['checkout'],
  checked_out: ['return'],
  overdue: ['return'],
  returned: [],
  rejected: [],
  cancelled: [],
};

/**
 * Maps problem types to domain-safe next action explanations.
 */
export function getNextSafeActionRecommendation(problemType?: string, detail?: string): string {
  if (!problemType && !detail) {
    return 'Review the error details above and verify input data before retrying.';
  }

  const typeLower = (problemType || '').toLowerCase();
  const detailLower = (detail || '').toLowerCase();

  if (typeLower.includes('copy-not-available') || detailLower.includes('cannot be borrowed')) {
    return 'Verify physical copy on shelf or re-assign copy before proceeding.';
  }
  if (typeLower.includes('loan-not-eligible') || detailLower.includes('active loan limit')) {
    return 'Review borrower loan count or return outstanding items first.';
  }
  if (typeLower.includes('invalid-loan-status-transition') || detailLower.includes('transition loan status')) {
    return 'Refresh loan state to verify current workflow status before taking further action.';
  }
  if (typeLower.includes('not-found') || detailLower.includes('not found')) {
    return 'Check the identifier for typos and verify that the record exists.';
  }

  return 'Review the error details above and verify input data before retrying.';
}

/**
 * Extracts problem type and detail message from ProblemDetailsError, raw ProblemDetails, or generic Error.
 */
export function extractProblemDetails(err: unknown): { type?: string; detail?: string } {
  if (!err) return {};
  if (typeof err === 'object') {
    const record = err as Record<string, unknown>;
    if (record.problem && typeof record.problem === 'object') {
      const p = record.problem as Record<string, unknown>;
      return {
        type: typeof p.type === 'string' ? p.type : undefined,
        detail:
          typeof p.detail === 'string'
            ? p.detail
            : typeof record.message === 'string'
              ? record.message
              : undefined,
      };
    }
    return {
      type: typeof record.type === 'string' ? record.type : undefined,
      detail:
        typeof record.detail === 'string'
          ? record.detail
          : typeof record.message === 'string'
            ? record.message
            : undefined,
    };
  }
  return {};
}
