import React, { useState, useEffect, useRef } from 'react';
import { useTokens } from '../../shared/tokens';
import { apiClient, Reservation, ReservationCreateWrite } from '../../shared/api';
import { Button, Input } from '../../shared/components';

export interface CreateReservationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newReservation: Reservation) => void;
  accessToken?: string | null;
}

/**
 * Accessible Modal Dialog for Creating Book Hold / Reservation (M-05).
 *
 * Implements strict design invariants:
 * - Single-column vertical form (no multi-column zigzag)
 * - Semantic spacing progression (Label 12px, Field 24px, Submit 32px)
 * - Only 1 primary action button (Von Restorff Isolation)
 * - 2:1 button whitespace padding ratio
 * - Actionable button labels (Tạo Đặt Giữ / Place Hold vs Hủy / Cancel)
 * - Inline error alerts and full keyboard accessibility (Esc + focus management)
 */
export function CreateReservationModal({
  isOpen,
  onClose,
  onSuccess,
  accessToken,
}: CreateReservationModalProps) {
  const tokens = useTokens();
  const [bookId, setBookId] = useState('');
  const [copyId, setCopyId] = useState('');
  const [requesterUserId, setRequesterUserId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const initialInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setBookId('');
      setCopyId('');
      setRequesterUserId('');
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

  const isFormValid = bookId.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isFormValid || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    const payload: ReservationCreateWrite = {
      book_id: bookId.trim(),
      copy_id: copyId.trim() || undefined,
      requester_user_id: requesterUserId.trim() || undefined,
    };

    try {
      const created = await apiClient.reservations.create(payload, {
        token: accessToken ?? undefined,
      });
      setIsSubmitting(false);
      onSuccess(created);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      setErrorMessage(err instanceof Error ? err.message : 'Không thể tạo yêu cầu đặt giữ sách.');
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
        aria-labelledby="create-reservation-title"
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
              📌
            </span>
            <div>
              <h2
                id="create-reservation-title"
                style={{
                  margin: 0,
                  fontSize: tokens.typography.fontSizes.lg,
                  fontWeight: tokens.typography.fontWeights.semibold,
                  color: tokens.colors.textPrimary,
                  fontFamily: tokens.typography.fontFamily,
                }}
              >
                Đặt Giữ Sách Mới
              </h2>
              <p
                style={{
                  margin: 0,
                  fontSize: tokens.typography.fontSizes.xs,
                  color: tokens.colors.textMuted,
                  fontFamily: tokens.typography.fontFamily,
                }}
              >
                Place New Book Reservation &amp; Queue Hold
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

          {/* Book ID (Required) */}
          <Input
            id="create-reservation-book-id"
            ref={initialInputRef}
            label="Mã Sách Thư Mục (Book ID)"
            description="UUID hoặc mã định danh của sách cần đặt trước."
            placeholder="e.g. b1234567-0000-0000-0000-000000000001"
            value={bookId}
            onChange={(e) => setBookId(e.target.value)}
            required
            autoComplete="off"
          />

          {/* Copy ID (Optional) */}
          <Input
            id="create-reservation-copy-id"
            label="Mã Bản Sao Cụ Thể (Copy ID)"
            optional
            description="Để trống nếu muốn xếp hàng tự động cho bất kỳ bản sao nào khả dụng."
            placeholder="e.g. c1234567-0000-0000-0000-000000000001"
            value={copyId}
            onChange={(e) => setCopyId(e.target.value)}
            autoComplete="off"
          />

          {/* Requester User ID (Optional) */}
          <Input
            id="create-reservation-user-id"
            label="Mã Độc Giả Yêu Cầu (Requester User ID)"
            optional
            description="Để trống để sử dụng tài khoản cán bộ/độc giả đang đăng nhập."
            placeholder="e.g. u1234567-0000-0000-0000-000000000001"
            value={requesterUserId}
            onChange={(e) => setRequesterUserId(e.target.value)}
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
              {isSubmitting ? 'Đang Tạo Yêu Cầu...' : 'Tạo Đặt Giữ'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
