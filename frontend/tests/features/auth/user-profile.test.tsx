import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { UserProfileModal } from '../../../src/features/auth/UserProfileModal';
import { TokenProvider } from '../../../src/shared/tokens';
import { apiClient } from '../../../src/shared/api';

describe('UserProfileModal Component (M-05)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <TokenProvider>
        <UserProfileModal isOpen={false} onClose={vi.fn()} />
      </TokenProvider>
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders accessible dialog, fetches and displays operator profile details', async () => {
    const mockPrincipal = {
      user_id: 'usr-1111-2222',
      organization_id: 'org-main-campus',
      session_id: 'sess-abc-xyz',
      role: 'librarian',
      permissions: ['catalog:read', 'catalog:write', 'circulation:desk'],
    };

    vi.spyOn(apiClient.auth, 'getCurrentPrincipal').mockResolvedValue(mockPrincipal);

    render(
      <TokenProvider>
        <UserProfileModal isOpen={true} onClose={vi.fn()} accessToken="test-token" />
      </TokenProvider>
    );

    expect(screen.getByRole('dialog', { name: /hồ sơ cán bộ/i })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/đang tải/i);

    await waitFor(() => {
      expect(screen.getByText('usr-1111-2222')).toBeInTheDocument();
      expect(screen.getByText('org-main-campus')).toBeInTheDocument();
      expect(screen.getByText('sess-abc-xyz')).toBeInTheDocument();
      expect(screen.getByText('catalog:read')).toBeInTheDocument();
      expect(screen.getByText('catalog:write')).toBeInTheDocument();
      expect(screen.getByText('circulation:desk')).toBeInTheDocument();
    });
  });

  it('renders error alert when principal lookup fails', async () => {
    vi.spyOn(apiClient.auth, 'getCurrentPrincipal').mockRejectedValue(
      new Error('Phiên làm việc đã hết hạn.')
    );

    render(
      <TokenProvider>
        <UserProfileModal isOpen={true} onClose={vi.fn()} accessToken="invalid-token" />
      </TokenProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/phiên làm việc đã hết hạn/i);
    });
  });

  it('closes on Escape key press or close button click', () => {
    vi.spyOn(apiClient.auth, 'getCurrentPrincipal').mockResolvedValue({
      user_id: 'u1',
      organization_id: 'o1',
      role: 'admin',
    });

    const handleClose = vi.fn();
    render(
      <TokenProvider>
        <UserProfileModal isOpen={true} onClose={handleClose} />
      </TokenProvider>
    );

    const closeButtons = screen.getAllByRole('button', { name: /đóng/i });
    expect(closeButtons[0]).toBeDefined();
    fireEvent.click(closeButtons[0]!);
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);
  });
});
