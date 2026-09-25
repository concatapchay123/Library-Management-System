import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { TokenProvider } from '../../../src/shared/tokens';
import { SessionProvider } from '../../../src/features/auth';
import { PublicLibraryWorkspace } from '../../../src/features/public-library';
import {
  PublicLibraryMember,
  PublicLibraryMembershipPlan,
  PublicLibrarySubscription,
  PublicLibraryFine,
  PublicLibraryInvoice,
  PublicLibraryPayment,
} from '../../../src/shared/api';
import { App } from '../../../src/app/App';

const mockPlans: PublicLibraryMembershipPlan[] = [
  {
    plan_id: 'plan-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    code: 'BASIC',
    name: 'Basic Reader Plan',
    description: 'Standard borrower access for community members.',
    max_active_loans: 5,
    duration_days: 30,
    price: '0.0000',
    currency: 'USD',
    status: 'active',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  },
  {
    plan_id: 'plan-22222222-2222-4222-8222-222222222222',
    organization_id: 'org-test-001',
    code: 'PREMIUM',
    name: 'Premium Researcher Plan',
    description: 'Extended loan capacity and longer borrowing periods.',
    max_active_loans: 20,
    duration_days: 90,
    price: '45.0000',
    currency: 'USD',
    status: 'active',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  },
];

const mockMembers: PublicLibraryMember[] = [
  {
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    user_id: 'usr-11111111-1111-4111-8111-111111111111',
    member_number: 'PUB-2026-0001',
    status: 'active',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
  },
  {
    member_id: 'mem-22222222-2222-4222-8222-222222222222',
    organization_id: 'org-test-001',
    user_id: 'usr-22222222-2222-4222-8222-222222222222',
    member_number: 'PUB-2026-0002',
    status: 'suspended',
    created_at: '2026-09-02T11:00:00Z',
    updated_at: '2026-09-02T11:00:00Z',
  },
];

const mockSubscriptions: PublicLibrarySubscription[] = [
  {
    subscription_id: 'sub-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    plan_id: 'plan-22222222-2222-4222-8222-222222222222',
    starts_at: '2026-09-01T00:00:00Z',
    ends_at: '2027-09-01T00:00:00Z',
    status: 'active',
    created_at: '2026-09-01T10:05:00Z',
    updated_at: '2026-09-01T10:05:00Z',
  },
];

const mockFines: PublicLibraryFine[] = [
  {
    fine_id: 'fine-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    loan_id: 'loan-11111111-1111-4111-8111-111111111111',
    amount: '15.5000',
    currency: 'USD',
    status: 'assessed',
    reason: 'Overdue returned book (14 days overdue)',
    assessed_at: '2026-09-10T14:30:00Z',
    created_at: '2026-09-10T14:30:00Z',
    updated_at: '2026-09-10T14:30:00Z',
  },
  {
    fine_id: 'fine-22222222-2222-4222-8222-222222222222',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    loan_id: null,
    amount: '5.0000',
    currency: 'USD',
    status: 'waived',
    reason: 'Damaged barcode replacement',
    assessed_at: '2026-09-05T09:00:00Z',
    created_at: '2026-09-05T09:00:00Z',
    updated_at: '2026-09-06T10:00:00Z',
  },
];

const mockInvoices: PublicLibraryInvoice[] = [
  {
    invoice_id: 'inv-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    invoice_number: 'INV-2026-0001',
    subtotal: '45.0000',
    tax: '0.0000',
    total: '45.0000',
    currency: 'USD',
    status: 'issued',
    issued_at: '2026-09-01T10:10:00Z',
    due_at: '2026-09-15T00:00:00Z',
    created_at: '2026-09-01T10:10:00Z',
    updated_at: '2026-09-01T10:10:00Z',
    lines: [
      {
        invoice_line_id: 'line-11111111-1111-4111-8111-111111111111',
        organization_id: 'org-test-001',
        invoice_id: 'inv-11111111-1111-4111-8111-111111111111',
        line_number: 1,
        description: 'Premium Researcher Plan annual subscription',
        quantity: 1,
        unit_price: '45.0000',
        amount: '45.0000',
        fine_id: null,
        created_at: '2026-09-01T10:10:00Z',
      },
    ],
  },
];

const mockPayments: PublicLibraryPayment[] = [
  {
    payment_id: 'pay-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    amount: '45.0000',
    currency: 'USD',
    provider: 'stripe',
    status: 'pending',
    provider_reference: 'pi_3KjF892eZvKYlo2C01pending',
    provider_event_id: null,
    paid_at: null,
    created_at: '2026-09-01T10:12:00Z',
    updated_at: '2026-09-01T10:12:00Z',
  },
  {
    payment_id: 'pay-22222222-2222-4222-8222-222222222222',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    amount: '15.5000',
    currency: 'USD',
    provider: 'stripe',
    status: 'succeeded',
    provider_reference: 'pi_3KjF892eZvKYlo2C02settled',
    provider_event_id: 'evt_settled_002',
    paid_at: '2026-09-11T08:00:00Z',
    created_at: '2026-09-11T07:55:00Z',
    updated_at: '2026-09-11T08:00:00Z',
  },
  {
    payment_id: 'pay-33333333-3333-4333-8333-333333333333',
    organization_id: 'org-test-001',
    member_id: 'mem-22222222-2222-4222-8222-222222222222',
    amount: '20.0000',
    currency: 'USD',
    provider: 'mock_gateway',
    status: 'failed',
    provider_reference: 'pi_failed_003',
    provider_event_id: 'evt_failed_003',
    paid_at: null,
    created_at: '2026-09-12T09:00:00Z',
    updated_at: '2026-09-12T09:01:00Z',
  },
  {
    payment_id: 'pay-44444444-4444-4444-8444-444444444444',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    amount: '50.0000',
    currency: 'USD',
    provider: 'stripe',
    status: 'partially_refunded',
    provider_reference: 'pi_partref_004',
    provider_event_id: 'evt_partref_004',
    paid_at: '2026-09-05T10:00:00Z',
    created_at: '2026-09-05T09:50:00Z',
    updated_at: '2026-09-06T14:00:00Z',
  },
  {
    payment_id: 'pay-55555555-5555-4555-8555-555555555555',
    organization_id: 'org-test-001',
    member_id: 'mem-11111111-1111-4111-8111-111111111111',
    amount: '10.0000',
    currency: 'USD',
    provider: 'stripe',
    status: 'refunded',
    provider_reference: 'pi_refunded_005',
    provider_event_id: 'evt_refunded_005',
    paid_at: '2026-09-07T11:00:00Z',
    created_at: '2026-09-07T10:50:00Z',
    updated_at: '2026-09-08T12:00:00Z',
  },
];

function setupDefaultMocks() {
  vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;

    if (url.includes('/public-library/memberships') || url.includes('/public-library/membership-plans')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockPlans }),
      } as Response;
    }

    if (url.includes('/public-library/subscriptions')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockSubscriptions }),
      } as Response;
    }

    if (url.includes('/public-library/members')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockMembers }),
      } as Response;
    }

    if (url.includes('/public-library/fines')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockFines }),
      } as Response;
    }

    if (url.includes('/public-library/invoices')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockInvoices }),
      } as Response;
    }

    if (url.includes('/public-library/payments')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockPayments }),
      } as Response;
    }

    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: async () => ({ items: [] }),
    } as Response;
  });
}

function renderPublicLibraryWorkspace(props: { initialTab?: 'memberships' | 'fines' | 'invoices' | 'payments' } = {}) {
  return render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-public-library-token">
        <PublicLibraryWorkspace initialTab={props.initialTab} />
      </SessionProvider>
    </TokenProvider>,
  );
}

describe('Public membership, fine, payment and invoice views (FE-010)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Tab Navigation and Workspace Layout', () => {
    it('renders the public library workspace with accessible navigation tabs', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace();

      expect(screen.getByRole('heading', { level: 2, name: /public library & finance/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /memberships & plans/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /fines/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /invoices/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /payments/i })).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText('PUB-2026-0001')).toBeInTheDocument();
      });
    });

    it('switches between tabs and displays relevant section content', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace();

      await waitFor(() => {
        expect(screen.getByText('PUB-2026-0001')).toBeInTheDocument();
      });

      // Switch to Fines tab
      const finesTab = screen.getByRole('tab', { name: /fines/i });
      fireEvent.click(finesTab);

      await waitFor(() => {
        expect(screen.getByText(/overdue returned book/i)).toBeInTheDocument();
      });

      // Switch to Invoices tab
      const invoicesTab = screen.getByRole('tab', { name: /invoices/i });
      fireEvent.click(invoicesTab);

      await waitFor(() => {
        expect(screen.getByText('INV-2026-0001')).toBeInTheDocument();
      });

      // Switch to Payments tab
      const paymentsTab = screen.getByRole('tab', { name: /payments/i });
      fireEvent.click(paymentsTab);

      await waitFor(() => {
        expect(screen.getByText(/pi_3KjF892eZvKYlo2C01pending/i)).toBeInTheDocument();
      });
    });
  });

  describe('Memberships & Server-Provided Policy Summary', () => {
    it('renders member profile, status, and active plan subscription', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'memberships' });

      await waitFor(() => {
        expect(screen.getByText('PUB-2026-0001')).toBeInTheDocument();
        expect(screen.getByText('PUB-2026-0002')).toBeInTheDocument();
      });

      // Text and non-color cues for member status
      expect(screen.getByText(/● active/i)).toBeInTheDocument();
      expect(screen.getByText(/⊘ suspended/i)).toBeInTheDocument();

      // Displays subscribed plan name
      expect(screen.getByText('Premium Researcher Plan')).toBeInTheDocument();
    });

    it('renders server-provided borrowing policy summary in plain language without client-side entitlement math', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'memberships' });

      await waitFor(() => {
        expect(screen.getByText('PUB-2026-0001')).toBeInTheDocument();
      });

      // Displays borrowing limits supplied by server plan
      expect(screen.getByText(/20 active loans/i)).toBeInTheDocument();
      expect(screen.getByText(/90-day borrowing duration/i)).toBeInTheDocument();

      // Informs user that borrowing limits and eligibility are authoritatively decided by the server
      expect(
        screen.getByText(/borrowing policy is enforced authoritatively by the backend server/i),
      ).toBeInTheDocument();
    });
  });

  describe('Fine Records, Explicit Currency and Backend Waive Action', () => {
    it('displays fine records with explicit currency code and decimal precision', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'fines' });

      await waitFor(() => {
        expect(screen.getByText(/overdue returned book/i)).toBeInTheDocument();
      });

      // Explicit currency code and full decimal formatting retained
      expect(screen.getByText(/USD 15.5000/i)).toBeInTheDocument();
      expect(screen.getByText(/USD 5.0000/i)).toBeInTheDocument();

      // Status badges use text and non-color cues
      expect(screen.getByText(/● assessed/i)).toBeInTheDocument();
      expect(screen.getByText(/— waived/i)).toBeInTheDocument();
    });

    it('allows waiving an assessed fine through backend authorized action with reason', async () => {
      setupDefaultMocks();

      let waiveRequested = false;
      let waivePayload: unknown = null;

      vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/fines/fine-11111111-1111-4111-8111-111111111111/waive')) {
          waiveRequested = true;
          waivePayload = JSON.parse(init?.body as string);
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({
              ...mockFines[0],
              status: 'waived',
            }),
          } as Response;
        }

        if (url.includes('/fines')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockFines }),
          } as Response;
        }

        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderPublicLibraryWorkspace({ initialTab: 'fines' });

      await waitFor(() => {
        expect(screen.getByText(/overdue returned book/i)).toBeInTheDocument();
      });

      const waiveBtn = screen.getByRole('button', { name: /waive fine/i });
      fireEvent.click(waiveBtn);

      // Dialog opens requesting reason
      expect(screen.getByRole('dialog', { name: /waive fine/i })).toBeInTheDocument();

      const reasonInput = screen.getByLabelText(/reason for waiver/i);
      fireEvent.change(reasonInput, { target: { value: 'Patron medical emergency' } });

      const confirmBtn = screen.getByRole('button', { name: /confirm waiver/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(waiveRequested).toBe(true);
      });

      expect(waivePayload).toEqual({
        reason: 'Patron medical emergency',
      });
    });
  });

  describe('Invoice Records and Read-Only Totals', () => {
    it('displays invoice history with explicit currency and line items', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'invoices' });

      await waitFor(() => {
        expect(screen.getByText('INV-2026-0001')).toBeInTheDocument();
      });

      expect(screen.getByText(/premium researcher plan annual subscription/i)).toBeInTheDocument();
      expect(screen.getByText(/subtotal:/i)).toBeInTheDocument();
      expect(screen.getAllByText(/USD 45.0000/i).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/● issued/i)).toBeInTheDocument();
    });

    it('enforces that issued invoice totals and line amounts are strictly read-only', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'invoices' });

      await waitFor(() => {
        expect(screen.getByText('INV-2026-0001')).toBeInTheDocument();
      });

      // Immutable issued badge/notice
      expect(screen.getByText(/immutable issued invoice/i)).toBeInTheDocument();

      // Any total or line item input must have readOnly or be non-editable text
      const totalElements = screen.getAllByDisplayValue('45.0000');
      for (const el of totalElements) {
        expect(el).toHaveAttribute('readOnly');
      }

      // No edit controls or line manipulation controls are present
      expect(screen.queryByRole('button', { name: /edit total/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /add line/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /delete line/i })).not.toBeInTheDocument();
    });

    it('allows voiding an invoice through backend-authorized action', async () => {
      setupDefaultMocks();

      let voidRequested = false;
      let voidPayload: unknown = null;

      vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/invoices/inv-11111111-1111-4111-8111-111111111111/void')) {
          voidRequested = true;
          voidPayload = JSON.parse(init?.body as string);
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({
              ...mockInvoices[0],
              status: 'void',
            }),
          } as Response;
        }

        if (url.includes('/invoices')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockInvoices }),
          } as Response;
        }

        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderPublicLibraryWorkspace({ initialTab: 'invoices' });

      await waitFor(() => {
        expect(screen.getByText('INV-2026-0001')).toBeInTheDocument();
      });

      const voidBtn = screen.getByRole('button', { name: /void invoice/i });
      fireEvent.click(voidBtn);

      expect(screen.getByRole('dialog', { name: /void invoice/i })).toBeInTheDocument();

      const reasonInput = screen.getByLabelText(/reason for voiding/i);
      fireEvent.change(reasonInput, { target: { value: 'Billed to incorrect patron account' } });

      const confirmBtn = screen.getByRole('button', { name: /confirm void/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(voidRequested).toBe(true);
      });

      expect(voidPayload).toEqual({
        reason: 'Billed to incorrect patron account',
      });
    });
  });

  describe('Payment History, State Representation and Security', () => {
    it('displays pending payment as pending without client-side settlement claim', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'payments' });

      await waitFor(() => {
        expect(screen.getByText(/pi_3KjF892eZvKYlo2C01pending/i)).toBeInTheDocument();
      });

      // Pending state displayed with plain language and non-color cue
      const pendingBadge = screen.getByText(/⏱ pending/i);
      expect(pendingBadge).toBeInTheDocument();

      // UI clarifies that settlement is pending asynchronous gateway verification
      expect(
        screen.getByText(/awaiting provider settlement or webhook confirmation/i),
      ).toBeInTheDocument();

      // No fake client-side success banner or claim
      expect(screen.queryByText(/payment completed successfully/i)).not.toBeInTheDocument();
    });

    it('displays all payment states in plain language with text and non-color cues', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace({ initialTab: 'payments' });

      await waitFor(() => {
        expect(screen.getByText(/pi_3KjF892eZvKYlo2C01pending/i)).toBeInTheDocument();
      });

      // Settled (succeeded)
      expect(screen.getByText(/✓ settled/i)).toBeInTheDocument();
      // Failed
      expect(screen.getByText(/✕ failed/i)).toBeInTheDocument();
      // Partial refund
      expect(screen.getByText(/◒ partial refund/i)).toBeInTheDocument();
      // Full refund
      expect(screen.getByText(/↺ refunded/i)).toBeInTheDocument();
    });

    it('minimizes sensitive data: never displays card numbers, provider secrets, or raw webhook material', async () => {
      setupDefaultMocks();
      const { container } = renderPublicLibraryWorkspace({ initialTab: 'payments' });

      await waitFor(() => {
        expect(screen.getByText(/pi_3KjF892eZvKYlo2C01pending/i)).toBeInTheDocument();
      });

      const fullHtml = container.innerHTML;
      // Never render card numbers or CVV
      expect(fullHtml).not.toMatch(/\b4[0-9]{12}(?:[0-9]{3})?\b/);
      expect(fullHtml).not.toMatch(/\bcvv\b/i);
      expect(fullHtml).not.toMatch(/\bcard_number\b/i);
      // Never render webhook signature secrets
      expect(fullHtml).not.toMatch(/whsec_/i);
      expect(fullHtml).not.toMatch(/secret_key/i);
    });

    it('does not infer payment success from an HTTP retry alone; triggers backend reconcile', async () => {
      setupDefaultMocks();

      let reconcileCalled = false;
      const basePayment = mockPayments[0];
      if (!basePayment) throw new Error('Mock payment not found');
      const testPayments: PublicLibraryPayment[] = [...mockPayments];
      vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/payments/pay-11111111-1111-4111-8111-111111111111/reconcile')) {
          reconcileCalled = true;
          const updated: PublicLibraryPayment = {
            ...basePayment,
            status: 'succeeded',
            paid_at: '2026-09-01T10:15:00Z',
          };
          testPayments[0] = updated;
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => updated,
          } as Response;
        }

        if (url.includes('/payments')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: testPayments }),
          } as Response;
        }

        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderPublicLibraryWorkspace({ initialTab: 'payments' });

      await waitFor(() => {
        expect(screen.getByText(/pi_3KjF892eZvKYlo2C01pending/i)).toBeInTheDocument();
      });

      // Find the row or card for the pending payment
      const reconcileBtn = screen.getByRole('button', { name: /reconcile payment/i });
      fireEvent.click(reconcileBtn);

      await waitFor(() => {
        expect(reconcileCalled).toBe(true);
      });

      // Updates strictly from backend response
      await waitFor(() => {
        expect(screen.getAllByText(/✓ settled/i).length).toBe(2);
      });
    });
  });

  describe('Edition Unavailable & Safe Error State', () => {
    it('renders edition-unavailable state without leaking tenant configuration on 403', async () => {
      vi.mocked(globalThis.fetch).mockImplementation(async () => {
        return {
          ok: false,
          status: 403,
          headers: new Headers({ 'Content-Type': 'application/problem+json' }),
          json: async () => ({
            type: 'https://openlibraryos.example/problems/edition-unavailable',
            title: 'Edition Unavailable',
            status: 403,
            detail: 'The public library edition is not enabled for this organization.',
            instance: '/api/v1/public-library/members',
            request_id: 'req-err-403',
          }),
        } as Response;
      });

      const { container } = renderPublicLibraryWorkspace();

      await waitFor(() => {
        expect(
          screen.getByRole('heading', { name: /public library edition unavailable/i }),
        ).toBeInTheDocument();
      });

      expect(
        screen.getByText(/the public library edition is not enabled for this organization/i),
      ).toBeInTheDocument();

      // Zero leakage of internal tenant configs, connection strings or database credentials
      const fullText = container.textContent || '';
      expect(fullText).not.toContain('Server=');
      expect(fullText).not.toContain('uid=');
      expect(fullText).not.toContain('Password=');
      expect(fullText).not.toContain('TenantRequestContext');

      // Clear return path to Circulation
      const returnBtn = screen.getByRole('link', { name: /return to circulation desk/i });
      expect(returnBtn).toBeInTheDocument();
      expect(returnBtn).toHaveAttribute('href', '#/circulation');
    });

    it('renders RFC 7807 problem details with retry and hides tabs when initial load fails (M-03)', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue({
        ok: false,
        status: 404,
        headers: new Headers({
          'Content-Type': 'application/problem+json',
          'X-Request-ID': 'req-err-404',
        }),
        json: async () => ({
          type: 'https://openlibrary.org/errors/not-found',
          title: 'Not Found',
          status: 404,
          detail: 'Public library module endpoints not found.',
          instance: '/api/v1/public-library',
          request_id: 'req-err-404',
        }),
      } as Response);

      renderPublicLibraryWorkspace();

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText(/Public library module endpoints not found/i)).toBeInTheDocument();
      });

      // Truthful Failure UI (M-03): hides tab navigation and does not show zero-count tabs or empty members message
      expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
      expect(screen.queryByText(/no public library members found/i)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('renders RFC 7807 problem details error banner safely when a financial action fails', async () => {
      setupDefaultMocks();

      vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/fines/fine-11111111-1111-4111-8111-111111111111/waive')) {
          return {
            ok: false,
            status: 409,
            headers: new Headers({ 'Content-Type': 'application/problem+json' }),
            json: async () => ({
              type: 'https://openlibraryos.example/problems/fine-already-closed',
              title: 'Fine Already Closed',
              status: 409,
              detail: 'Cannot waive fine fine-11111111-1111-4111-8111-111111111111 because it is already closed.',
              instance: '/api/v1/public-library/fines/fine-11111111-1111-4111-8111-111111111111/waive',
              request_id: 'req-err-409',
            }),
          } as Response;
        }

        if (url.includes('/fines')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockFines }),
          } as Response;
        }

        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderPublicLibraryWorkspace({ initialTab: 'fines' });

      await waitFor(() => {
        expect(screen.getByText(/overdue returned book/i)).toBeInTheDocument();
      });

      const waiveBtn = screen.getByRole('button', { name: /waive fine/i });
      fireEvent.click(waiveBtn);

      const reasonInput = screen.getByLabelText(/reason for waiver/i);
      fireEvent.change(reasonInput, { target: { value: 'Testing waiver failure' } });

      const confirmBtn = screen.getByRole('button', { name: /confirm waiver/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(screen.getByText(/fine already closed/i)).toBeInTheDocument();
        expect(screen.getByText(/because it is already closed/i)).toBeInTheDocument();
      });
    });
  });

  describe('App Shell & Navigation Route Integration', () => {
    it('integrates public-library route into navigation model and App shell', async () => {
      setupDefaultMocks();
      window.location.hash = '#/public-library';

      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      await waitFor(() => {
        expect(
          screen.getByRole('heading', { level: 2, name: /public library & finance/i }),
        ).toBeInTheDocument();
      });

      const nav = screen.getByRole('navigation', { name: /primary navigation/i });
      const publicLink = within(nav).getByRole('link', { name: /public library & finance/i });
      expect(publicLink).toBeInTheDocument();
      expect(publicLink).toHaveAttribute('href', '#/public-library');
    });

    it('passes authorization bearer token to public library API requests (H-02)', async () => {
      setupDefaultMocks();
      renderPublicLibraryWorkspace();

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/public-library/'),
          expect.objectContaining({
            headers: expect.objectContaining({
              Authorization: 'Bearer test-public-library-token',
            }),
          }),
        );
      });
    });
  });
});
