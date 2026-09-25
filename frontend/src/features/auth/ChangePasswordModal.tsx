import React, { useState, useEffect, useRef } from 'react';
import { useTokens } from '../../shared/tokens';
import { changePassword } from './authApi';

export interface ChangePasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
  accessToken?: string | null;
  onSuccess?: () => void;
}

export function ChangePasswordModal({
  isOpen,
  onClose,
  accessToken,
  onSuccess,
}: ChangePasswordModalProps) {
  const tokens = useTokens();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const initialInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setErrorMessage(null);
      setSuccessMessage(null);
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

  // Realtime password checklist validation
  const hasMinLength = newPassword.length >= 8;
  const hasUpperCase = /[A-Z]/.test(newPassword);
  const hasSpecialOrDigit = /[0-9!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/.test(newPassword);
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;
  const isFormValid = hasMinLength && hasUpperCase && hasSpecialOrDigit && passwordsMatch && currentPassword.length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await changePassword(
        {
          current_password: currentPassword,
          new_password: newPassword,
        },
        accessToken
      );
      setSuccessMessage('Đổi mật khẩu thành công! / Password changed successfully.');
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1200);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Không thể đổi mật khẩu. Vui lòng kiểm tra lại.';
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

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
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: tokens.spacing.md,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-modal-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: tokens.colors.surface,
          borderRadius: tokens.radius.lg,
          border: `1px solid ${tokens.colors.border}`,
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
          maxWidth: '480px',
          width: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: `${tokens.spacing.lg} ${tokens.spacing.xl}`,
            borderBottom: `1px solid ${tokens.colors.borderMuted}`,
          }}
        >
          <div>
            <h2
              id="change-password-modal-title"
              style={{
                margin: 0,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.lg,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              Đổi Mật Khẩu (Change Password)
            </h2>
            <p
              style={{
                margin: `${tokens.spacing.xs} 0 0 0`,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xs,
                color: tokens.colors.textMuted,
              }}
            >
              Cập nhật mật khẩu tài khoản thủ thư / Operator password update
            </p>
          </div>
          <button
            type="button"
            aria-label="Đóng / Close"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '20px',
              color: tokens.colors.textMuted,
              cursor: 'pointer',
              padding: tokens.spacing.xs,
              borderRadius: tokens.radius.sm,
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        </div>

        {/* Form Body - Single column layout */}
        <form
          onSubmit={handleSubmit}
          style={{
            padding: tokens.spacing.xl,
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.lg,
          }}
        >
          {errorMessage && (
            <div
              role="alert"
              style={{
                padding: tokens.spacing.md,
                backgroundColor: tokens.colors.status.danger.bg,
                border: `1px solid ${tokens.colors.status.danger.border}`,
                borderRadius: tokens.radius.md,
                color: tokens.colors.status.danger.color,
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              ⚠️ {errorMessage}
            </div>
          )}

          {successMessage && (
            <div
              role="status"
              style={{
                padding: tokens.spacing.md,
                backgroundColor: tokens.colors.status.success.bg,
                border: `1px solid ${tokens.colors.status.success.border}`,
                borderRadius: tokens.radius.md,
                color: tokens.colors.status.success.color,
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              ✓ {successMessage}
            </div>
          )}

          {/* Current Password Field */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
            <label
              htmlFor="field-current-password"
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textPrimary,
              }}
            >
              Mật khẩu hiện tại (Current Password)
            </label>
            <input
              id="field-current-password"
              ref={initialInputRef}
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Nhập mật khẩu đang sử dụng..."
              style={{
                padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
                borderRadius: tokens.radius.md,
                border: `1px solid ${tokens.colors.border}`,
                backgroundColor: tokens.colors.surfaceAlt,
                color: tokens.colors.textPrimary,
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
                outline: 'none',
              }}
            />
          </div>

          {/* New Password Field */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
            <label
              htmlFor="field-new-password"
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textPrimary,
              }}
            >
              Mật khẩu mới (New Password)
            </label>
            <input
              id="field-new-password"
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Tối thiểu 8 ký tự, có chữ hoa và ký tự đặc biệt..."
              style={{
                padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
                borderRadius: tokens.radius.md,
                border: `1px solid ${tokens.colors.border}`,
                backgroundColor: tokens.colors.surfaceAlt,
                color: tokens.colors.textPrimary,
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
                outline: 'none',
              }}
            />
          </div>

          {/* Confirm New Password Field */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
            <label
              htmlFor="field-confirm-password"
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textPrimary,
              }}
            >
              Xác nhận mật khẩu mới (Confirm New Password)
            </label>
            <input
              id="field-confirm-password"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Nhập lại chính xác mật khẩu mới..."
              style={{
                padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
                borderRadius: tokens.radius.md,
                border: `1px solid ${tokens.colors.border}`,
                backgroundColor: tokens.colors.surfaceAlt,
                color: tokens.colors.textPrimary,
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
                outline: 'none',
              }}
            />
          </div>

          {/* Realtime Password Checklist */}
          <div
            style={{
              padding: tokens.spacing.sm,
              backgroundColor: tokens.colors.surfaceAlt,
              borderRadius: tokens.radius.md,
              border: `1px solid ${tokens.colors.borderMuted}`,
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.xs,
              fontSize: tokens.typography.fontSizes.xs,
              fontFamily: tokens.typography.fontFamily,
            }}
          >
            <div style={{ color: hasMinLength ? tokens.colors.status.success.color : tokens.colors.textMuted }}>
              {hasMinLength ? '✓' : '○'} Tối thiểu 8 ký tự (At least 8 characters)
            </div>
            <div style={{ color: hasUpperCase ? tokens.colors.status.success.color : tokens.colors.textMuted }}>
              {hasUpperCase ? '✓' : '○'} Có ít nhất 1 chữ in hoa (At least 1 uppercase letter)
            </div>
            <div style={{ color: hasSpecialOrDigit ? tokens.colors.status.success.color : tokens.colors.textMuted }}>
              {hasSpecialOrDigit ? '✓' : '○'} Chứa số hoặc ký tự đặc biệt (Contains digit/special char)
            </div>
            <div style={{ color: passwordsMatch ? tokens.colors.status.success.color : tokens.colors.textMuted }}>
              {passwordsMatch ? '✓' : '○'} Mật khẩu xác nhận trùng khớp (Passwords match)
            </div>
          </div>

          {/* Action Buttons - 2:1 Whitespace padding ratio */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: tokens.spacing.md,
              marginTop: tokens.spacing.md,
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                borderRadius: tokens.radius.md,
                border: `1px solid ${tokens.colors.border}`,
                backgroundColor: 'transparent',
                color: tokens.colors.textSecondary,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.medium,
                cursor: 'pointer',
              }}
            >
              Hủy / Cancel
            </button>
            <button
              type="submit"
              disabled={!isFormValid || isSubmitting}
              style={{
                padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                borderRadius: tokens.radius.md,
                border: 'none',
                backgroundColor: isFormValid && !isSubmitting ? tokens.colors.primary : tokens.colors.border,
                color: tokens.colors.primaryContrastText,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.semibold,
                cursor: isFormValid && !isSubmitting ? 'pointer' : 'not-allowed',
                boxShadow: isFormValid ? '0 1px 2px rgba(0, 0, 0, 0.05)' : 'none',
              }}
            >
              {isSubmitting ? 'Đang lưu / Updating...' : 'Cập Nhật Mật Khẩu (Update Password)'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
