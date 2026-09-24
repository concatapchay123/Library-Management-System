import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { TokenProvider } from '../../../src/shared/tokens';
import { SessionProvider } from '../../../src/features/auth';
import { InventoryWorkspace } from '../../../src/features/inventory';
import { App } from '../../../src/app/App';
import {
  Book,
  Location,
  BookCopy,
  CopyStatusHistoryRecord,
} from '../../../src/shared/api';

const mockBook: Book = {
  book_id: 'b1111111-1111-4111-8111-111111111111',
  title: 'Designing Data-Intensive Applications',
  authors: ['Martin Kleppmann'],
  isbn: '978-1449373320',
  published_year: 2017,
};

const mockLocations: Location[] = [
  {
    location_id: 'loc-11111111-1111-4111-8111-111111111111',
    name: 'Main Stacks Level 2 - Shelf A3',
    code: 'MAIN-L2-A3',
    parent_location_id: null,
    status: 'active',
  },
  {
    location_id: 'loc-22222222-2222-4222-8222-222222222222',
    name: 'Reserve Desk Holding',
    code: 'RES-DESK',
    parent_location_id: null,
    status: 'active',
  },
  {
    location_id: 'loc-33333333-3333-4333-8333-333333333333',
    name: 'Conservation & Repair Lab',
    code: 'LAB-REPAIR',
    parent_location_id: null,
    status: 'active',
  },
];

const mockCopy1: BookCopy = {
  copy_id: 'c1111111-1111-4111-8111-111111111111',
  book_id: mockBook.book_id,
  barcode: 'BC-9781449373320-001',
  location_id: mockLocations[0]!.location_id,
  status: 'available',
  condition_code: 'good',
  acquired_at: '2026-01-15T08:00:00Z',
};

const mockCopy2: BookCopy = {
  copy_id: 'c2222222-2222-4222-8222-222222222222',
  book_id: mockBook.book_id,
  barcode: 'BC-9781449373320-002',
  location_id: mockLocations[1]!.location_id,
  status: 'lost',
  condition_code: 'fair',
  acquired_at: '2026-02-10T10:30:00Z',
};

const mockHistory1: CopyStatusHistoryRecord = {
  history_id: 'h1111111-1111-4111-8111-111111111111',
  copy_id: mockCopy1.copy_id,
  from_status: 'available',
  to_status: 'maintenance',
  reason: 'Routine binding inspection and reinforcing page stitching',
  actor_id: 'u9999999-9999-4999-8999-999999999999',
  created_at: '2026-03-01T14:22:00Z',
};

function renderInventoryWorkspace(props: { initialBook?: Book; initialCopyId?: string } = {}) {
  return render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-inventory-token">
        <InventoryWorkspace
          initialBook={props.initialBook ?? mockBook}
          initialCopyId={props.initialCopyId}
        />
      </SessionProvider>
    </TokenProvider>,
  );
}

describe('Inventory, Locations, Copies and Status-Management Workspace (FE-006)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Form Layout, Labels, Help Text & Single Primary Action Invariants', () => {
    it('renders barcode, location, and condition fields with explicit labels and help text', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace();

      await waitFor(() => {
        expect(screen.getByLabelText(/copy barcode/i)).toBeInTheDocument();
      });

      // Barcode field has explicit label and help text
      const barcodeInput = screen.getByLabelText(/copy barcode/i);
      expect(barcodeInput).toBeInTheDocument();
      expect(
        screen.getByText(/scan or enter physical barcode label/i),
      ).toBeInTheDocument();

      // Location field has explicit label and help text
      const regPanel = screen.getByTestId('copy-registration-panel');
      const locationSelect = within(regPanel).getByLabelText(/shelf location/i);
      expect(locationSelect).toBeInTheDocument();
      expect(
        screen.getByText(/select the physical shelving or holding location/i),
      ).toBeInTheDocument();

      // Condition field has explicit label, (Optional) tag, and help text
      const conditionInput = screen.getByLabelText(/copy condition/i);
      expect(conditionInput).toBeInTheDocument();
      expect(within(regPanel).getByText(/\(optional\)/i)).toBeInTheDocument();
      expect(
        screen.getByText(/current physical condition assessment/i),
      ).toBeInTheDocument();
    });

    it('has exactly one primary submission action per workflow panel', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace({ initialCopyId: mockCopy1.copy_id });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /register copy/i })).toBeInTheDocument();
      });

      // Panel 1: Copy Registration has ONE primary button
      const regPanel = screen.getByTestId('copy-registration-panel');
      const regButtons = within(regPanel).getAllByRole('button');
      const primaryRegButtons = regButtons.filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryRegButtons).toHaveLength(1);
      expect(primaryRegButtons[0]!).toHaveTextContent(/register copy/i);

      // Panel 2: Location Assignment has ONE primary button
      const locPanel = screen.getByTestId('location-assignment-panel');
      const locButtons = within(locPanel).getAllByRole('button');
      const primaryLocButtons = locButtons.filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryLocButtons).toHaveLength(1);
      expect(primaryLocButtons[0]!).toHaveTextContent(/update location/i);

      // Panel 3: Status Management has ONE primary button
      const statusPanel = screen.getByTestId('copy-status-panel');
      const statusButtons = within(statusPanel).getAllByRole('button');
      const primaryStatusButtons = statusButtons.filter((b) => b.getAttribute('data-variant') === 'primary');
      expect(primaryStatusButtons).toHaveLength(1);
      expect(primaryStatusButtons[0]!).toHaveTextContent(/change status/i);
    });

    it('strictly separates bibliographic title facts from copy-level physical state', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace();

      await waitFor(() => {
        expect(screen.getByText('Designing Data-Intensive Applications')).toBeInTheDocument();
      });

      // Clear domain boundary statement explaining intellectual work vs physical copies
      expect(
        screen.getByText(/bibliographic title records represent the intellectual work/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/physical copies are individually tracked shelf inventory items/i),
      ).toBeInTheDocument();
    });
  });

  describe('Client-Side Immediate Validation', () => {
    it('validates barcode, location, and reason immediately before making server requests', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /register copy/i })).toBeInTheDocument();
      });

      const registerBtn = screen.getByRole('button', { name: /register copy/i });
      fireEvent.click(registerBtn);

      // Immediate client-side validation triggers
      await waitFor(() => {
        expect(screen.getByText(/barcode is required/i)).toBeInTheDocument();
        expect(screen.getByText(/please select a shelving location/i)).toBeInTheDocument();
      });

      // Verify no POST request was dispatched due to client validation failure
      expect(fetch).not.toHaveBeenCalledWith(
        expect.stringContaining('/copies'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  describe('Copy Registration Workflow', () => {
    it('registers a copy and displays the newly created physical copy in the inventory list', async () => {
      const createdCopy: BookCopy = {
        copy_id: 'c3333333-3333-4333-8333-333333333333',
        book_id: mockBook.book_id,
        barcode: 'BC-9781449373320-003',
        location_id: mockLocations[0]!.location_id,
        status: 'available',
        condition_code: 'mint',
        acquired_at: '2026-03-24T10:00:00Z',
      };

      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method ?? 'GET';

        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies') && method === 'POST') {
          return {
            ok: true,
            status: 201,
            headers: new Headers({
              'content-type': 'application/json',
              'X-Request-ID': 'req-copy-create-ok',
            }),
            json: async () => createdCopy,
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace();

      await waitFor(() => {
        expect(screen.getByLabelText(/copy barcode/i)).toBeInTheDocument();
      });

      const regPanel = screen.getByTestId('copy-registration-panel');
      // Fill in barcode and select location
      fireEvent.change(screen.getByLabelText(/copy barcode/i), {
        target: { value: 'BC-9781449373320-003' },
      });
      fireEvent.change(within(regPanel).getByLabelText(/shelf location/i), {
        target: { value: mockLocations[0]!.location_id },
      });
      fireEvent.change(screen.getByLabelText(/copy condition/i), {
        target: { value: 'mint' },
      });

      // Submit registration
      fireEvent.click(screen.getByRole('button', { name: /register copy/i }));

      // Verify POST call
      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          expect.stringContaining(`/api/v1/books/${mockBook.book_id}/copies`),
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({
              barcode: 'BC-9781449373320-003',
              location_id: mockLocations[0]!.location_id,
              condition_code: 'mint',
            }),
          }),
        );
      });

      // Newly created copy appears in the copy list
      await waitFor(() => {
        expect(screen.getByText('BC-9781449373320-003')).toBeInTheDocument();
      });
    });

    it('surfaces stable Problem Details beside registration form on duplicate barcode error', async () => {
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method ?? 'GET';

        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies') && method === 'POST') {
          return {
            ok: false,
            status: 409,
            headers: new Headers({
              'content-type': 'application/problem+json',
              'X-Request-ID': 'req-barcode-dup-409',
            }),
            json: async () => ({
              type: 'https://openlibraryos.example/problems/conflict',
              title: 'Duplicate Barcode',
              status: 409,
              detail: 'A physical copy with barcode BC-9781449373320-001 already exists in this organization.',
              instance: `/api/v1/books/${mockBook.book_id}/copies`,
              request_id: 'req-barcode-dup-409',
            }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace();

      await waitFor(() => {
        expect(screen.getByLabelText(/copy barcode/i)).toBeInTheDocument();
      });

      const regPanel = screen.getByTestId('copy-registration-panel');
      fireEvent.change(screen.getByLabelText(/copy barcode/i), {
        target: { value: 'BC-9781449373320-001' },
      });
      fireEvent.change(within(regPanel).getByLabelText(/shelf location/i), {
        target: { value: mockLocations[0]!.location_id },
      });

      fireEvent.click(screen.getByRole('button', { name: /register copy/i }));

      // Problem details displayed beside the form
      await waitFor(() => {
        expect(screen.getByText('Duplicate Barcode')).toBeInTheDocument();
        expect(
          screen.getByText(/already exists in this organization/i),
        ).toBeInTheDocument();
        expect(screen.getByText('req-barcode-dup-409')).toBeInTheDocument();
      });
    });
  });

  describe('Permitted Server-Defined Status Actions', () => {
    it('renders only permitted server-defined status actions for an available copy', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies') && url.includes('/history')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [] }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace({ initialCopyId: mockCopy1.copy_id });

      await waitFor(() => {
        expect(screen.getByLabelText(/target status/i)).toBeInTheDocument();
      });

      const targetSelect = screen.getByLabelText(/target status/i) as HTMLSelectElement;
      const options = Array.from(targetSelect.options).map((o) => o.value).filter(Boolean);

      // For available copy, allowed backend transitions are: borrowed, reserved, maintenance, damaged, lost
      expect(options).toEqual(
        expect.arrayContaining(['borrowed', 'reserved', 'maintenance', 'damaged', 'lost']),
      );
      // 'available' itself must not be an action option
      expect(options).not.toContain('available');
    });

    it('renders only permitted server-defined status actions for a lost copy', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies') && url.includes('/history')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [] }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy2] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      // Render workspace with copy2 (status: 'lost')
      renderInventoryWorkspace({ initialCopyId: mockCopy2.copy_id });

      await waitFor(() => {
        expect(screen.getByLabelText(/target status/i)).toBeInTheDocument();
      });

      const targetSelect = screen.getByLabelText(/target status/i) as HTMLSelectElement;
      const options = Array.from(targetSelect.options).map((o) => o.value).filter(Boolean);

      // Backend BE-014 policy: lost -> [available, maintenance, damaged]
      // borrowed and reserved MUST NOT appear for a lost copy!
      expect(options).toEqual(expect.arrayContaining(['available', 'maintenance', 'damaged']));
      expect(options).not.toContain('borrowed');
      expect(options).not.toContain('reserved');
      expect(options).not.toContain('lost');
    });
  });

  describe('Status Transition Failure & Read-Only History (Evidence Checkpoint)', () => {
    it('displays comprehensible error without mutating local history on invalid server transition', async () => {
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        const url = String(input);
        const method = init?.method ?? 'GET';

        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/history')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockHistory1] }),
          } as Response;
        }
        if (url.includes('/status') && method === 'POST') {
          // Server rejects with 409 Problem Details
          return {
            ok: false,
            status: 409,
            headers: new Headers({
              'content-type': 'application/problem+json',
              'X-Request-ID': 'req-invalid-trans-409',
            }),
            json: async () => ({
              type: 'https://openlibraryos.example/problems/invalid-copy-status-transition',
              title: 'Invalid copy status transition',
              status: 409,
              detail: "Cannot transition copy status from 'lost' to 'borrowed'.",
              instance: `/api/v1/copies/${mockCopy2.copy_id}/status`,
              request_id: 'req-invalid-trans-409',
            }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy2] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace({ initialCopyId: mockCopy2.copy_id });

      // Wait for existing history to load
      await waitFor(() => {
        expect(
          screen.getByText('Routine binding inspection and reinforcing page stitching'),
        ).toBeInTheDocument();
      });

      // Target status selection and mandatory reason input
      fireEvent.change(screen.getByLabelText(/target status/i), {
        target: { value: 'available' },
      });
      fireEvent.change(screen.getByLabelText(/transition reason/i), {
        target: { value: 'Patron located missing book on library shelf' },
      });

      // Submit status change
      fireEvent.click(screen.getByRole('button', { name: /change status/i }));

      // Problem Details rendered beside status controls
      await waitFor(() => {
        expect(screen.getByText('Invalid copy status transition')).toBeInTheDocument();
        expect(
          screen.getByText("Cannot transition copy status from 'lost' to 'borrowed'."),
        ).toBeInTheDocument();
        expect(screen.getByText('req-invalid-trans-409')).toBeInTheDocument();
      });

      // CRITICAL EVIDENCE CHECKPOINT: Local history remains completely unchanged!
      const historyRows = screen.getAllByTestId('history-record-item');
      expect(historyRows).toHaveLength(1);
      expect(
        screen.getByText('Routine binding inspection and reinforcing page stitching'),
      ).toBeInTheDocument();
      expect(
        screen.queryByText('Patron located missing book on library shelf'),
      ).not.toBeInTheDocument();
    });

    it('renders visibly read-only status history identifying actor, reason, and timestamp', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/history')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockHistory1] }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderInventoryWorkspace({ initialCopyId: mockCopy1.copy_id });

      // Verify read-only notice
      await waitFor(() => {
        expect(
          screen.getByText(/immutable audit log|read-only status history/i),
        ).toBeInTheDocument();
      });

      // Verify history item fields: Actor, Reason, Transition, and Time
      const historyItem = screen.getByTestId('history-record-item');
      expect(historyItem).toBeInTheDocument();

      // Actor identified
      expect(
        within(historyItem).getByText(/u9999999-9999-4999-8999-999999999999/),
      ).toBeInTheDocument();

      // Reason identified
      expect(
        within(historyItem).getByText(
          'Routine binding inspection and reinforcing page stitching',
        ),
      ).toBeInTheDocument();

      // Transition identified: available -> maintenance
      expect(within(historyItem).getByText(/available/i)).toBeInTheDocument();
      expect(within(historyItem).getByText(/maintenance/i)).toBeInTheDocument();

      // Time rendered
      expect(within(historyItem).getByText(/2026/)).toBeInTheDocument();

      // No edit or delete controls exist in history (purely read-only)
      expect(within(historyItem).queryByRole('button', { name: /edit|delete|remove/i })).toBeNull();
    });
  });

  describe('Application Shell Navigation Integration', () => {
    it('navigates to Inventory workspace when Inventory link is clicked in AppShell', async () => {
      vi.mocked(fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes('/locations')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: mockLocations }),
          } as Response;
        }
        if (url.includes('/copies')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ items: [mockCopy1] }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      render(
        <TokenProvider>
          <App initialAuthenticated={true} />
        </TokenProvider>,
      );

      // Find Inventory navigation link
      const inventoryNavLinks = screen.getAllByRole('link', { name: /inventory/i });
      expect(inventoryNavLinks.length).toBeGreaterThan(0);
      const inventoryNav = inventoryNavLinks[0]!;

      // Click Inventory tab
      fireEvent.click(inventoryNav);

      // App heading updates to Inventory & Copy Management
      await waitFor(() => {
        expect(
          screen.getByRole('heading', { level: 1, name: /inventory & copy management/i }),
        ).toBeInTheDocument();
      });

      // Copy registration panel is available in the workspace
      expect(screen.getByLabelText(/copy barcode/i)).toBeInTheDocument();
    });
  });
});
