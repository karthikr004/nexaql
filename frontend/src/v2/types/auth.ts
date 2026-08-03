export interface AuthUser {
  id: number;
  email: string;
  name: string | null;
  avatarUrl: string | null;
  roles: string[];
}

export type AuthMode = 'dev' | 'oauth';

export interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  authMode: AuthMode;
  providers: string[];
}
