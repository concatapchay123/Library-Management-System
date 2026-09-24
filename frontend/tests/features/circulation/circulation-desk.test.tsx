import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TokenProvider } from '../../../src/shared/tokens';
import { SessionProvider } from '../../../src/features/auth';
import { CirculationDesk } from '../../../src/features/circulation';
import { App } from '../../../src/app/App';
import { Loan, ProblemDetails } from '../../../src/shared/api';

const mockRequestedLoan: Loan = {
  loan_id: 'l1111111-1111-4111-8111-111111111111',
  organization_id: 'org-test-001',
  copy_id: 'c1111111-1111-4111-8111-111111111111',
  borrower_user_id: 'u1111111-1111-4111-8111-111111111111',
  status: 'requested',
  requested_at: '2026-03-24T09:00:00Z',
  approved_at: null,
  checked_out_at: null,
  due_at: null,
  returned_at: null,
  created_at: '2026-03-24T09:00:00Z',
  updated_at: '2026-03-24T09:00:00Z',
};

const mockApprovedLoan: Loan = {
  ...mockRequestedLoan,
  loan_id: 'l2222222-2222-4222-8222-222222222222',
  status: 'approved',
  approved_at: '2026-03-24T10:00:00Z',
  updated_at: '2026-03-24T10:00:00Z',
};

const mockCheckedOutLoan: Loan = {
  ...mockApprovedLoan,
  loan_id: 'l3333333-3333-4333-8333-333333333333',
  status: 'checked_out',
  checked_out_at: '2026-03-24T11:00:00Z',
  due_at: '2026-04-07T11:00:00Z',
  updated_at: '2026-03-24T11:00:00Z',
};

const mockReturnedLoan: Loan = {
  ...mockCheckedOutLoan,
  status: 'returned',
  returned_at: '2026-03-24T14:30:00Z',
  updated_at: '2026-03-24T14:30:00Z',
};

const mockOverdueLoan: Loan = {
  ...mockCheckedOutLoan,
  loan_id: 'l4444444-4444-4444-8444-444444444444',
  status: 'overdue',
  due_at: '2026-03-20T11:00:00Z',
  updated_at: '2026-03-24T11:00:00Z',
};

function renderCirculationDesk(props: { initialLoan?: Loan } = {}) {
  return render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-circulation-token">
        <CirculationDesk initialLoan={props.initialLoan} />
      </SessionProvider>
    </TokenProvider>,
  );
}

describe('Circulation Desk for Request, Approval, Checkout and Return (FE-007)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Self-Service and Staff Loan Request Flow', () => {
    it('creates a loan request and renders request result in operation-result view', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-request-001',
        }),
        json: async () => mockRequestedLoan,
      } as Response);

      renderCirculationDesk();

      // Switch to Request tab
      const requestTab = screen.getByRole('tab', { name: /Loan Request/i });
      fireEvent.click(requestTab);

      // Enter copy and borrower UUIDs
      const copyInput = screen.getByLabelText(/Physical Copy ID/i);
      const borrowerInput = screen.getByLabelText(/Borrower User ID/i);
      fireEvent.change(copyInput, { target: { value: mockRequestedLoan.copy_id } });
      fireEvent.change(borrowerInput, { target: { value: mockRequestedLoan.borrower_user_id } });

      // Exactly 1 primary CTA
      const submitBtn = screen.getByRole('button', { name: /Submit Loan Request/i });
      expect(submitBtn).toHaveAttribute('data-variant', 'primary');

      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/v1/loans'),
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining(mockRequestedLoan.copy_id),
          }),
        );
      });

      // Verify Operation Result View shows loan request with distinct user language
      await waitFor(() => {
        expect(screen.getByText(/Loan Request Created/i)).toBeInTheDocument();
        expect(screen.getByText(mockRequestedLoan.loan_id)).toBeInTheDocument();
        expect(screen.getByTestId('loan-status-badge')).toHaveTextContent(/requested/i);
      });
    });
  });

  describe('Staff Approval Flow & Permitted Actions', () => {
    it('presents requested loan with only server-permitted actions: approve (primary) and reject (secondary)', async () => {
      renderCirculationDesk({ initialLoan: mockRequestedLoan });

      // Primary action must be Approve
      const approveBtn = screen.getByRole('button', { name: /Approve Loan/i });
      expect(approveBtn).toHaveAttribute('data-variant', 'primary');

      // Secondary action is Reject
      const rejectBtn = screen.getByRole('button', { name: /Reject Loan/i });
      expect(rejectBtn).toHaveAttribute('data-variant', 'secondary');

      // Checkout and Return buttons must NOT be present
      expect(screen.queryByRole('button', { name: /Complete Checkout/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Process Return/i })).not.toBeInTheDocument();
    });

    it('approves a requested loan and updates state to approved', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-approve-001',
        }),
        json: async () => mockApprovedLoan,
      } as Response);

      renderCirculationDesk({ initialLoan: mockRequestedLoan });

      const approveBtn = screen.getByRole('button', { name: /Approve Loan/i });
      fireEvent.click(approveBtn);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          expect.stringContaining(`/api/v1/loans/${mockRequestedLoan.loan_id}/approve`),
          expect.objectContaining({
            method: 'POST',
          }),
        );
      });

      await waitFor(() => {
        expect(screen.getByText(/Loan Approved/i)).toBeInTheDocument();
        expect(screen.getByTestId('loan-status-badge')).toHaveTextContent(/approved/i);
      });
    });

    it('rejects a requested loan with reason and moves to terminal rejected state', async () => {
      const mockRejectedLoan: Loan = {
        ...mockRequestedLoan,
        status: 'rejected',
        updated_at: '2026-03-24T10:05:00Z',
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-reject-001',
        }),
        json: async () => mockRejectedLoan,
      } as Response);

      renderCirculationDesk({ initialLoan: mockRequestedLoan });

      const rejectBtn = screen.getByRole('button', { name: /Reject Loan/i });
      fireEvent.click(rejectBtn);

      // Dialog opens for rejection reason
      const reasonInput = screen.getByLabelText(/Rejection Reason/i);
      fireEvent.change(reasonInput, { target: { value: 'Patron has overdue loans.' } });

      const confirmRejectBtn = screen.getByRole('button', { name: /Confirm Rejection/i });
      fireEvent.click(confirmRejectBtn);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          expect.stringContaining(`/api/v1/loans/${mockRequestedLoan.loan_id}/reject`),
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('Patron has overdue loans.'),
          }),
        );
      });

      await waitFor(() => {
        expect(screen.getByText(/Loan Rejected/i)).toBeInTheDocument();
      });
    });
  });

  describe('Evidence Checkpoint 1: Checkout Conflict Preserves State & Explains Next Safe Action', () => {
    it('preserves displayed state and explains next safe action on 409 conflict during checkout', async () => {
      const conflictProblem: ProblemDetails = {
        type: 'https://openlibraryos.example/problems/copy-not-available',
        title: 'Copy not available',
        status: 409,
        detail: `Copy ${mockApprovedLoan.copy_id} is in status 'borrowed' and cannot be borrowed.`,
        instance: `/api/v1/loans/${mockApprovedLoan.loan_id}/checkout`,
        request_id: 'req-conflict-409',
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: new Headers({
          'Content-Type': 'application/problem+json',
          'X-Request-ID': 'req-conflict-409',
        }),
        json: async () => conflictProblem,
      } as Response);

      renderCirculationDesk({ initialLoan: mockApprovedLoan });

      // Verify approved loan is currently displayed
      expect(screen.getByText(mockApprovedLoan.loan_id)).toBeInTheDocument();
      expect(screen.getByTestId('loan-status-badge')).toHaveTextContent(/approved/i);

      // Click Complete Checkout
      const checkoutBtn = screen.getByRole('button', { name: /Complete Checkout/i });
      expect(checkoutBtn).toHaveAttribute('data-variant', 'primary');
      fireEvent.click(checkoutBtn);

      // Verify conflict error is rendered
      await waitFor(() => {
        expect(screen.getByText('Copy not available')).toBeInTheDocument();
        expect(
          screen.getByText(
            new RegExp(`Copy ${mockApprovedLoan.copy_id} is in status 'borrowed'`, 'i'),
          ),
        ).toBeInTheDocument();
      });

      // INVARIANT CHECKPOINT: Loan state is preserved, NOT reset or cleared
      expect(screen.getByText(mockApprovedLoan.loan_id)).toBeInTheDocument();
      expect(screen.getByText(mockApprovedLoan.copy_id)).toBeInTheDocument();
      expect(screen.getByText(mockApprovedLoan.borrower_user_id)).toBeInTheDocument();

      // INVARIANT CHECKPOINT: Explains the next safe action
      expect(
        screen.getByText(/Next safe action:/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Verify physical copy on shelf or re-assign copy before proceeding/i),
      ).toBeInTheDocument();
    });

    it('preserves desk checkout form inputs on 409 conflict and explains safe resolution', async () => {
      const conflictProblem: ProblemDetails = {
        type: 'https://openlibraryos.example/problems/loan-not-eligible',
        title: 'Loan request rejected',
        status: 409,
        detail: 'The borrower has reached the active loan limit.',
        instance: '/api/v1/loans/desk-checkout',
        request_id: 'req-conflict-desk-409',
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: new Headers({
          'Content-Type': 'application/problem+json',
          'X-Request-ID': 'req-conflict-desk-409',
        }),
        json: async () => conflictProblem,
      } as Response);

      renderCirculationDesk();

      // Desk Checkout tab is active by default
      const copyInput = screen.getByLabelText(/Physical Copy ID/i);
      const borrowerInput = screen.getByLabelText(/Borrower User ID/i);
      fireEvent.change(copyInput, { target: { value: 'c9999999-9999-4999-8999-999999999999' } });
      fireEvent.change(borrowerInput, { target: { value: 'u8888888-8888-4888-8888-888888888888' } });

      const checkoutBtn = screen.getByRole('button', { name: /Direct Desk Checkout/i });
      fireEvent.click(checkoutBtn);

      await waitFor(() => {
        expect(screen.getByText('Loan request rejected')).toBeInTheDocument();
        expect(screen.getByText('The borrower has reached the active loan limit.')).toBeInTheDocument();
      });

      // Form inputs are preserved
      expect(copyInput).toHaveValue('c9999999-9999-4999-8999-999999999999');
      expect(borrowerInput).toHaveValue('u8888888-8888-4888-8888-888888888888');

      // Next safe action guidance is visible
      expect(screen.getByText(/Next safe action:/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Review borrower loan count or return outstanding items first/i),
      ).toBeInTheDocument();
    });
  });

  describe('Evidence Checkpoint 2: Repeat Click Behavior & Idempotency Key Handling', () => {
    it('disables mutation button during in-flight request and passes Idempotency-Key header', async () => {
      let resolvePromise: (value: Response) => void;
      const inFlightPromise = new Promise<Response>((resolve) => {
        resolvePromise = resolve;
      });

      vi.mocked(fetch).mockReturnValueOnce(inFlightPromise);

      renderCirculationDesk({ initialLoan: mockApprovedLoan });

      const checkoutBtn = screen.getByRole('button', { name: /Complete Checkout/i });
      fireEvent.click(checkoutBtn);

      // Button is immediately disabled during in-flight submission
      expect(checkoutBtn).toBeDisabled();

      // Repeated click while in flight does not trigger second fetch call
      fireEvent.click(checkoutBtn);
      expect(fetch).toHaveBeenCalledTimes(1);

      // Verify Idempotency-Key header was sent
      const callArgs = vi.mocked(fetch).mock.calls[0];
      const headers = callArgs?.[1]?.headers as Record<string, string>;
      expect(headers).toBeDefined();
      expect(headers['Idempotency-Key']).toBeTruthy();
      expect(headers['Idempotency-Key']?.length).toBeGreaterThan(0);

      // Complete the request
      resolvePromise!({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-checkout-success',
        }),
        json: async () => mockCheckedOutLoan,
      } as Response);

      await waitFor(() => {
        expect(screen.getByText(/Loan Checked Out/i)).toBeInTheDocument();
      });

      // INVARIANT: Exactly one completed operation result card is visible
      const resultHeadings = screen.getAllByRole('heading', { name: /Loan Checked Out/i });
      expect(resultHeadings).toHaveLength(1);
    });

    it('handles idempotent replay response with Idempotency-Replayed header safely', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-replay-001',
          'Idempotency-Replayed': 'true',
        }),
        json: async () => mockCheckedOutLoan,
      } as Response);

      renderCirculationDesk({ initialLoan: mockApprovedLoan });

      const checkoutBtn = screen.getByRole('button', { name: /Complete Checkout/i });
      fireEvent.click(checkoutBtn);

      await waitFor(() => {
        expect(screen.getByText(/Loan Checked Out/i)).toBeInTheDocument();
      });

      // Verify only 1 result is visible and no second duplicate state is rendered
      expect(screen.getAllByText(mockCheckedOutLoan.loan_id)).toHaveLength(1);
    });
  });

  describe('Return Success Flow', () => {
    it('presents checked out loan with Process Return as only permitted primary action', async () => {
      renderCirculationDesk({ initialLoan: mockCheckedOutLoan });

      // Process Return is the ONLY primary action
      const returnBtn = screen.getByRole('button', { name: /Process Return/i });
      expect(returnBtn).toHaveAttribute('data-variant', 'primary');

      // Approve, Checkout, Request must NOT be present
      expect(screen.queryByRole('button', { name: /Approve Loan/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Complete Checkout/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Submit Loan Request/i })).not.toBeInTheDocument();
    });

    it('returns checked out book, updating copy to available and displaying server returned timestamp', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-return-001',
        }),
        json: async () => mockReturnedLoan,
      } as Response);

      renderCirculationDesk({ initialLoan: mockCheckedOutLoan });

      const returnBtn = screen.getByRole('button', { name: /Process Return/i });
      fireEvent.click(returnBtn);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          expect.stringContaining(`/api/v1/loans/${mockCheckedOutLoan.loan_id}/return`),
          expect.objectContaining({
            method: 'POST',
          }),
        );
      });

      await waitFor(() => {
        expect(screen.getByText(/Book Returned Successfully/i)).toBeInTheDocument();
        expect(screen.getByTestId('loan-status-badge')).toHaveTextContent(/returned/i);
      });
    });

    it('supports returning an overdue loan', async () => {
      const mockReturnedFromOverdue: Loan = {
        ...mockOverdueLoan,
        status: 'returned',
        returned_at: '2026-03-24T15:00:00Z',
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-return-overdue',
        }),
        json: async () => mockReturnedFromOverdue,
      } as Response);

      renderCirculationDesk({ initialLoan: mockOverdueLoan });

      expect(screen.getByText(/Overdue/i)).toBeInTheDocument();
      const returnBtn = screen.getByRole('button', { name: /Process Return/i });
      expect(returnBtn).toHaveAttribute('data-variant', 'primary');

      fireEvent.click(returnBtn);

      await waitFor(() => {
        expect(screen.getByText(/Book Returned Successfully/i)).toBeInTheDocument();
      });
    });
  });

  describe('Acceptance Criteria Invariants', () => {
    it('strictly renders one visually primary action at a time per workflow panel', () => {
      // 1. Requested loan: only Approve is primary
      const { unmount: unmount1 } = renderCirculationDesk({ initialLoan: mockRequestedLoan });
      const primaryButtons1 = screen
        .getAllByRole('button')
        .filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryButtons1).toHaveLength(1);
      expect(primaryButtons1[0]).toHaveTextContent(/Approve Loan/i);
      unmount1();

      // 2. Approved loan: only Complete Checkout is primary
      const { unmount: unmount2 } = renderCirculationDesk({ initialLoan: mockApprovedLoan });
      const primaryButtons2 = screen
        .getAllByRole('button')
        .filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryButtons2).toHaveLength(1);
      expect(primaryButtons2[0]).toHaveTextContent(/Complete Checkout/i);
      unmount2();

      // 3. Checked out loan: only Process Return is primary
      const { unmount: unmount3 } = renderCirculationDesk({ initialLoan: mockCheckedOutLoan });
      const primaryButtons3 = screen
        .getAllByRole('button')
        .filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryButtons3).toHaveLength(1);
      expect(primaryButtons3[0]).toHaveTextContent(/Process Return/i);
      unmount3();

      // 4. Desk Checkout form: only Direct Desk Checkout is primary
      const { unmount: unmount4 } = renderCirculationDesk();
      const primaryButtons4 = screen
        .getAllByRole('button')
        .filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryButtons4).toHaveLength(1);
      expect(primaryButtons4[0]).toHaveTextContent(/Direct Desk Checkout/i);
      unmount4();
    });

    it('displays server-provided due date without client-side calculation or eligibility overrides', async () => {
      // Server returned due date exactly: '2026-04-07T11:00:00Z'
      renderCirculationDesk({ initialLoan: mockCheckedOutLoan });

      // Verifies server due date is displayed
      expect(screen.getByText(/Due Date:/i)).toBeInTheDocument();
      expect(screen.getByText(/2026-04-07/i)).toBeInTheDocument();

      // Invariant: no client-computed eligibility or due date formulas
      const desk = screen.getByTestId('circulation-desk');
      expect(desk).not.toHaveTextContent(/14 days/i);
    });

    it('renders terminal status for completed loans without mutation actions', () => {
      renderCirculationDesk({ initialLoan: mockReturnedLoan });

      // Shows Returned status
      expect(screen.getByTestId('loan-status-badge')).toHaveTextContent(/returned/i);
      expect(
        screen.getByText(/This loan has reached its final state and cannot undergo further lifecycle mutations/i),
      ).toBeInTheDocument();

      // Zero primary mutation actions
      const primaryButtons = screen
        .queryAllByRole('button')
        .filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryButtons).toHaveLength(0);
    });
  });

  describe('Integration with Authorized App Shell', () => {
    it('mounts CirculationDesk when navigation tab is circulation', async () => {
      render(
        <TokenProvider>
          <App initialAuthenticated={true} />
        </TokenProvider>,
      );

      // Circulation is the default desk tab
      expect(screen.getByTestId('circulation-desk')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /Circulation Desk/i })).toBeInTheDocument();
    });
  });
});
