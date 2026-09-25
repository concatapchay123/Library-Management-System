import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChangePasswordModal } from '../../../src/features/auth/ChangePasswordModal';
import { TokenProvider } from '../../../src/shared/tokens';
import * as authApi from '../../../src/features/auth/authApi';

describe('ChangePasswordModal Component (M-05 & M-07)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <TokenProvider>
        <ChangePasswordModal isOpen={false} onClose={vi.fn()} />
      </TokenProvider>
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders accessible dialog with 1-column form when isOpen is true', () => {
    render(
      <TokenProvider>
        <ChangePasswordModal isOpen={true} onClose={vi.fn()} />
      </TokenProvider>
    );

    const dialog = screen.getByRole('dialog', { name: /đổi mật khẩu/i });
    expect(dialog).toBeInTheDocument();

    const currentPwdInput = screen.getByLabelText(/mật khẩu hiện tại/i);
    const newPwdInput = screen.getByLabelText(/^mật khẩu mới/i);
    const confirmPwdInput = screen.getByLabelText(/xác nhận mật khẩu mới/i);
    const submitBtn = screen.getByRole('button', { name: /cập nhật mật khẩu/i });

    expect(currentPwdInput).toBeInTheDocument();
    expect(newPwdInput).toBeInTheDocument();
    expect(confirmPwdInput).toBeInTheDocument();
    expect(submitBtn).toBeInTheDocument();
    expect(submitBtn).toBeDisabled();
  });

  it('enables submit button only when all password rules and match conditions are satisfied', () => {
    render(
      <TokenProvider>
        <ChangePasswordModal isOpen={true} onClose={vi.fn()} />
      </TokenProvider>
    );

    const currentPwdInput = screen.getByLabelText(/mật khẩu hiện tại/i);
    const newPwdInput = screen.getByLabelText(/^mật khẩu mới/i);
    const confirmPwdInput = screen.getByLabelText(/xác nhận mật khẩu mới/i);
    const submitBtn = screen.getByRole('button', { name: /cập nhật mật khẩu/i });

    // Step 1: Fill current password
    fireEvent.change(currentPwdInput, { target: { value: 'OldPassword123!' } });
    expect(submitBtn).toBeDisabled();

    // Step 2: Fill short new password
    fireEvent.change(newPwdInput, { target: { value: 'short' } });
    expect(submitBtn).toBeDisabled();

    // Step 3: Satisfy all rules: 8+ chars, uppercase, digit/special
    fireEvent.change(newPwdInput, { target: { value: 'NewSecretPass123!' } });
    expect(submitBtn).toBeDisabled(); // Passwords don't match yet

    // Step 4: Fill matching confirmation
    fireEvent.change(confirmPwdInput, { target: { value: 'NewSecretPass123!' } });
    expect(submitBtn).not.toBeDisabled();
  });

  it('calls authApi.changePassword and renders success message upon submission', async () => {
    const changePasswordSpy = vi.spyOn(authApi, 'changePassword').mockResolvedValue(undefined);
    const handleClose = vi.fn();
    const handleSuccess = vi.fn();

    render(
      <TokenProvider>
        <ChangePasswordModal
          isOpen={true}
          onClose={handleClose}
          onSuccess={handleSuccess}
          accessToken="mock-token-xyz"
        />
      </TokenProvider>
    );

    fireEvent.change(screen.getByLabelText(/mật khẩu hiện tại/i), {
      target: { value: 'CurrentPass123!' },
    });
    fireEvent.change(screen.getByLabelText(/^mật khẩu mới/i), {
      target: { value: 'SuperNewPass456#' },
    });
    fireEvent.change(screen.getByLabelText(/xác nhận mật khẩu mới/i), {
      target: { value: 'SuperNewPass456#' },
    });

    const submitBtn = screen.getByRole('button', { name: /cập nhật mật khẩu/i });
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    expect(changePasswordSpy).toHaveBeenCalledWith(
      {
        current_password: 'CurrentPass123!',
        new_password: 'SuperNewPass456#',
      },
      'mock-token-xyz'
    );

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/thành công/i);
    });
  });

  it('displays inline error alert if changePassword rejects', async () => {
    vi.spyOn(authApi, 'changePassword').mockRejectedValue(new Error('Mật khẩu hiện tại không chính xác.'));

    render(
      <TokenProvider>
        <ChangePasswordModal isOpen={true} onClose={vi.fn()} accessToken="mock-token" />
      </TokenProvider>
    );

    fireEvent.change(screen.getByLabelText(/mật khẩu hiện tại/i), {
      target: { value: 'WrongPass123!' },
    });
    fireEvent.change(screen.getByLabelText(/^mật khẩu mới/i), {
      target: { value: 'ValidNewPass456!' },
    });
    fireEvent.change(screen.getByLabelText(/xác nhận mật khẩu mới/i), {
      target: { value: 'ValidNewPass456!' },
    });

    const submitBtn = screen.getByRole('button', { name: /cập nhật mật khẩu/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/mật khẩu hiện tại không chính xác/i);
    });
  });

  it('closes on Escape key press or close button click', () => {
    const handleClose = vi.fn();
    render(
      <TokenProvider>
        <ChangePasswordModal isOpen={true} onClose={handleClose} />
      </TokenProvider>
    );

    const closeBtn = screen.getByRole('button', { name: /đóng/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);
  });
});
