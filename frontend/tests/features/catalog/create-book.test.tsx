import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CreateBookModal } from '../../../src/features/catalog/CreateBookModal';
import { TokenProvider } from '../../../src/shared/tokens';
import { apiClient, Book } from '../../../src/shared/api';

describe('CreateBookModal Component (M-05)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <TokenProvider>
        <CreateBookModal isOpen={false} onClose={vi.fn()} onSuccess={vi.fn()} />
      </TokenProvider>
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('enables submit button only when title and authors are non-empty', () => {
    render(
      <TokenProvider>
        <CreateBookModal isOpen={true} onClose={vi.fn()} onSuccess={vi.fn()} />
      </TokenProvider>
    );

    const titleInput = screen.getByLabelText(/tên sách/i);
    const authorsInput = screen.getByLabelText(/tác giả/i);
    const submitBtn = screen.getByRole('button', { name: /đăng ký sách/i });

    expect(submitBtn).toBeDisabled();

    fireEvent.change(titleInput, { target: { value: 'Refactoring' } });
    expect(submitBtn).toBeDisabled();

    fireEvent.change(authorsInput, { target: { value: 'Martin Fowler, Kent Beck' } });
    expect(submitBtn).not.toBeDisabled();
  });

  it('calls apiClient.books.create with proper payload and triggers onSuccess', async () => {
    const mockBook: Book = {
      book_id: 'b-999-created',
      title: 'Domain-Driven Design',
      isbn: '978-0321125217',
      authors: ['Eric Evans'],
      published_year: 2003,
    };

    const createSpy = vi.spyOn(apiClient.books, 'create').mockResolvedValue(mockBook);
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    render(
      <TokenProvider>
        <CreateBookModal
          isOpen={true}
          onClose={handleClose}
          onSuccess={handleSuccess}
          accessToken="sample-access-token"
        />
      </TokenProvider>
    );

    fireEvent.change(screen.getByLabelText(/tên sách/i), {
      target: { value: 'Domain-Driven Design' },
    });
    fireEvent.change(screen.getByLabelText(/tác giả/i), {
      target: { value: 'Eric Evans' },
    });
    fireEvent.change(screen.getByLabelText(/mã isbn/i), {
      target: { value: '978-0321125217' },
    });
    fireEvent.change(screen.getByLabelText(/năm xuất bản/i), {
      target: { value: '2003' },
    });

    const submitBtn = screen.getByRole('button', { name: /đăng ký sách/i });
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        {
          title: 'Domain-Driven Design',
          isbn: '978-0321125217',
          authors: ['Eric Evans'],
          published_year: 2003,
        },
        { token: 'sample-access-token' }
      );
      expect(handleSuccess).toHaveBeenCalledWith(mockBook);
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('renders error message when book creation fails', async () => {
    vi.spyOn(apiClient.books, 'create').mockRejectedValue(
      new Error('ISBN trùng lặp trong hệ thống.')
    );

    render(
      <TokenProvider>
        <CreateBookModal isOpen={true} onClose={vi.fn()} onSuccess={vi.fn()} />
      </TokenProvider>
    );

    fireEvent.change(screen.getByLabelText(/tên sách/i), { target: { value: 'Duplicate Book' } });
    fireEvent.change(screen.getByLabelText(/tác giả/i), { target: { value: 'Author' } });

    const submitBtn = screen.getByRole('button', { name: /đăng ký sách/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/isbn trùng lặp/i);
    });
  });
});
