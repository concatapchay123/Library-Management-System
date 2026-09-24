import { useState, useEffect, useContext, useCallback } from 'react';
import { useTokens } from '../../shared/tokens';
import {
  Book,
  BookCopy,
  Location,
  CopyStatusHistoryRecord,
  CopyStatusTransition,
  ProblemDetails,
  apiClient,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import {
  Button,
  LoadingSkeleton,
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { CopyRegistrationForm } from './CopyRegistrationForm';
import { LocationAssignmentForm } from './LocationAssignmentForm';
import { CopyStatusControls } from './CopyStatusControls';
import { StatusHistoryView } from './StatusHistoryView';
import {
  CopyRegistrationFormValues,
  LocationAssignmentFormValues,
} from './types';

export interface InventoryWorkspaceProps {
  initialBook?: Book;
  initialCopyId?: string;
}

const defaultBook: Book = {
  book_id: 'b1111111-1111-4111-8111-111111111111',
  title: 'Designing Data-Intensive Applications',
  authors: ['Martin Kleppmann'],
  isbn: '978-1449373320',
  published_year: 2017,
};

/**
 * Inventory & Physical Copy Management Workspace (FE-006).
 *
 * Adheres to domain boundaries and UI invariants:
 * - Strictly separates bibliographic work facts from physical copy status.
 * - Single-column forms with semantic spacing and explicit labels.
 * - Exactly one primary CTA per workflow panel.
 * - Only server-defined permitted status actions are rendered.
 * - Append-only, visibly read-only status history identifying actor, reason, and time.
 * - Surfaces stable RFC Problem Details alongside affected controls.
 */
export function InventoryWorkspace({
  initialBook = defaultBook,
  initialCopyId,
}: InventoryWorkspaceProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [book] = useState<Book>(initialBook);
  const [locations, setLocations] = useState<Location[]>([]);
  const [isLoadingLocations, setIsLoadingLocations] = useState(true);
  const [locationsError, setLocationsError] = useState<ProblemDetails | Error | null>(null);

  const [copies, setCopies] = useState<BookCopy[]>([]);
  const [isLoadingCopies, setIsLoadingCopies] = useState(true);
  const [copiesError, setCopiesError] = useState<ProblemDetails | Error | null>(null);

  const [selectedCopyId, setSelectedCopyId] = useState<string | null>(initialCopyId ?? null);
  const [history, setHistory] = useState<CopyStatusHistoryRecord[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<ProblemDetails | Error | null>(null);

  // Fetch locations
  const loadLocations = useCallback(async () => {
    setIsLoadingLocations(true);
    setLocationsError(null);
    try {
      const response = await apiClient.locations.list({ token });
      setLocations(response.items || []);
    } catch (err) {
      setLocationsError(err as ProblemDetails | Error);
    } finally {
      setIsLoadingLocations(false);
    }
  }, [token]);

  // Fetch copies for book
  const loadCopies = useCallback(async () => {
    if (!book.book_id) return;
    setIsLoadingCopies(true);
    setCopiesError(null);
    try {
      const response = await apiClient.copies.listForBook(book.book_id, { token });
      const copyList = response.items || [];
      setCopies(copyList);
      setSelectedCopyId((prev) => {
        if (prev) return prev;
        if (initialCopyId) return initialCopyId;
        return copyList[0]?.copy_id ?? null;
      });
    } catch (err) {
      setCopiesError(err as ProblemDetails | Error);
    } finally {
      setIsLoadingCopies(false);
    }
  }, [book.book_id, token, initialCopyId]);

  // Fetch history for selected copy
  const loadHistory = useCallback(async (copyId: string) => {
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const response = await apiClient.copies.getHistory(copyId, { token });
      setHistory(response.items || []);
    } catch (err) {
      setHistoryError(err as ProblemDetails | Error);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [token]);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

  useEffect(() => {
    loadCopies();
  }, [loadCopies]);

  useEffect(() => {
    if (selectedCopyId) {
      loadHistory(selectedCopyId);
    } else {
      setHistory([]);
    }
  }, [selectedCopyId, loadHistory]);

  const selectedCopy = copies.find((c) => c.copy_id === selectedCopyId) || null;

  // Handler: register new copy
  const handleRegisterCopy = async (values: CopyRegistrationFormValues): Promise<BookCopy> => {
    const created = await apiClient.copies.createForBook(
      book.book_id,
      {
        barcode: values.barcode,
        location_id: values.location_id,
        condition_code: values.condition_code || 'good',
      },
      { token },
    );
    setCopies((prev) => [...prev, created]);
    setSelectedCopyId(created.copy_id);
    return created;
  };

  // Handler: update location & condition
  const handleUpdateLocation = async (
    copyId: string,
    values: LocationAssignmentFormValues,
  ): Promise<BookCopy> => {
    const updated = await apiClient.copies.update(
      copyId,
      {
        location_id: values.location_id,
        condition_code: values.condition_code,
      },
      { token },
    );
    setCopies((prev) => prev.map((c) => (c.copy_id === copyId ? updated : c)));
    return updated;
  };

  // Handler: transition copy status
  const handleTransitionStatus = async (
    copyId: string,
    transition: CopyStatusTransition,
  ): Promise<BookCopy> => {
    const updated = await apiClient.copies.transitionStatus(copyId, transition, { token });
    setCopies((prev) => prev.map((c) => (c.copy_id === copyId ? updated : c)));
    // Refresh history
    await loadHistory(copyId);
    return updated;
  };

  const getLocationName = (locId: string) => {
    const loc = locations.find((l) => l.location_id === locId);
    return loc ? `${loc.name} (${loc.code})` : locId;
  };

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
      {/* Bibliographic Domain Boundary Notice */}
      <StatusMessage status="info" title="Inventory Domain Boundary">
        <span>
          Bibliographic title records represent the intellectual work; physical copies are individually
          tracked shelf inventory items with unique barcodes and locations.
        </span>
      </StatusMessage>

      {/* Bibliographic Book Overview Card */}
      <div
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          borderRadius: tokens.radius.xl,
          border: `1px solid ${tokens.colors.border}`,
          padding: tokens.spacing.xl,
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.md,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap' }}>
          <div>
            <span
              style={{
                fontSize: tokens.typography.fontSizes.xs,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textMuted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                display: 'block',
              }}
            >
              Selected Bibliographic Title
            </span>
            <h2
              style={{
                margin: 0,
                marginTop: tokens.spacing.xs,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xl,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              {book.title}
            </h2>
          </div>
          <span
            style={{
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
              fontFamily: tokens.typography.fontFamily,
            }}
          >
            ISBN: <code style={{ fontFamily: 'monospace' }}>{book.isbn || 'N/A'}</code>
          </span>
        </div>

        <div style={{ display: 'flex', gap: tokens.spacing.xl, flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>Authors:</span>{' '}
            <span style={{ fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textPrimary }}>
              {book.authors?.join(', ') || 'Unknown'}
            </span>
          </div>
          <div>
            <span style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>Year:</span>{' '}
            <span style={{ fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textPrimary }}>
              {book.published_year ?? 'Unspecified'}
            </span>
          </div>
        </div>
      </div>

      {/* Physical Copies Overview Table / Selector */}
      <div
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          borderRadius: tokens.radius.xl,
          border: `1px solid ${tokens.colors.border}`,
          padding: tokens.spacing.xl,
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.md,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3
            style={{
              margin: 0,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Tracked Physical Copies ({copies.length})
          </h3>
        </div>

        {isLoadingCopies ? (
          <LoadingSkeleton lines={3} ariaLabel="Loading copies..." />
        ) : copiesError ? (
          <ProblemDetailsRenderer error={copiesError} onRetry={loadCopies} isSafeToRetry={true} />
        ) : copies.length === 0 ? (
          <p style={{ margin: 0, fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textMuted }}>
            No physical copies registered for this title yet. Use the form below to register the first copy.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
            {copies.map((copy) => {
              const isSelected = copy.copy_id === selectedCopyId;
              return (
                <div
                  key={copy.copy_id}
                  style={{
                    backgroundColor: isSelected ? tokens.colors.surfaceElevated : tokens.colors.surface,
                    border: `1px solid ${isSelected ? tokens.colors.primary : tokens.colors.border}`,
                    borderRadius: tokens.radius.md,
                    padding: tokens.spacing.md,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: tokens.spacing.md,
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
                      <strong style={{ fontFamily: 'monospace', fontSize: tokens.typography.fontSizes.sm }}>
                        {copy.barcode}
                      </strong>
                      <span
                        style={{
                          fontSize: tokens.typography.fontSizes.xs,
                          padding: '2px 6px',
                          borderRadius: tokens.radius.sm,
                          backgroundColor:
                            copy.status === 'available'
                              ? tokens.colors.status.success.bg
                              : tokens.colors.status.warning.bg,
                          color:
                            copy.status === 'available'
                              ? tokens.colors.status.success.color
                              : tokens.colors.status.warning.color,
                          fontWeight: tokens.typography.fontWeights.semibold,
                          textTransform: 'capitalize',
                        }}
                      >
                        {copy.status}
                      </span>
                    </div>
                    <span style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textSecondary }}>
                      Location: {getLocationName(copy.location_id)} • Condition: {copy.condition_code}
                    </span>
                  </div>

                  <Button
                    type="button"
                    variant={isSelected ? 'primary' : 'outline'}
                    size="sm"
                    onClick={() => setSelectedCopyId(copy.copy_id)}
                  >
                    {isSelected ? 'Managing Copy' : 'Select Copy'}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Workflow Panel 1: Copy Registration */}
      {locationsError ? (
        <ProblemDetailsRenderer error={locationsError} onRetry={loadLocations} isSafeToRetry={true} />
      ) : (
        <CopyRegistrationForm
          locations={locations}
          onSubmitCopy={handleRegisterCopy}
          isSubmitting={isLoadingLocations}
        />
      )}

      {/* Selected Copy Management Panels */}
      {selectedCopy && (
        <>
          {/* Workflow Panel 2: Location & Condition Assignment */}
          <LocationAssignmentForm
            copy={selectedCopy}
            locations={locations}
            onSubmitUpdate={handleUpdateLocation}
          />

          {/* Workflow Panel 3: Status Transition Controls */}
          <CopyStatusControls
            copy={selectedCopy}
            onSubmitTransition={handleTransitionStatus}
          />

          {/* Workflow Panel 4: Read-Only Status History View */}
          <StatusHistoryView
            history={history}
            isLoading={isLoadingHistory}
            error={historyError}
            onRetry={() => loadHistory(selectedCopy.copy_id)}
          />
        </>
      )}
    </div>
  );
}

export default InventoryWorkspace;
