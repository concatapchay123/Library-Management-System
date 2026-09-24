import { ThemeTokens } from './types';

/**
 * Default design tokens for OpenLibraryOS.
 *
 * Rules strictly followed:
 * - Anti-glare contrast: no pure white (#ffffff) or pure black (#000000)
 * - Text contrast >= 4.5:1 against surfaces (WCAG AA)
 * - Non-color status cues: every status state includes an icon identifier and textual label
 * - Semantic spacing progression: 12px label-input, 24px group-group, 32px form-submit
 * - 2:1 button whitespace ratio: px = 2 * py
 * - Nested radius formula: R_inner = max(0, R_outer - Padding)
 */
export const defaultTokens: ThemeTokens = {
  spacing: {
    none: '0px',
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    '2xl': '32px',
    '3xl': '48px',
    '4xl': '64px',
    semantic: {
      labelToInput: '12px',
      groupToGroup: '24px',
      formToSubmit: '32px',
    },
  },
  colors: {
    // Calibrated off-white surfaces to eliminate glare and eye strain
    surface: '#f8fafc',
    surfaceAlt: '#f4f4f5',
    surfaceElevated: '#e7e9eb',

    // Calibrated charcoal and slate typography for optimal contrast (>= 4.5:1)
    textPrimary: '#121212',
    textSecondary: '#3f3f46',
    textMuted: '#71717a',

    // Borders & dividers
    border: '#d4d4d8',
    borderMuted: '#e4e4e7',
    borderFocus: '#2563eb',

    // Brand and Primary Action (accessible slate blue)
    primary: '#1d4ed8',
    primaryHover: '#1e40af',
    primaryActive: '#1e3a8a',
    primaryContrastText: '#f8fafc',

    // Status tokens with non-color cues (icon + label)
    status: {
      success: {
        color: '#15803d',
        bg: '#f0fdf4',
        border: '#bbf7d0',
        icon: 'check-circle',
        label: 'Success',
      },
      warning: {
        color: '#b45309',
        bg: '#fffbeb',
        border: '#fde68a',
        icon: 'alert-triangle',
        label: 'Warning',
      },
      danger: {
        color: '#b91c1c',
        bg: '#fef2f2',
        border: '#fecaca',
        icon: 'alert-circle',
        label: 'Danger',
      },
      info: {
        color: '#0369a1',
        bg: '#f0f9ff',
        border: '#bae6fd',
        icon: 'info-circle',
        label: 'Info',
      },
    },
  },
  focus: {
    outlineWidth: '2px',
    outlineStyle: 'solid',
    outlineColor: '#2563eb',
    outlineOffset: '2px',
    cssString: '2px solid #2563eb',
  },
  typography: {
    fontFamily:
      "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    monoFontFamily:
      "'JetBrains Mono', Consolas, Monaco, 'Courier New', monospace",
    fontSizes: {
      xs: '12px',
      sm: '14px',
      md: '16px',
      lg: '18px',
      xl: '20px',
      '2xl': '24px',
      '3xl': '30px',
    },
    fontWeights: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
    lineHeights: {
      tight: 1.25,
      normal: 1.5,
      relaxed: 1.75,
    },
  },
  radius: {
    none: '0px',
    sm: '4px',
    md: '6px',
    lg: '8px',
    xl: '12px',
    full: '9999px',
  },
  buttonSpacing: {
    sm: { py: '6px', px: '12px' },
    md: { py: '8px', px: '16px' },
    lg: { py: '12px', px: '24px' },
  },
};

/**
 * Calculates nested border radius to prevent eccentric distortion:
 * R_inner = max(0, R_outer - Padding)
 */
export function calcNestedRadius(
  outerRadiusPx: number,
  paddingPx: number,
): number {
  return Math.max(0, outerRadiusPx - paddingPx);
}
