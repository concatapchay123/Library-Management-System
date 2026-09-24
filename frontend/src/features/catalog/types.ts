import { Book, ProblemDetails } from '../../shared/api';

/**
 * Filter input state for catalog search form.
 */
export interface CatalogFilterValues {
  title: string;
  isbn: string;
}

/**
 * Lifecycle status of catalog search requests.
 */
export type CatalogViewStatus = 'idle' | 'loading' | 'loadingMore' | 'success' | 'error';

/**
 * Full UI state for catalog browsing.
 */
export interface CatalogState {
  status: CatalogViewStatus;
  filters: CatalogFilterValues;
  appliedFilters: CatalogFilterValues;
  items: Book[];
  nextCursor: string | null;
  selectedBook: Book | null;
  error: ProblemDetails | Error | null;
  hasSearched: boolean;
}
