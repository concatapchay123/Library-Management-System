import {
  useMemo,
  type FC,
  type ReactNode,
  type CSSProperties,
} from 'react';
import { ThemeTokens } from './types';
import { defaultTokens } from './tokens';
import { TokenContext } from './context';

export interface TokenProviderProps {
  tokens?: Partial<ThemeTokens>;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export const TokenProvider: FC<TokenProviderProps> = ({
  tokens: customTokens,
  children,
  className,
  style,
}) => {
  const mergedTokens = useMemo<ThemeTokens>(() => {
    if (!customTokens) return defaultTokens;
    return {
      spacing: {
        ...defaultTokens.spacing,
        ...customTokens.spacing,
        semantic: {
          ...defaultTokens.spacing.semantic,
          ...(customTokens.spacing?.semantic || {}),
        },
      },
      colors: {
        ...defaultTokens.colors,
        ...customTokens.colors,
        status: {
          ...defaultTokens.colors.status,
          ...(customTokens.colors?.status || {}),
        },
      },
      focus: {
        ...defaultTokens.focus,
        ...customTokens.focus,
      },
      typography: {
        ...defaultTokens.typography,
        ...customTokens.typography,
      },
      radius: {
        ...defaultTokens.radius,
        ...customTokens.radius,
      },
      buttonSpacing: {
        ...defaultTokens.buttonSpacing,
        ...customTokens.buttonSpacing,
      },
    };
  }, [customTokens]);

  const cssVariables = useMemo<CSSProperties>(() => {
    return {
      '--ol-spacing-xs': mergedTokens.spacing.xs,
      '--ol-spacing-sm': mergedTokens.spacing.sm,
      '--ol-spacing-md': mergedTokens.spacing.md,
      '--ol-spacing-lg': mergedTokens.spacing.lg,
      '--ol-spacing-xl': mergedTokens.spacing.xl,
      '--ol-spacing-2xl': mergedTokens.spacing['2xl'],
      '--ol-spacing-label-to-input':
        mergedTokens.spacing.semantic.labelToInput,
      '--ol-spacing-group-to-group':
        mergedTokens.spacing.semantic.groupToGroup,
      '--ol-spacing-form-to-submit':
        mergedTokens.spacing.semantic.formToSubmit,

      '--ol-color-surface': mergedTokens.colors.surface,
      '--ol-color-surface-alt': mergedTokens.colors.surfaceAlt,
      '--ol-color-surface-elevated': mergedTokens.colors.surfaceElevated,
      '--ol-color-text-primary': mergedTokens.colors.textPrimary,
      '--ol-color-text-secondary': mergedTokens.colors.textSecondary,
      '--ol-color-text-muted': mergedTokens.colors.textMuted,
      '--ol-color-border': mergedTokens.colors.border,
      '--ol-color-border-muted': mergedTokens.colors.borderMuted,
      '--ol-color-border-focus': mergedTokens.colors.borderFocus,
      '--ol-color-primary': mergedTokens.colors.primary,
      '--ol-color-primary-hover': mergedTokens.colors.primaryHover,
      '--ol-color-primary-contrast': mergedTokens.colors.primaryContrastText,

      '--ol-color-status-success': mergedTokens.colors.status.success.color,
      '--ol-color-status-warning': mergedTokens.colors.status.warning.color,
      '--ol-color-status-danger': mergedTokens.colors.status.danger.color,
      '--ol-color-status-info': mergedTokens.colors.status.info.color,

      '--ol-focus-outline': mergedTokens.focus.cssString,
      '--ol-font-family': mergedTokens.typography.fontFamily,
      '--ol-mono-font-family': mergedTokens.typography.monoFontFamily,
      ...style,
    } as CSSProperties;
  }, [mergedTokens, style]);

  return (
    <TokenContext.Provider value={mergedTokens}>
      <div
        className={className}
        style={cssVariables}
        data-theme-root="openlibrary-tokens"
      >
        {children}
      </div>
    </TokenContext.Provider>
  );
};
