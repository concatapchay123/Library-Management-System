import React from 'react';
import { Book } from '../../shared/api';
import { useTokens } from '../../shared/tokens';
import { Dialog, Button } from '../../shared/components';

export interface BookDetailProps {
  book: Book | null;
  isOpen: boolean;
  onClose: () => void;
  triggerRef?: React.RefObject<HTMLElement | null>;
}

/**
 * Accessible detail view for inspecting bibliographic book records.
 *
 * Adheres to domain boundaries and UI invariants:
 * - Does not expose copy inventory or availability beyond bibliographic contract.
 * - Explicitly explains that records represent intellectual works, not shelf items.
 * - Fully keyboard-accessible modal dialog with Escape dismissal and focus restoration.
 */
export function BookDetail({ book, isOpen, onClose, triggerRef }: BookDetailProps) {
  const tokens = useTokens();

  if (!book) {
    return null;
  }

  const authorsText = book.authors && book.authors.length > 0
    ? book.authors.join(', ')
    : 'Unknown Author';

  const isbnText = book.isbn || 'None registered';
  const yearText = book.published_year !== null && book.published_year !== undefined
    ? String(book.published_year)
    : 'Unspecified';

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={book.title}
      description="Bibliographic Title Record"
      triggerRef={triggerRef}
      maxWidth="580px"
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.lg,
        }}
      >
        {/* Bibliographic Boundary Notice */}
        <div
          role="note"
          style={{
            backgroundColor: tokens.colors.surfaceElevated,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: tokens.radius.md,
            padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
            fontSize: tokens.typography.fontSizes.xs,
            color: tokens.colors.textSecondary,
            lineHeight: tokens.typography.lineHeights.normal,
          }}
        >
          <strong style={{ color: tokens.colors.textPrimary, display: 'block', marginBottom: '2px' }}>
            Bibliographic Work Notice:
          </strong>
          Physical copies and shelf availability are tracked by inventory, not bibliographic title records.
        </div>

        {/* Metadata Details Grid / List */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.sm,
            backgroundColor: tokens.colors.surfaceAlt,
            borderRadius: tokens.radius.md,
            padding: tokens.spacing.md,
            border: `1px solid ${tokens.colors.borderMuted}`,
          }}
        >
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
              Authors
            </span>
            <span
              style={{
                fontSize: tokens.typography.fontSizes.sm,
                color: tokens.colors.textPrimary,
                fontWeight: tokens.typography.fontWeights.medium,
              }}
            >
              {authorsText}
            </span>
          </div>

          <div style={{ display: 'flex', gap: tokens.spacing.xl, flexWrap: 'wrap' }}>
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
                ISBN
              </span>
              <span
                style={{
                  fontSize: tokens.typography.fontSizes.sm,
                  color: tokens.colors.textPrimary,
                  fontFamily: 'monospace',
                }}
              >
                {isbnText}
              </span>
            </div>

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
                Published Year
              </span>
              <span
                style={{
                  fontSize: tokens.typography.fontSizes.sm,
                  color: tokens.colors.textPrimary,
                }}
              >
                {yearText}
              </span>
            </div>
          </div>

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
              Bibliographic ID
            </span>
            <span
              style={{
                fontSize: tokens.typography.fontSizes.xs,
                color: tokens.colors.textSecondary,
                fontFamily: 'monospace',
              }}
            >
              {book.book_id}
            </span>
          </div>
        </div>

        {/* Dialog Actions */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: tokens.spacing.md,
            marginTop: tokens.spacing.xs,
          }}
        >
          <Button variant="secondary" size="md" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export default BookDetail;
