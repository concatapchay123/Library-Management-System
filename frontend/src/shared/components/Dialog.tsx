import React, { useEffect, useRef, useId } from 'react';
import { useTokens, calcNestedRadius } from '../tokens';

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  triggerRef?: React.RefObject<HTMLElement | null>;
  role?: 'dialog' | 'alertdialog';
  maxWidth?: string;
}

/**
 * Accessible Modal Dialog Primitive for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - Proper ARIA semantics: role="dialog" or "alertdialog", aria-modal="true", aria-labelledby, aria-describedby
 * - Escape key dismissal
 * - Focus preservation: restores focus to the trigger element when closed
 * - Non-pure black backdrop and anti-glare dialog surface
 * - Close button [X] at top-right with explicit accessible label
 */
export function Dialog({
  isOpen,
  onClose,
  title,
  description,
  children,
  triggerRef,
  role = 'dialog',
  maxWidth = '520px',
}: DialogProps) {
  const tokens = useTokens();
  const idPrefix = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedElementRef = useRef<HTMLElement | null>(null);

  const titleId = `${idPrefix}-title`;
  const descriptionId = description ? `${idPrefix}-desc` : undefined;

  // Track and restore focus on open/close
  useEffect(() => {
    if (isOpen) {
      previouslyFocusedElementRef.current = (document.activeElement as HTMLElement) || null;

      // Focus first field or focusable element inside the dialog
      if (dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
        );
        // Prefer first form input over close button if available
        const target =
          Array.from(focusables).find(
            (el) => el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT'
          ) || focusables[0];

        if (target) {
          target.focus();
        } else {
          dialogRef.current.focus();
        }
      }
    } else {
      // Restore focus to triggerRef or saved previously focused element
      const targetToFocus = triggerRef?.current || previouslyFocusedElementRef.current;
      if (targetToFocus && typeof targetToFocus.focus === 'function') {
        targetToFocus.focus();
      }
    }
  }, [isOpen, triggerRef]);

  // Handle Escape key and Tab/Shift+Tab Focus Trap
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' || event.code === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key === 'Tab' || event.code === 'Tab') {
        if (!dialogRef.current) return;
        const focusables = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => el.getAttribute('tabindex') !== '-1');

        if (focusables.length === 0) {
          event.preventDefault();
          return;
        }

        const firstElement = focusables[0];
        const lastElement = focusables[focusables.length - 1];
        if (!firstElement || !lastElement) return;

        if (event.shiftKey) {
          if (document.activeElement === firstElement || document.activeElement === dialogRef.current) {
            event.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            event.preventDefault();
            firstElement.focus();
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const outerRadius = 12;
  const paddingVal = 20;
  const innerRadius = calcNestedRadius(outerRadius, paddingVal);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(18, 18, 18, 0.45)', // Calibrated backdrop (no pure black)
        padding: tokens.spacing.md,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth,
          backgroundColor: tokens.colors.surface,
          borderRadius: `${outerRadius}px`,
          border: `1px solid ${tokens.colors.border}`,
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
          padding: `${paddingVal}px`,
          outline: 'none',
          boxSizing: 'border-box',
        }}
      >
        {/* Header Region */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: tokens.spacing.md,
            marginBottom: tokens.spacing.md,
          }}
        >
          <div>
            <h2
              id={titleId}
              style={{
                margin: 0,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xl,
                fontWeight: tokens.typography.fontWeights.bold,
                lineHeight: tokens.typography.lineHeights.tight,
                color: tokens.colors.textPrimary,
              }}
            >
              {title}
            </h2>
            {description && (
              <p
                id={descriptionId}
                style={{
                  margin: 0,
                  marginTop: tokens.spacing.xs,
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.sm,
                  color: tokens.colors.textSecondary,
                  lineHeight: tokens.typography.lineHeights.normal,
                }}
              >
                {description}
              </p>
            )}
          </div>

          {/* Close button [X] */}
          <button
            type="button"
            aria-label="Đóng / Close dialog"
            onClick={onClose}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '32px',
              height: '32px',
              border: `1px solid ${tokens.colors.borderMuted}`,
              borderRadius: tokens.radius.md,
              backgroundColor: tokens.colors.surfaceAlt,
              color: tokens.colors.textSecondary,
              cursor: 'pointer',
              fontSize: tokens.typography.fontSizes.md,
              fontWeight: tokens.typography.fontWeights.bold,
              lineHeight: 1,
              flexShrink: 0,
            }}
          >
            ✕
          </button>
        </div>

        {/* Dialog Content Area */}
        <div
          style={{
            backgroundColor: tokens.colors.surfaceAlt,
            borderRadius: `${innerRadius}px`,
            padding: tokens.spacing.md,
            border: `1px solid ${tokens.colors.borderMuted}`,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

export default Dialog;
