import { createContext, useContext } from 'react';
import { ThemeTokens } from './types';
import { defaultTokens } from './tokens';

export const TokenContext = createContext<ThemeTokens>(defaultTokens);

export function useTokens(): ThemeTokens {
  const context = useContext(TokenContext);
  return context || defaultTokens;
}
