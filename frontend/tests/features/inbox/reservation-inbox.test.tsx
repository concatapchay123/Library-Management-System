import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { TokenProvider } from '../../../src/shared/tokens';
import { SessionProvider } from '../../../src/features/auth';
import { ReservationInbox } from '../../../src/features/inbox';
import { Reservation, Notification } from '../../../src/shared/api';
import { App } from '../../../src/app/App';

const mockPendingReservation: Reservation = {
  reservation_id: 'r1111111-1111-4111-8111-111111111111',
  organization_id: 'org-test-001',
  book_id: 'b1111111-1111-4111-8111-111111111111',
  requester_user_id: 'u1111111-1111-4111-8111-111111111111',
  queue_position: 2,
  status: 'pending',
  copy_id: null,
  hold_expires_at: null,
  fulfilled_at: null,
  cancelled_at: null,
  created_at: '2026-03-24T09:00:00Z',
  updated_at: '2026-03-24T09:00:00Z',
};

const mockHeldReservation: Reservation = {
  reservation_id: 'r2222222-2222-4222-8222-222222222222',
  organization_id: 'org-test-001',
  book_id: 'b2222222-2222-4222-8222-222222222222',
  requester_user_id: 'u1111111-1111-4111-8111-111111111111',
  queue_position: 1,
  status: 'held',
  copy_id: 'c2222222-2222-4222-8222-222222222222',
  hold_expires_at: '2026-03-26T12:00:00Z',
  fulfilled_at: null,
  cancelled_at: null,
  created_at: '2026-03-24T10:00:00Z',
  updated_at: '2026-03-24T10:00:00Z',
};

const mockUnreadNotification: Notification = {
  notification_id: 'n1111111-1111-4111-8111-111111111111',
  organization_id: 'org-test-001',
  user_id: 'u1111111-1111-4111-8111-111111111111',
  channel: 'in_app',
  type: 'circulation.reservation_allocated',
  payload: {
    reservation_id: 'r2222222-2222-4222-8222-222222222222',
    book_id: 'b2222222-2222-4222-8222-222222222222',
    book_title: 'Designing Data-Intensive Applications',
    message: 'Your reserved book is ready for pickup at Main Circulation Desk.',
    hold_expires_at: '2026-03-26T12:00:00Z',
  },
  status: 'unread',
  read_at: null,
  created_at: '2026-03-24T10:05:00Z',
};

const mockReadNotification: Notification = {
  notification_id: 'n2222222-2222-4222-8222-222222222222',
  organization_id: 'org-test-001',
  user_id: 'u1111111-1111-4111-8111-111111111111',
  channel: 'in_app',
  type: 'circulation.loan_due_soon',
  payload: {
    loan_id: 'l3333333-3333-4333-8333-333333333333',
    book_title: 'Clean Architecture',
    message: 'Your loan is due in 3 days. Please return or renew online.',
    due_at: '2026-03-27T18:00:00Z',
  },
  status: 'read',
  read_at: '2026-03-24T11:00:00Z',
  created_at: '2026-03-24T08:00:00Z',
};

function renderReservationInbox(props: {
  initialReservations?: Reservation[];
  initialNotifications?: Notification[];
  onOpenRecord?: (type: string, id: string) => void;
} = {}) {
  return render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-inbox-token">
        <ReservationInbox
          initialReservations={props.initialReservations}
          initialNotifications={props.initialNotifications}
          onOpenRecord={props.onOpenRecord}
        />
      </SessionProvider>
    </TokenProvider>,
  );
}

describe('Reservation status and notification inbox (FE-008)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Reservation queue progression and hold status', () => {
    it('renders pending reservation queue progression using server facts without promising pickup date', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-res-001' }),
            json: async () => ({ items: [mockPendingReservation], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-notif-001' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByTestId('reservation-item-r1111111-1111-4111-8111-111111111111')).toBeInTheDocument();
      });

      // Must display queue position 2 from server
      expect(screen.getByText(/Queue Position #2/i)).toBeInTheDocument();
      expect(screen.getByText(/Waiting for Copy Allocation/i)).toBeInTheDocument();

      // Invariant: MUST NOT promise pickup date or calculate client-side availability
      expect(screen.queryByText(/pickup date guaranteed/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/estimated pickup/i)).not.toBeInTheDocument();
    });

    it('renders held reservation with exact server-provided hold expiration date', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-res-002' }),
            json: async () => ({ items: [mockHeldReservation], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-notif-002' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByTestId('reservation-item-r2222222-2222-4222-8222-222222222222')).toBeInTheDocument();
      });

      // Status badge and hold expiry verbatim
      expect(screen.getByText(/Ready for Pickup \(Held\)/i)).toBeInTheDocument();
      expect(screen.getByText(/2026-03-26T12:00:00Z/i)).toBeInTheDocument();
      expect(screen.getByText(/Copy ID: c2222222-2222-4222-8222-222222222222/i)).toBeInTheDocument();
    });

    it('allows cancelling a pending or held reservation with server confirmation', async () => {
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method || 'GET';
        if (url.includes('/reservations') && method === 'GET') {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-res-003' }),
            json: async () => ({ items: [mockPendingReservation], total: 1 }),
          } as Response;
        }
        if (url.includes('/reservations/r1111111-1111-4111-8111-111111111111/cancel') && method === 'POST') {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-cancel-001' }),
            json: async () => ({
              ...mockPendingReservation,
              status: 'cancelled',
              cancelled_at: '2026-03-24T12:00:00Z',
            }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Cancel Reservation/i })).toBeInTheDocument();
      });

      const cancelBtn = screen.getByRole('button', { name: /Cancel Reservation/i });
      fireEvent.click(cancelBtn);

      await waitFor(() => {
        expect(screen.getByText(/Reservation Cancelled/i)).toBeInTheDocument();
      });
    });
  });

  describe('Notification inbox and read-state workflow', () => {
    it('presents notifications with distinct unread vs read badges', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-notif-003' }),
            json: async () => ({ items: [mockUnreadNotification, mockReadNotification], total: 2 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByTestId('notification-item-n1111111-1111-4111-8111-111111111111')).toBeInTheDocument();
        expect(screen.getByTestId('notification-item-n2222222-2222-4222-8222-222222222222')).toBeInTheDocument();
      });

      // Unread badge and read badge
      expect(screen.getByText('Unread')).toBeInTheDocument();
      expect(screen.getByText('Read')).toBeInTheDocument();

      // Content payload messages
      expect(screen.getByText(/Your reserved book is ready for pickup/i)).toBeInTheDocument();
      expect(screen.getByText(/Your loan is due in 3 days/i)).toBeInTheDocument();
    });

    it('marking a notification read updates ONLY after a successful server response', async () => {
      let markReadCalled = false;
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method || 'GET';
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        if (url.includes('/notifications') && method === 'GET') {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockUnreadNotification], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications/n1111111-1111-4111-8111-111111111111/read') && method === 'POST') {
          markReadCalled = true;
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-read-001' }),
            json: async () => ({
              ...mockUnreadNotification,
              status: 'read',
              read_at: '2026-03-24T12:00:00Z',
            }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Mark as Read/i })).toBeInTheDocument();
      });

      const markReadBtn = screen.getByRole('button', { name: /Mark as Read/i });
      fireEvent.click(markReadBtn);

      await waitFor(() => {
        expect(markReadCalled).toBe(true);
        // Once server responds 200, status changes to Read
        expect(screen.queryByRole('button', { name: /Mark as Read/i })).not.toBeInTheDocument();
        expect(screen.getByText('Read')).toBeInTheDocument();
      });
    });

    it('marking a notification read does NOT update if server responds with error', async () => {
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method || 'GET';
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        if (url.includes('/notifications') && method === 'GET') {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockUnreadNotification], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications/n1111111-1111-4111-8111-111111111111/read') && method === 'POST') {
          return {
            ok: false,
            status: 500,
            headers: new Headers({ 'Content-Type': 'application/problem+json', 'X-Request-ID': 'req-err-001' }),
            json: async () => ({
              type: 'https://openlibrary.org/errors/internal-error',
              title: 'Internal Server Error',
              status: 500,
              detail: 'Database transaction failed during read marker.',
              instance: '/api/v1/notifications/n1111111-1111-4111-8111-111111111111/read',
              request_id: 'req-err-001',
            }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Mark as Read/i })).toBeInTheDocument();
      });

      const markReadBtn = screen.getByRole('button', { name: /Mark as Read/i });
      fireEvent.click(markReadBtn);

      // Verify that notification remains Unread and error details are rendered
      await waitFor(() => {
        expect(screen.getByText('Unread')).toBeInTheDocument();
        expect(screen.getByText(/Database transaction failed during read marker/i)).toBeInTheDocument();
      });
      // The mark as read button should still be available to retry
      expect(screen.getByRole('button', { name: /Mark as Read/i })).toBeInTheDocument();
    });

    it('read-state controls are keyboard accessible', async () => {
      let markReadCalled = false;
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method || 'GET';
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        if (url.includes('/notifications') && method === 'GET') {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockUnreadNotification], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications/n1111111-1111-4111-8111-111111111111/read') && method === 'POST') {
          markReadCalled = true;
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req-read-kbd' }),
            json: async () => ({
              ...mockUnreadNotification,
              status: 'read',
              read_at: '2026-03-24T12:00:00Z',
            }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Mark as Read/i })).toBeInTheDocument();
      });

      const markReadBtn = screen.getByRole('button', { name: /Mark as Read/i });
      await act(async () => {
        markReadBtn.focus();
      });
      expect(document.activeElement).toBe(markReadBtn);

      // Trigger with Enter key wrapped in act
      await act(async () => {
        fireEvent.keyDown(markReadBtn, { key: 'Enter', code: 'Enter' });
      });

      await waitFor(() => {
        expect(markReadCalled).toBe(true);
        expect(screen.getByText('Read')).toBeInTheDocument();
      });
    });
  });

  describe('Empty and failure states', () => {
    it('uses distinct understandable copy for no-reservations and no-notifications states', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByText(/No Active Reservations/i)).toBeInTheDocument();
        expect(screen.getByText(/Notification Inbox Clear/i)).toBeInTheDocument();
      });

      // Distinct understandable copy
      expect(
        screen.getByText(/You do not have any pending or held book reservations at this time/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/You have no unread notifications or system alerts/i),
      ).toBeInTheDocument();

      // Clear next action
      expect(screen.getByRole('button', { name: /Explore Catalog/i })).toBeInTheDocument();
    });

    it('renders problem details renderer with retry on server failure', async () => {
      vi.mocked(fetch).mockImplementation(async () => {
        return {
          ok: false,
          status: 403,
          headers: new Headers({
            'Content-Type': 'application/problem+json',
            'X-Request-ID': 'req-err-403',
          }),
          json: async () => ({
            type: 'https://openlibrary.org/errors/authorization-denied',
            title: 'Forbidden',
            status: 403,
            detail: 'Principal lacks permission to access reservation inbox.',
            instance: '/api/v1/reservations',
            request_id: 'req-err-403',
          }),
        } as Response;
      });

      renderReservationInbox();

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText(/Principal lacks permission to access reservation inbox/i)).toBeInTheDocument();
      });

      // Shows request ID citation
      expect(screen.getByText(/req-err-403/i)).toBeInTheDocument();
      // Retry button is available
      expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();

      // Truthful Failure UI (M-03): hides synchronized cues and zero-count tablist on loadError
      expect(screen.queryByText(/synchronized with authoritative backend state/i)).not.toBeInTheDocument();
      expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
      expect(screen.queryByText(/All Items \(0\)/i)).not.toBeInTheDocument();
    });
  });

  describe('Dominant action and record opening', () => {
    it('inbox items contain one dominant action: open the relevant record', async () => {
      const onOpenRecord = vi.fn();

      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockPendingReservation], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockUnreadNotification], total: 1 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      renderReservationInbox({ onOpenRecord });

      await waitFor(() => {
        expect(screen.getByTestId('open-record-res-r1111111-1111-4111-8111-111111111111')).toBeInTheDocument();
        expect(screen.getByTestId('open-record-notif-n1111111-1111-4111-8111-111111111111')).toBeInTheDocument();
      });

      // Dominant action on reservation card
      const openResBtn = screen.getByTestId('open-record-res-r1111111-1111-4111-8111-111111111111');
      fireEvent.click(openResBtn);
      expect(onOpenRecord).toHaveBeenCalledWith('book', 'b1111111-1111-4111-8111-111111111111');

      // Dominant action on notification card
      const openNotifBtn = screen.getByTestId('open-record-notif-n1111111-1111-4111-8111-111111111111');
      fireEvent.click(openNotifBtn);
      expect(onOpenRecord).toHaveBeenCalledWith('reservation', 'r2222222-2222-4222-8222-222222222222');
    });

    it('notifications are not treated as a source of authorization truth', async () => {
      // Notification says "ready for pickup", but actual record interaction is bound to server verification
      const onOpenRecord = vi.fn();
      renderReservationInbox({
        initialNotifications: [mockUnreadNotification],
        initialReservations: [],
        onOpenRecord,
      });

      const openRecordBtn = screen.getByTestId('open-record-notif-n1111111-1111-4111-8111-111111111111');
      fireEvent.click(openRecordBtn);

      // The UI passes the identifier to open the record; it does not claim loan possession or bypass server authorization
      expect(onOpenRecord).toHaveBeenCalledWith('reservation', 'r2222222-2222-4222-8222-222222222222');
    });
  });

  describe('Integration with App Shell', () => {
    it('renders reservation and notification inbox when navigating to #/reservations', async () => {
      window.location.hash = '#/reservations';

      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/reservations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockHeldReservation], total: 1 }),
          } as Response;
        }
        if (url.includes('/notifications')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [mockUnreadNotification], total: 1 }),
          } as Response;
        }
        return { ok: false, status: 404 } as Response;
      });

      render(<App initialAuthenticated={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('reservation-inbox-workspace')).toBeInTheDocument();
      });

      expect(screen.getAllByText(/Reservation Queue & Notification Inbox/i).length).toBeGreaterThanOrEqual(1);
    });
  });
});
