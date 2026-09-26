import React, { useState, useEffect, useRef } from 'react';
import { useTokens } from '../../shared/tokens';
import { apiClient, Reservation, ReservationCreateWrite } from '../../shared/api';
import { Button, Input, Dialog } from '../../shared/components';

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
 * - Built on top of accessible Dialog primitive with full Tab/Shift+Tab focus trap
 * - Single-column vertical form (no multi-column zigzag)
 * - Semantic spacing progression (Label 12px, Field 24px, Submit 32px)
 * - Only 1 primary action button (Von Restorff Isolation)
 * - 2:1 button whitespace padding ratio
 * - Actionable button labels (Tạo Đặt Giữ vs Hủy)
 * - Inline error alerts and full keyboard accessibility
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
    }
  }, [isOpen]);

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
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Đặt Giữ Sách Mới"
      description="Place New Book Reservation & Queue Hold"
      maxWidth="560px"
    >
      <form
        onSubmit={handleSubmit}
        style={{
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
    </Dialog>
  );
}
