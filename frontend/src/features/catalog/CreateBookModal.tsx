import React, { useState, useEffect, useRef } from 'react';
import { useTokens } from '../../shared/tokens';
import { apiClient, Book, BookWrite } from '../../shared/api';
import { Button, Input } from '../../shared/components';

export interface CreateBookModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newBook: Book) => void;
  accessToken?: string | null;
}

/**
 * Accessible Modal Dialog for Bibliographic Book Registration (M-05).
 *
 * Implements strict design invariants:
 * - Single-column vertical form (no zigzag multi-column layouts)
 * - Semantic spacing progression (Label 12px, Field 24px, Submit 32px)
 * - Only 1 primary action button (Von Restorff Isolation)
 * - 2:1 button whitespace padding ratio
 * - Actionable button labels (Tạo Sách / Create Book vs Hủy / Cancel)
 * - Realtime inline error feedback and keyboard accessibility (Esc + auto-focus)
 */
export function CreateBookModal({
  isOpen,
  onClose,
  onSuccess,
  accessToken,
}: CreateBookModalProps) {
  const tokens = useTokens();
  const [title, setTitle] = useState('');
  const [isbn, setIsbn] = useState('');
  const [authors, setAuthors] = useState('');
  const [publishedYear, setPublishedYear] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const initialInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTitle('');
      setIsbn('');
      setAuthors('');
      setPublishedYear('');
      setErrorMessage(null);
      setIsSubmitting(false);
      setTimeout(() => {
        initialInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const authorList = authors
    .split(',')
    .map((a) => a.trim())
    .filter((a) => a.length > 0);

  const isFormValid = title.trim().length > 0 && authorList.length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isFormValid || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    const yearNumber = publishedYear.trim() ? parseInt(publishedYear.trim(), 10) : null;
    const payload: BookWrite = {
      title: title.trim(),
      isbn: isbn.trim() || null,
      authors: authorList,
      published_year: yearNumber && !isNaN(yearNumber) ? yearNumber : null,
    };

    try {
      const created = await apiClient.books.create(payload, {
        token: accessToken ?? undefined,
      });
      setIsSubmitting(false);
      onSuccess(created);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      setErrorMessage(err instanceof Error ? err.message : 'Không thể tạo sách mới.');
    }
  }

  return (
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(18, 18, 18, 0.65)',
        backdropFilter: 'blur(2px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: tokens.spacing.md,
        boxSizing: 'border-box',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-book-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: tokens.colors.surface,
          borderRadius: tokens.radius.lg,
          border: `1px solid ${tokens.colors.border}`,
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.2)',
          width: '100%',
          maxWidth: '560px',
          boxSizing: 'border-box',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: `${tokens.spacing.lg} ${tokens.spacing.xl}`,
            borderBottom: `1px solid ${tokens.colors.border}`,
            backgroundColor: tokens.colors.surfaceAlt,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
            <span aria-hidden="true" style={{ fontSize: '20px' }}>
              📚
            </span>
            <div>
              <h2
                id="create-book-title"
                style={{
                  margin: 0,
                  fontSize: tokens.typography.fontSizes.lg,
                  fontWeight: tokens.typography.fontWeights.semibold,
                  color: tokens.colors.textPrimary,
                  fontFamily: tokens.typography.fontFamily,
                }}
              >
                Đăng Ký Sách Mới
              </h2>
              <p
                style={{
                  margin: 0,
                  fontSize: tokens.typography.fontSizes.xs,
                  color: tokens.colors.textMuted,
                  fontFamily: tokens.typography.fontFamily,
                }}
              >
                Register New Bibliographic Book Title
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            style={{
              background: 'transparent',
              border: 'none',
              fontSize: '18px',
              cursor: 'pointer',
              color: tokens.colors.textMuted,
              padding: tokens.spacing.xs,
              borderRadius: tokens.radius.sm,
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Body / Form */}
        <form
          onSubmit={handleSubmit}
          style={{
            padding: `${tokens.spacing.xl} ${tokens.spacing.xl}`,
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.semantic.groupToGroup,
          }}
        >
          {errorMessage && (
            <div
              role="alert"
              style={{
                padding: tokens.spacing.md,
                backgroundColor: '#fef2f2',
                border: '1px solid #f87171',
                borderRadius: tokens.radius.md,
                color: '#b91c1c',
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              {errorMessage}
            </div>
          )}

          {/* Title (Required) */}
          <Input
            id="create-book-title-input"
            ref={initialInputRef}
            label="Tên Sách (Title)"
            description="Tên đầy đủ của tác phẩm thư mục."
            placeholder="e.g. Design Patterns: Elements of Reusable Object-Oriented Software"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoComplete="off"
          />

          {/* Authors (Required, comma separated) */}
          <Input
            id="create-book-authors-input"
            label="Tác Giả (Authors)"
            description="Tên một hoặc nhiều tác giả, phân tách bằng dấu phẩy."
            placeholder="e.g. Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides"
            value={authors}
            onChange={(e) => setAuthors(e.target.value)}
            required
            autoComplete="off"
          />

          {/* ISBN (Optional) */}
          <Input
            id="create-book-isbn-input"
            label="Mã ISBN"
            optional
            description="Mã số tiêu chuẩn quốc tế cho sách (10 hoặc 13 chữ số)."
            placeholder="e.g. 978-0201633610"
            value={isbn}
            onChange={(e) => setIsbn(e.target.value)}
            autoComplete="off"
          />

          {/* Published Year (Optional) */}
          <Input
            id="create-book-year-input"
            label="Năm Xuất Bản (Published Year)"
            optional
            description="Năm phát hành ấn bản thư mục."
            placeholder="e.g. 1994"
            type="number"
            value={publishedYear}
            onChange={(e) => setPublishedYear(e.target.value)}
            autoComplete="off"
          />

          {/* Actions */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              gap: tokens.spacing.md,
              marginTop: tokens.spacing.md,
              paddingTop: tokens.spacing.md,
              borderTop: `1px solid ${tokens.colors.border}`,
            }}
          >
            <Button
              type="button"
              variant="secondary"
              size="md"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={!isFormValid || isSubmitting}
            >
              {isSubmitting ? 'Đang Đăng Ký...' : 'Đăng Ký Sách'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
