import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CreateReservationModal } from '../../../src/features/inbox/CreateReservationModal';
import { TokenProvider } from '../../../src/shared/tokens';
import { apiClient, Reservation } from '../../../src/shared/api';

describe('CreateReservationModal Component (M-05)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <TokenProvider>
        <CreateReservationModal isOpen={false} onClose={vi.fn()} onSuccess={vi.fn()} />
      </TokenProvider>
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('enables submit button when bookId is provided', () => {
    render(
      <TokenProvider>
        <CreateReservationModal isOpen={true} onClose={vi.fn()} onSuccess={vi.fn()} />
      </TokenProvider>
    );

    const bookIdInput = screen.getByLabelText(/mã sách thư mục/i);
    const submitBtn = screen.getByRole('button', { name: /tạo đặt giữ/i });

    expect(submitBtn).toBeDisabled();

    fireEvent.change(bookIdInput, { target: { value: 'b-12345' } });
    expect(submitBtn).not.toBeDisabled();
  });

  it('calls apiClient.reservations.create with payload and invokes onSuccess', async () => {
    const mockReservation: Reservation = {
      reservation_id: 'res-999-new',
      organization_id: 'org-test',
      book_id: 'b-12345',
      requester_user_id: 'u-55555',
      status: 'pending',
      created_at: '2026-09-26T10:00:00Z',
      queue_position: 1,
    };

    const createSpy = vi
      .spyOn(apiClient.reservations, 'create')
      .mockResolvedValue(mockReservation);
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    render(
      <TokenProvider>
        <CreateReservationModal
          isOpen={true}
          onClose={handleClose}
          onSuccess={handleSuccess}
          accessToken="mock-token-xyz"
        />
      </TokenProvider>
    );

    fireEvent.change(screen.getByLabelText(/mã sách thư mục/i), {
      target: { value: 'b-12345' },
    });
    fireEvent.change(screen.getByLabelText(/mã bản sao cụ thể/i), {
      target: { value: 'c-67890' },
    });
    fireEvent.change(screen.getByLabelText(/mã độc giả yêu cầu/i), {
      target: { value: 'u-55555' },
    });

    const submitBtn = screen.getByRole('button', { name: /tạo đặt giữ/i });
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        {
          book_id: 'b-12345',
          copy_id: 'c-67890',
          requester_user_id: 'u-55555',
        },
        { token: 'mock-token-xyz' }
      );
      expect(handleSuccess).toHaveBeenCalledWith(mockReservation);
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('displays inline error alert if reservations.create rejects', async () => {
    vi.spyOn(apiClient.reservations, 'create').mockRejectedValue(
      new Error('Sách này hiện đã có số lượng giữ tối đa.')
    );

    render(
      <TokenProvider>
        <CreateReservationModal isOpen={true} onClose={vi.fn()} onSuccess={vi.fn()} />
      </TokenProvider>
    );

    fireEvent.change(screen.getByLabelText(/mã sách thư mục/i), {
      target: { value: 'b-full' },
    });

    const submitBtn = screen.getByRole('button', { name: /tạo đặt giữ/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/số lượng giữ tối đa/i);
    });
  });
});
