import { useAuth } from '../contexts/AuthContext';
import '../styles/design-system.css';

const PROVIDER_ICONS: Record<string, JSX.Element> = {
  google: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  ),
  github: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
    </svg>
  ),
};

const PROVIDER_LABELS: Record<string, string> = {
  google: 'Continue with Google',
  github: 'Continue with GitHub',
};

export default function LoginPage() {
  const { providers, login, loading } = useAuth();

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.spinner} />
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.logo}>N</div>
        <h1 style={styles.title}>Sign in to NexaQL</h1>
        <p style={styles.subtitle}>Privacy-aware data intelligence</p>

        <div style={styles.providers}>
          {providers.map((provider) => (
            <button
              key={provider}
              onClick={() => login(provider)}
              style={styles.providerButton}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--v2-purple-500)';
                e.currentTarget.style.backgroundColor = 'var(--v2-bg-hover)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--v2-border)';
                e.currentTarget.style.backgroundColor = 'var(--v2-bg-elevated)';
              }}
            >
              <span style={styles.providerIcon}>{PROVIDER_ICONS[provider]}</span>
              <span>{PROVIDER_LABELS[provider] ?? `Continue with ${provider}`}</span>
            </button>
          ))}
        </div>

        {providers.length === 0 && (
          <p style={styles.noProviders}>
            No OAuth providers configured. Ask your administrator to set up authentication in Settings.
          </p>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'var(--v2-bg-app, #fff)',
    fontFamily: 'var(--v2-font-sans)',
    padding: '1rem',
  },
  card: {
    width: '100%',
    maxWidth: 400,
    textAlign: 'center',
    padding: '3rem 2.5rem',
    borderRadius: 'var(--v2-radius-xl, 16px)',
    border: '1px solid var(--v2-border, #e5e7eb)',
    backgroundColor: 'var(--v2-bg-elevated, #fff)',
    boxShadow: 'var(--v2-shadow-md)',
  },
  logo: {
    width: 56,
    height: 56,
    borderRadius: 'var(--v2-radius-lg, 12px)',
    backgroundColor: 'var(--v2-purple-500, #8B5CF6)',
    color: '#fff',
    fontSize: '1.5rem',
    fontWeight: 700,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '1.5rem',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 600,
    color: 'var(--v2-text-primary, #111827)',
    margin: '0 0 0.5rem',
  },
  subtitle: {
    fontSize: '0.875rem',
    color: 'var(--v2-text-secondary, #6b7280)',
    margin: '0 0 2rem',
  },
  providers: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  providerButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.75rem',
    width: '100%',
    padding: '0.75rem 1rem',
    fontSize: '0.9375rem',
    fontWeight: 500,
    fontFamily: 'var(--v2-font-sans)',
    color: 'var(--v2-text-primary, #111827)',
    backgroundColor: 'var(--v2-bg-elevated, #fff)',
    border: '1px solid var(--v2-border, #e5e7eb)',
    borderRadius: 'var(--v2-radius-md, 8px)',
    cursor: 'pointer',
    transition: 'border-color var(--v2-transition-fast), background-color var(--v2-transition-fast)',
  },
  providerIcon: {
    display: 'flex',
    alignItems: 'center',
  },
  noProviders: {
    fontSize: '0.875rem',
    color: 'var(--v2-text-secondary, #6b7280)',
    lineHeight: 1.5,
  },
  spinner: {
    width: 32,
    height: 32,
    border: '3px solid var(--v2-border, #e5e7eb)',
    borderTopColor: 'var(--v2-purple-500, #8B5CF6)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
    margin: '2rem auto',
  },
};
