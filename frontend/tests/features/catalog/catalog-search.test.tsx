import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { TokenProvider } from '../../../src/shared/tokens';
import { SessionProvider } from '../../../src/features/auth';
import { CatalogSearch } from '../../../src/features/catalog';
import { App } from '../../../src/app/App';
import { Book, BookPage } from '../../../src/shared/api';

const mockBook1: Book = {
  book_id: 'b1111111-1111-4111-8111-111111111111',
  title: 'Designing Data-Intensive Applications',
  authors: ['Martin Kleppmann'],
  isbn: '978-1449373320',
  published_year: 2017,
};

const mockBook2: Book = {
  book_id: 'b2222222-2222-4222-8222-222222222222',
  title: 'Domain-Driven Design: Tackling Complexity',
  authors: ['Eric Evans'],
  isbn: '978-0321125217',
  published_year: 2003,
};

const mockBookPage1: BookPage = {
  items: [mockBook1],
  next_cursor: 'cursor-token-page-2',
};

const mockBookPage2: BookPage = {
  items: [mockBook2],
  next_cursor: null,
};

function renderCatalogSearch(props = {}) {
  return render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-catalog-token">
        <CatalogSearch {...props} />
      </SessionProvider>
    </TokenProvider>,
  );
}

describe('Catalog Search and Book Browsing (FE-005)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Form Layout, Prominent Action & User Language Invariants', () => {
    it('renders prominent search input with actionable placeholder and single primary action', () => {
      renderCatalogSearch();

      const searchInput = screen.getByLabelText(/search catalog/i);
      expect(searchInput).toBeInTheDocument();
      // Actionable placeholder complying with design invariant
      expect(searchInput).toHaveAttribute(
        'placeholder',
        expect.stringMatching(/search by book title, author, or isbn/i),
      );

      // Search button is the prominent primary action
      const searchButton = screen.getByRole('button', { name: /search catalog/i });
      expect(searchButton).toBeInTheDocument();

      // Clear/Reset filter action exists as secondary
      const clearButton = screen.queryByRole('button', { name: /clear filters|reset/i });
      expect(clearButton).toBeInTheDocument();
    });

    it('distinguishes bibliographic books from physical copies in user language', () => {
      renderCatalogSearch();

      // UI explains in clear user language that catalog records are bibliographic titles, not shelf copies
      const distinctionNotices = screen.getAllByText(/bibliographic (catalog|records|title)/i);
      expect(distinctionNotices.length).toBeGreaterThan(0);
      expect(
        screen.getByText(/physical cop(y|ies)|shelf inventory|circulation desk/i),
      ).toBeInTheDocument();
    });

    it('displays documented supported filter inputs in a single-column layout', () => {
      renderCatalogSearch();

      const titleInput = screen.getByLabelText(/search catalog|book title/i);
      const isbnInput = screen.getByLabelText(/filter by isbn|isbn/i);

      expect(titleInput).toBeInTheDocument();
      expect(isbnInput).toBeInTheDocument();
      expect(isbnInput).toHaveAttribute('placeholder', expect.stringMatching(/978-/i));
    });
  });

  describe('Search Execution, Result Rendering & Loading State', () => {
    it('submits search query and renders matching bibliographic books with metadata', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-catalog-1',
        }),
        json: async () => ({
          items: [mockBook1, mockBook2],
          next_cursor: null,
        }),
      } as Response);

      renderCatalogSearch();

      const searchInput = screen.getByLabelText(/search catalog/i);
      fireEvent.change(searchInput, { target: { value: 'Designing Data' } });

      const searchButton = screen.getByRole('button', { name: /search catalog/i });
      fireEvent.click(searchButton);

      // Verify API fetch was called with title filter
      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/v1/books?limit=20&title=Designing+Data'),
          expect.objectContaining({
            method: 'GET',
            headers: expect.objectContaining({
              Authorization: 'Bearer test-catalog-token',
            }),
          }),
        );
      });

      // Verify results rendered
      await waitFor(() => {
        expect(
          screen.getByText('Designing Data-Intensive Applications'),
        ).toBeInTheDocument();
        expect(
          screen.getByText('Domain-Driven Design: Tackling Complexity'),
        ).toBeInTheDocument();
      });

      // Verify metadata displayed: authors, ISBN, publication year
      expect(screen.getByText(/Martin Kleppmann/i)).toBeInTheDocument();
      expect(screen.getByText(/978-1449373320/i)).toBeInTheDocument();
      expect(screen.getByText(/2017/i)).toBeInTheDocument();

      // Verify result summary
      expect(screen.getByText(/2 bibliographic titles found/i)).toBeInTheDocument();
    });

    it('renders empty state explaining when no matching books are found with reset action', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-empty-1',
        }),
        json: async () => ({
          items: [],
          next_cursor: null,
        }),
      } as Response);

      renderCatalogSearch();

      const searchInput = screen.getByLabelText(/search catalog/i);
      fireEvent.change(searchInput, { target: { value: 'Nonexistent Quantum Manual' } });

      fireEvent.click(screen.getByRole('button', { name: /search catalog/i }));

      await waitFor(() => {
        expect(screen.getByText(/no bibliographic books found/i)).toBeInTheDocument();
      });

      expect(
        screen.getByText(/no books in the catalog matched your search criteria/i),
      ).toBeInTheDocument();

      // Clear filters button resets query and shows initial state
      const clearButton = screen.getByRole('button', { name: /clear search|reset filters/i });
      fireEvent.click(clearButton);

      expect(searchInput).toHaveValue('');
    });
  });

  describe('Cursor Continuation & Filter Preservation', () => {
    it('preserves the selected supported filters when continuing through next cursor', async () => {
      // First page response
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-page-1',
        }),
        json: async () => mockBookPage1,
      } as Response);

      // Second page response
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-page-2',
        }),
        json: async () => mockBookPage2,
      } as Response);

      renderCatalogSearch();

      const titleInput = screen.getByLabelText(/search catalog/i);
      const isbnInput = screen.getByLabelText(/filter by isbn|isbn/i);

      fireEvent.change(titleInput, { target: { value: 'Design' } });
      fireEvent.change(isbnInput, { target: { value: '978' } });

      fireEvent.click(screen.getByRole('button', { name: /search catalog/i }));

      // Wait for page 1 results
      await waitFor(() => {
        expect(
          screen.getByText('Designing Data-Intensive Applications'),
        ).toBeInTheDocument();
      });

      // Verify page 1 URL contained the filters
      expect(fetch).toHaveBeenNthCalledWith(
        1,
        expect.stringMatching(/\/api\/v1\/books\?.*title=Design.*isbn=978/),
        expect.anything(),
      );

      // Next page pagination control is visible
      const nextPageButton = screen.getByRole('button', { name: /next page|load more/i });
      expect(nextPageButton).toBeInTheDocument();

      // Click Next Page
      fireEvent.click(nextPageButton);

      // Critical Checkpoint: Cursor continuation preserves selected supported filters!
      await waitFor(() => {
        expect(fetch).toHaveBeenNthCalledWith(
          2,
          expect.stringMatching(
            /\/api\/v1\/books\?.*cursor=cursor-token-page-2.*title=Design.*isbn=978/,
          ),
          expect.anything(),
        );
      });

      // Verify page 2 book appears
      await waitFor(() => {
        expect(
          screen.getByText('Domain-Driven Design: Tackling Complexity'),
        ).toBeInTheDocument();
      });
    });
  });

  describe('API Error Handling & Recoverability', () => {
    it('renders RFC Problem Details with retry action upon API error', async () => {
      // Error response
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: new Headers({
          'content-type': 'application/problem+json',
          'X-Request-ID': 'req-catalog-err-1',
        }),
        json: async () => ({
          type: 'https://openlibraryos.example/problems/bad-request',
          title: 'Invalid Catalog Query',
          status: 400,
          detail: 'Unsupported filter field provided to catalog index.',
          instance: '/api/v1/books',
          request_id: 'req-catalog-err-1',
        }),
      } as Response);

      // Subsequent successful retry response
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-catalog-retry-ok',
        }),
        json: async () => ({
          items: [mockBook1],
          next_cursor: null,
        }),
      } as Response);

      renderCatalogSearch();

      const searchInput = screen.getByLabelText(/search catalog/i);
      fireEvent.change(searchInput, { target: { value: 'InvalidSearch' } });
      fireEvent.click(screen.getByRole('button', { name: /search catalog/i }));

      // Verify Problem Details rendered
      await waitFor(() => {
        expect(screen.getByText('Invalid Catalog Query')).toBeInTheDocument();
        expect(
          screen.getByText('Unsupported filter field provided to catalog index.'),
        ).toBeInTheDocument();
      });

      // Retry button is available
      const retryButton = screen.getByRole('button', { name: /try again|retry/i });
      expect(retryButton).toBeInTheDocument();

      // Click retry
      fireEvent.click(retryButton);

      // Verify recovery to successful state
      await waitFor(() => {
        expect(
          screen.getByText('Designing Data-Intensive Applications'),
        ).toBeInTheDocument();
      });
    });
  });

  describe('Book Detail Inspection & Keyboard Accessibility', () => {
    it('opens book detail view on selection and allows keyboard dismissal', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-detail-list',
        }),
        json: async () => ({
          items: [mockBook1],
          next_cursor: null,
        }),
      } as Response);

      renderCatalogSearch();

      fireEvent.click(screen.getByRole('button', { name: /search catalog/i }));

      await waitFor(() => {
        expect(
          screen.getByText('Designing Data-Intensive Applications'),
        ).toBeInTheDocument();
      });

      // Inspect book details
      const inspectButton = screen.getByRole('button', {
        name: /inspect bibliographic details|view details for designing data/i,
      });
      fireEvent.click(inspectButton);

      // Detail dialog is open
      const dialog = screen.getByRole('dialog', {
        name: /designing data-intensive applications/i,
      });
      expect(dialog).toBeInTheDocument();

      // Metadata verified in detail view
      expect(within(dialog).getByText(/Martin Kleppmann/i)).toBeInTheDocument();
      expect(within(dialog).getByText(/978-1449373320/i)).toBeInTheDocument();
      expect(within(dialog).getByText(/2017/i)).toBeInTheDocument();
      expect(
        within(dialog).getByText(/physical copies and shelf availability are tracked by inventory/i),
      ).toBeInTheDocument();

      // Dismiss dialog via Escape key
      fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });

    it('submits search via keyboard Enter press in search input', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-ID': 'req-enter-key',
        }),
        json: async () => ({
          items: [mockBook1],
          next_cursor: null,
        }),
      } as Response);

      renderCatalogSearch();

      const searchInput = screen.getByLabelText(/search catalog/i);
      fireEvent.change(searchInput, { target: { value: 'Martin' } });
      fireEvent.submit(searchInput.closest('form')!);

      await waitFor(() => {
        expect(
          screen.getByText('Designing Data-Intensive Applications'),
        ).toBeInTheDocument();
      });
    });
  });

  describe('Application Shell Navigation Integration', () => {
    it('navigates to catalog view when Catalog link is clicked in AppShell', async () => {
      render(
        <TokenProvider>
          <App initialAuthenticated={true} />
        </TokenProvider>,
      );

      // Find Catalog navigation link in primary nav
      const catalogNavLinks = screen.getAllByRole('link', { name: /catalog/i });
      const catalogNav = catalogNavLinks[0]!;
      expect(catalogNav).toBeInTheDocument();

      // Click Catalog tab
      fireEvent.click(catalogNav);

      // App heading updates to Catalog
      await waitFor(() => {
        expect(
          screen.getByRole('heading', { level: 1, name: /bibliographic catalog/i }),
        ).toBeInTheDocument();
      });

      // Catalog search form is rendered
      expect(screen.getByLabelText(/search catalog/i)).toBeInTheDocument();
    });
  });
});
