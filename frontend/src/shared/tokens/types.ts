/**
 * Design Token Type Definitions for OpenLibraryOS
 *
 * Implements low-tech, accessible UI requirements:
 * - Semantic spacing progression (12px label-to-input, 24px group-to-group, 32px form-to-submit)
 * - Anti-glare contrast rules (no pure black #000000 or pure white #ffffff)
 * - Non-color status cues (pairing color with icon and text label)
 * - Visible keyboard focus indicators
 * - 2:1 horizontal to vertical button whitespace ratio
 * - Nested border radius calculations
 */

export interface SpacingScale {
  none: string;
  xs: string;
  sm: string;
  md: string;
  lg: string;
  xl: string;
  '2xl': string;
  '3xl': string;
  '4xl': string;
}

export interface SemanticSpacing {
  labelToInput: string;
  groupToGroup: string;
  formToSubmit: string;
}

export interface SpacingTokens extends SpacingScale {
  semantic: SemanticSpacing;
}

export interface StatusCue {
  color: string;
  bg: string;
  border: string;
  icon: string;
  label: string;
}

export interface StatusTokens {
  success: StatusCue;
  warning: StatusCue;
  danger: StatusCue;
  info: StatusCue;
}

export interface ColorTokens {
  surface: string;
  surfaceAlt: string;
  surfaceElevated: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  borderMuted: string;
  borderFocus: string;
  primary: string;
  primaryHover: string;
  primaryActive: string;
  primaryContrastText: string;
  status: StatusTokens;
}

export interface FocusTokens {
  outlineWidth: string;
  outlineStyle: string;
  outlineColor: string;
  outlineOffset: string;
  cssString: string;
}

export interface TypographyTokens {
  fontFamily: string;
  monoFontFamily: string;
  fontSizes: {
    xs: string;
    sm: string;
    md: string;
    lg: string;
    xl: string;
    '2xl': string;
    '3xl': string;
  };
  fontWeights: {
    normal: number;
    medium: number;
    semibold: number;
    bold: number;
  };
  lineHeights: {
    tight: number;
    normal: number;
    relaxed: number;
  };
}

export interface RadiusTokens {
  none: string;
  sm: string;
  md: string;
  lg: string;
  xl: string;
  full: string;
}

export interface ButtonPadding {
  py: string;
  px: string;
}

export interface ButtonSpacingTokens {
  sm: ButtonPadding;
  md: ButtonPadding;
  lg: ButtonPadding;
}

export interface ThemeTokens {
  spacing: SpacingTokens;
  colors: ColorTokens;
  focus: FocusTokens;
  typography: TypographyTokens;
  radius: RadiusTokens;
  buttonSpacing: ButtonSpacingTokens;
}
