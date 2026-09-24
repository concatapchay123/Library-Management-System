import React, { useState } from 'react';
import { useTokens } from '../tokens';

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isFullWidth?: boolean;
  children: React.ReactNode;
}

/**
 * Accessible Button Component for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - 2:1 Whitespace ratio (paddingX = 2 * paddingY) via token definitions
 * - Visible keyboard focus ring token
 * - Distinct danger variant for destructive actions
 * - Title Case label support
 */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    isFullWidth = false,
    disabled = false,
    children,
    style,
    onFocus,
    onBlur,
    ...props
  },
  ref,
) {
  const tokens = useTokens();
  const [isFocused, setIsFocused] = useState(false);

  const spacing = tokens.buttonSpacing[size];

  // Derive styling based on variant
  let backgroundColor: string = tokens.colors.surfaceAlt;
  let color: string = tokens.colors.textPrimary;
  let border: string = `1px solid ${tokens.colors.border}`;

  switch (variant) {
    case 'primary':
      backgroundColor = tokens.colors.primary;
      color = tokens.colors.primaryContrastText;
      border = `1px solid ${tokens.colors.primary}`;
      break;
    case 'danger':
      backgroundColor = tokens.colors.status.danger.bg;
      color = tokens.colors.status.danger.color;
      border = `1px solid ${tokens.colors.status.danger.border}`;
      break;
    case 'outline':
      backgroundColor = 'transparent';
      color = tokens.colors.textPrimary;
      border = `1px solid ${tokens.colors.border}`;
      break;
    case 'ghost':
      backgroundColor = 'transparent';
      color = tokens.colors.textPrimary;
      border = '1px solid transparent';
      break;
    case 'secondary':
    default:
      backgroundColor = tokens.colors.surfaceAlt;
      color = tokens.colors.textPrimary;
      border = `1px solid ${tokens.colors.border}`;
      break;
  }

  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: tokens.typography.fontFamily,
    fontSize: size === 'sm' ? tokens.typography.fontSizes.sm : tokens.typography.fontSizes.md,
    fontWeight: tokens.typography.fontWeights.medium,
    lineHeight: tokens.typography.lineHeights.tight,
    borderRadius: tokens.radius.md,
    paddingTop: spacing.py,
    paddingBottom: spacing.py,
    paddingLeft: spacing.px,
    paddingRight: spacing.px,
    backgroundColor,
    color,
    border,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    outline: isFocused ? tokens.focus.cssString : 'none',
    outlineOffset: isFocused ? tokens.focus.outlineOffset : undefined,
    width: isFullWidth ? '100%' : 'auto',
    transition: 'background-color 150ms ease, border-color 150ms ease, box-shadow 150ms ease',
    textDecoration: 'none',
    boxSizing: 'border-box',
    userSelect: 'none',
    ...style,
  };

  return (
    <button
      ref={ref}
      disabled={disabled}
      data-variant={variant}
      data-size={size}
      style={baseStyle}
      onFocus={(e) => {
        setIsFocused(true);
        if (onFocus) onFocus(e);
      }}
      onBlur={(e) => {
        setIsFocused(false);
        if (onBlur) onBlur(e);
      }}
      {...props}
    >
      {children}
    </button>
  );
});

export default Button;
