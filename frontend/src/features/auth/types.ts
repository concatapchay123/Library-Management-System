/**
 * Authentication and session types for OpenLibraryOS (FE-003).
 */

export interface LoginCredentials {
  organization_slug: string;
  email: string;
  password: string;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Principal {
  user_id: string;
  organization_id: string;
  session_id: string;
  permissions: string[];
}

export interface AuthState {
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

export interface AuthContextValue extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>;
  refresh: () => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
}
