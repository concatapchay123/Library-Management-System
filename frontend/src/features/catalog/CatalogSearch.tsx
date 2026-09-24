import React, { useState, useContext, useRef } from 'react';
import { Book, ProblemDetails, apiClient } from '../../shared/api';
import { useTokens } from '../../shared/tokens';
import {
  Button,
  Input,
  LoadingSkeleton,
  EmptyState,
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { AuthContext } from '../auth/context';
import { BookDetail } from './BookDetail';
import { CatalogFilterValues, CatalogViewStatus } from './types';

export interface CatalogSearchProps {
  initialTitle?: string;
  initialIsbn?: string;
}

/**
 * Accessible Catalog Search and Bibliographic Book Browsing Screen (FE-005).
 *
 * Adheres strictly to design invariants:
 * - Jakob's Law: Familiar search pattern with prominent primary search action.
 * - Hick's Law: Single visual primary action ("Search Catalog"), secondary actions do not compete.
 * - Law of Proximity: Spacing follows semantic progression (label 12px, group 24px, submit 32px).
 * - Miller's Law: Clean single-column layout with <= 7 fields.
 * - Von Restorff: Isolated primary CTA for catalog search.
 * - Anti-super-minimalism: Explains difference between bibliographic records and physical copies.
 * - Cursor continuation: Strictly preserves active search filters across pages.
 */
export function CatalogSearch({ initialTitle = '', initialIsbn = '' }: CatalogSearchProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  // Filter input state
  const [filters, setFilters] = useState<CatalogFilterValues>({
    title: initialTitle,
    isbn: initialIsbn,
  });

  // Active filters applied to the current query (used for cursor pagination and retry)
  const [appliedFilters, setAppliedFilters] = useState<CatalogFilterValues>({
    title: initialTitle,
    isbn: initialIsbn,
  });

  // Catalog items & pagination state
  const [status, setStatus] = useState<CatalogViewStatus>('idle');
  const [items, setItems] = useState<Book[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<ProblemDetails | Error | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Detail inspection state
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const lastTriggerRef = useRef<HTMLButtonElement | null>(null);

  /**
   * Executes a catalog search request.
   */
  async function executeSearch(targetFilters: CatalogFilterValues) {
    setStatus('loading');
    setError(null);
    setHasSearched(true);
    setAppliedFilters(targetFilters);

    try {
      const response = await apiClient.books.list(
        {
          title: targetFilters.title.trim() || undefined,
          isbn: targetFilters.isbn.trim() || undefined,
          limit: 20,
        },
        { token: token || undefined },
      );

      setItems(response.items);
      setNextCursor(response.next_cursor);
      setStatus('success');
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setStatus('error');
    }
  }

  /**
   * Form submission handler.
   */
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    executeSearch(filters);
  }

  /**
   * Resets all search filters and results back to initial state.
   */
  function handleReset() {
    setFilters({ title: '', isbn: '' });
    setAppliedFilters({ title: '', isbn: '' });
    setItems([]);
    setNextCursor(null);
    setError(null);
    setHasSearched(false);
    setStatus('idle');
  }

  /**
   * Retries the previous search request using the last applied filters.
   */
  function handleRetry() {
    executeSearch(appliedFilters);
  }

  /**
   * Continues pagination via cursor while preserving applied filters.
   */
  async function handleLoadMore() {
    if (!nextCursor || status === 'loading' || status === 'loadingMore') {
      return;
    }

    setStatus('loadingMore');
    setError(null);

    try {
      const response = await apiClient.books.list(
        {
          title: appliedFilters.title.trim() || undefined,
          isbn: appliedFilters.isbn.trim() || undefined,
          cursor: nextCursor,
          limit: 20,
        },
        { token: token || undefined },
      );

      setItems((prev) => [...prev, ...response.items]);
      setNextCursor(response.next_cursor);
      setStatus('success');
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setStatus('error');
    }
  }

  /**
   * Opens the bibliographic book detail modal.
   */
  function handleInspectBook(book: Book, triggerElement: HTMLButtonElement | null) {
    lastTriggerRef.current = triggerElement;
    setSelectedBook(book);
    setIsDetailOpen(true);
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.semantic.groupToGroup,
        maxWidth: '780px',
        width: '100%',
        margin: '0 auto',
      }}
    >
      {/* Bibliographic Notice Landmark: Distinguishes bibliographic books from physical copies */}
      <StatusMessage status="info" title="Bibliographic Catalog & Metadata">
        Bibliographic records represent intellectual works, titles, and edition metadata across
        the library system. Physical copies, shelf inventory, and circulation loans are managed at the
        Circulation Desk.
      </StatusMessage>

      {/* Main Catalog Search Form Card */}
      <div
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          borderRadius: tokens.radius.xl,
          border: `1px solid ${tokens.colors.border}`,
          padding: tokens.spacing.xl,
          boxSizing: 'border-box',
        }}
      >
        <div style={{ marginBottom: tokens.spacing.lg }}>
          <h2
            style={{
              margin: 0,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.xl,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Search Catalog
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
            Find bibliographic records by title or ISBN. Results show catalog metadata without
            inventory lock status.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.semantic.groupToGroup,
          }}
        >
          {/* Primary Field: Book Title / Keyword Query */}
          <Input
            id="catalog-search-query"
            label="Search Catalog"
            description="Find bibliographic books by title or keywords across the catalog."
            placeholder="Search by book title, author, or ISBN (e.g. Clean Code, 978-0132350884)..."
            value={filters.title}
            onChange={(e) => setFilters({ ...filters, title: e.target.value })}
            autoComplete="off"
          />

          {/* Secondary Filter: Exact or Prefix ISBN */}
          <Input
            id="catalog-filter-isbn"
            label="Filter by ISBN"
            optional
            description="Match exact or prefix ISBN (e.g. 978-0132350884)."
            placeholder="e.g. 978-0132350884..."
            value={filters.isbn}
            onChange={(e) => setFilters({ ...filters, isbn: e.target.value })}
            autoComplete="off"
          />

          {/* Actions: Strictly 1 Primary Button (Von Restorff Isolation) */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: tokens.spacing.md,
              marginTop: tokens.spacing.xs,
              paddingTop: tokens.spacing.md,
              borderTop: `1px solid ${tokens.colors.borderMuted}`,
              flexWrap: 'wrap',
            }}
          >
            {/* The ONLY visually primary action in this region */}
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={status === 'loading'}
            >
              Search Catalog
            </Button>

            {/* Secondary Action */}
            <Button
              type="button"
              variant="secondary"
              size="md"
              onClick={handleReset}
              disabled={status === 'loading'}
            >
              Clear Filters
            </Button>
          </div>
        </form>
      </div>

      {/* Recoverable Error State View */}
      {status === 'error' && error && (
        <div role="region" aria-label="Catalog Error">
          <ProblemDetailsRenderer
            error={error}
            onRetry={handleRetry}
            isSafeToRetry={true}
          />
        </div>
      )}

      {/* Loading Skeleton State View */}
      {status === 'loading' && (
        <div role="region" aria-label="Loading Catalog Results" aria-busy="true">
          <LoadingSkeleton lines={3} ariaLabel="Loading catalog books..." />
        </div>
      )}

      {/* Empty State View */}
      {status === 'success' && hasSearched && items.length === 0 && (
        <EmptyState
          title="No Bibliographic Books Found"
          description="No books in the catalog matched your search criteria. Check your spelling or try searching with a different title or ISBN."
          action={{
            label: 'Clear Search',
            onAction: handleReset,
            variant: 'secondary',
          }}
        />
      )}

      {/* Results List View */}
      {items.length > 0 && (
        <section
          aria-labelledby="catalog-results-heading"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.md,
          }}
        >
          {/* Result Summary Bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`,
            }}
          >
            <h3
              id="catalog-results-heading"
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textSecondary,
              }}
            >
              {items.length} {items.length === 1 ? 'bibliographic title' : 'bibliographic titles'} found
            </h3>
            <span
              style={{
                fontSize: tokens.typography.fontSizes.xs,
                color: tokens.colors.textMuted,
              }}
            >
              Page Size: 20
            </span>
          </div>

          {/* Book Cards */}
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.md,
            }}
          >
            {items.map((book) => {
              const authorsText = book.authors && book.authors.length > 0
                ? book.authors.join(', ')
                : 'Unknown Author';

              return (
                <li
                  key={book.book_id}
                  style={{
                    backgroundColor: tokens.colors.surfaceAlt,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: tokens.radius.lg,
                    padding: tokens.spacing.lg,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: tokens.spacing.sm,
                    transition: 'border-color 150ms ease, box-shadow 150ms ease',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      gap: tokens.spacing.md,
                      flexWrap: 'wrap',
                    }}
                  >
                    <div>
                      <div
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          padding: `2px ${tokens.spacing.xs}`,
                          borderRadius: tokens.radius.sm,
                          backgroundColor: tokens.colors.surfaceElevated,
                          color: tokens.colors.textMuted,
                          fontSize: tokens.typography.fontSizes.xs,
                          fontWeight: tokens.typography.fontWeights.medium,
                          marginBottom: tokens.spacing.xs,
                        }}
                      >
                        Bibliographic Record
                      </div>
                      <h4
                        style={{
                          margin: 0,
                          fontSize: tokens.typography.fontSizes.lg,
                          fontWeight: tokens.typography.fontWeights.bold,
                          color: tokens.colors.textPrimary,
                        }}
                      >
                        {book.title}
                      </h4>
                      <p
                        style={{
                          margin: 0,
                          marginTop: tokens.spacing.xs,
                          fontSize: tokens.typography.fontSizes.sm,
                          color: tokens.colors.textSecondary,
                        }}
                      >
                        By <span style={{ color: tokens.colors.textPrimary }}>{authorsText}</span>
                      </p>
                    </div>

                    {/* Inspect Button */}
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={(e) => handleInspectBook(book, e.currentTarget)}
                      aria-label={`Inspect bibliographic details for ${book.title}`}
                    >
                      Inspect Bibliographic Details
                    </Button>
                  </div>

                  {/* Metadata Chips / Row */}
                  <div
                    style={{
                      display: 'flex',
                      gap: tokens.spacing.lg,
                      marginTop: tokens.spacing.xs,
                      paddingTop: tokens.spacing.xs,
                      borderTop: `1px solid ${tokens.colors.borderMuted}`,
                      fontSize: tokens.typography.fontSizes.xs,
                      color: tokens.colors.textMuted,
                      flexWrap: 'wrap',
                    }}
                  >
                    <span>
                      <strong>ISBN:</strong>{' '}
                      <span style={{ fontFamily: 'monospace', color: tokens.colors.textSecondary }}>
                        {book.isbn || 'None'}
                      </span>
                    </span>
                    <span>
                      <strong>Published:</strong>{' '}
                      <span style={{ color: tokens.colors.textSecondary }}>
                        {book.published_year !== null && book.published_year !== undefined
                          ? book.published_year
                          : 'Unspecified'}
                      </span>
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>

          {/* Cursor Continuation Controls */}
          {nextCursor && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                marginTop: tokens.spacing.md,
                paddingBottom: tokens.spacing.lg,
              }}
            >
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={handleLoadMore}
                disabled={status === 'loadingMore'}
              >
                {status === 'loadingMore' ? 'Loading Titles...' : 'Next Page'}
              </Button>
            </div>
          )}

          {!nextCursor && items.length > 0 && (
            <p
              style={{
                textAlign: 'center',
                margin: tokens.spacing.md,
                fontSize: tokens.typography.fontSizes.xs,
                color: tokens.colors.textMuted,
              }}
            >
              All matching catalog titles loaded.
            </p>
          )}
        </section>
      )}

      {/* Book Detail Modal */}
      <BookDetail
        book={selectedBook}
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        triggerRef={lastTriggerRef}
      />
    </div>
  );
}

export default CatalogSearch;
