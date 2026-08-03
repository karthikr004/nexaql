import { useState, useCallback, useEffect } from 'react';

interface AuthConfig {
  auth_mode: string;
  providers: ProviderInfo[];
}

interface ProviderInfo {
  provider: string;
  client_id: string;
  client_secret: string;
  enabled: boolean;
}

interface Toast {
  message: string;
  type: 'success' | 'error' | 'info';
}

interface AuthSettingsProps {
  showToast: (t: Toast) => void;
}

const OAUTH_PROVIDERS = [
  { value: 'google', label: 'Google' },
  { value: 'github', label: 'GitHub' },
] as const;

const SETUP_LINKS: Record<string, string> = {
  google: 'https://console.cloud.google.com/apis/credentials',
  github: 'https://github.com/settings/developers',
};

const SETUP_STEPS: Record<string, string[]> = {
  google: [
    'Go to Google Cloud Console → APIs & Services → Credentials',
    'Create an OAuth 2.0 Client ID (Web application)',
    'Add authorized redirect URI: {origin}/api/auth/callback/google',
    'Copy the Client ID and Client Secret below',
  ],
  github: [
    'Go to GitHub → Settings → Developer settings → OAuth Apps',
    'Create a new OAuth App',
    'Set Authorization callback URL to: {origin}/api/auth/callback/github',
    'Copy the Client ID and generate a Client Secret below',
  ],
};

export default function AuthSettings({ showToast }: AuthSettingsProps) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [newProvider, setNewProvider] = useState<'google' | 'github'>('google');
  const [newClientId, setNewClientId] = useState('');
  const [newClientSecret, setNewClientSecret] = useState('');
  const [saving, setSaving] = useState(false);
  const [switchingMode, setSwitchingMode] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/auth-config', { credentials: 'include' });
      if (res.ok) {
        setConfig(await res.json());
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const handleToggleMode = useCallback(async () => {
    if (!config) return;
    const newMode = config.auth_mode === 'oauth' ? 'dev' : 'oauth';
    setSwitchingMode(true);
    try {
      const res = await fetch('/api/admin/auth-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_mode: newMode }),
        credentials: 'include',
      });
      if (res.ok) {
        showToast({ message: `Auth mode switched to ${newMode}`, type: 'success' });
        fetchConfig();
      } else {
        const body = await res.json();
        showToast({ message: body.detail || 'Failed to switch mode', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSwitchingMode(false);
    }
  }, [config, fetchConfig, showToast]);

  const handleAddProvider = useCallback(async () => {
    if (!newClientId.trim() || !newClientSecret.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/admin/oauth-providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: newProvider,
          client_id: newClientId.trim(),
          client_secret: newClientSecret.trim(),
          enabled: true,
        }),
        credentials: 'include',
      });
      if (res.ok) {
        showToast({ message: `${newProvider} provider configured`, type: 'success' });
        setShowAddProvider(false);
        setNewClientId('');
        setNewClientSecret('');
        fetchConfig();
      } else {
        const body = await res.json();
        showToast({ message: body.detail || 'Failed to save', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [newProvider, newClientId, newClientSecret, fetchConfig, showToast]);

  const handleDeleteProvider = useCallback(async (provider: string) => {
    try {
      const res = await fetch(`/api/admin/oauth-providers/${encodeURIComponent(provider)}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        showToast({ message: `Removed ${provider} provider`, type: 'success' });
        fetchConfig();
      } else {
        const body = await res.json();
        showToast({ message: body.detail || 'Failed to remove', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    }
  }, [fetchConfig, showToast]);

  if (loading || !config) {
    return (
      <div style={{ marginBottom: 32 }}>
        <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Auth Mode</h2>
        <div className="v2-card" style={{ padding: 24, textAlign: 'center' }}>
          <p className="v2-body-sm">Loading...</p>
        </div>
      </div>
    );
  }

  const isOAuth = config.auth_mode === 'oauth';
  const configuredProviders = config.providers.map((p) => p.provider);
  const availableToAdd = OAUTH_PROVIDERS.filter((p) => !configuredProviders.includes(p.value));
  const origin = window.location.origin;

  return (
    <>
      {/* ── Auth Mode ──────────────────────────────────────────── */}
      <div style={{ marginBottom: 32 }}>
        <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Auth Mode</h2>
        <div className="v2-card" style={{ padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div className="v2-heading-sm">
                {isOAuth ? 'OAuth enabled' : 'Dev mode (open access)'}
              </div>
              <p className="v2-body-sm" style={{ marginTop: 4, maxWidth: 480, lineHeight: 1.5 }}>
                {isOAuth
                  ? 'Users must sign in with Google or GitHub. Roles and access policies are enforced per user.'
                  : 'Anyone can access NexaQL without signing in. Use this for local development and testing.'}
              </p>
            </div>
            <button
              type="button"
              className={`v2-btn v2-btn-sm ${isOAuth ? 'v2-btn-primary' : ''}`}
              onClick={handleToggleMode}
              disabled={switchingMode}
              style={{
                minWidth: 120,
                ...(isOAuth ? {} : { border: '1px solid var(--v2-border)', background: 'var(--v2-bg-surface)' }),
              }}
            >
              {switchingMode ? '...' : isOAuth ? 'Disable OAuth' : 'Enable OAuth'}
            </button>
          </div>
        </div>
      </div>

      {/* ── OAuth Providers ────────────────────────────────────── */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 className="v2-heading-md">OAuth Providers</h2>
          {availableToAdd.length > 0 && !showAddProvider && (
            <button
              type="button"
              className="v2-btn v2-btn-primary v2-btn-sm"
              onClick={() => {
                setNewProvider(availableToAdd[0]?.value ?? 'google');
                setShowAddProvider(true);
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Add Provider
            </button>
          )}
        </div>

        {/* Explainer */}
        <div
          className="v2-card-flat"
          style={{ padding: '12px 16px', marginBottom: 16, fontSize: 12, color: 'var(--v2-text-secondary)', lineHeight: 1.6 }}
        >
          <strong style={{ color: 'var(--v2-text-primary)' }}>How it works:</strong> You register an OAuth app with Google or GitHub, then paste the credentials here.
          When OAuth is enabled, your users sign in with their existing Google/GitHub accounts &mdash; they never see these credentials.
          Secrets are stored locally in <code style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, color: 'var(--v2-accent-text)' }}>~/.nexaql/nexaql.db</code> and
          never leave your machine.
        </div>

        {/* Configured providers */}
        {config.providers.length > 0 ? (
          <div className="v2-card">
            <table className="v2-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Client ID</th>
                  <th>Secret</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {config.providers.map((p) => (
                  <tr key={p.provider}>
                    <td>
                      <span className="v2-badge v2-badge-teal">{p.provider}</span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-secondary)' }}>
                        {p.client_id}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                        {p.client_secret}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="v2-btn v2-btn-ghost v2-btn-sm"
                          onClick={() => handleDeleteProvider(p.provider)}
                          style={{ color: 'var(--v2-red-500)' }}
                        >
                          Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !showAddProvider ? (
          <div className="v2-card" style={{ textAlign: 'center', padding: '40px 24px' }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
              <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <p className="v2-heading-sm" style={{ marginBottom: 4 }}>No OAuth providers configured</p>
            <p className="v2-body-sm">Add Google or GitHub to enable user sign-in</p>
          </div>
        ) : null}

        {/* Add provider form */}
        {showAddProvider && (
          <div className="v2-card" style={{ padding: 24, marginTop: config.providers.length > 0 ? 16 : 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div className="v2-heading-sm">Add OAuth Provider</div>
              <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={() => setShowAddProvider(false)}>Cancel</button>
            </div>

            {/* Setup steps */}
            <div
              style={{
                padding: '12px 16px',
                marginBottom: 16,
                borderRadius: 'var(--v2-radius-sm)',
                background: 'var(--v2-purple-50)',
                border: '1px solid var(--v2-purple-100)',
                fontSize: 12,
                lineHeight: 1.6,
                color: 'var(--v2-text-secondary)',
              }}
            >
              <div style={{ fontWeight: 600, color: 'var(--v2-purple-700)', marginBottom: 6 }}>
                Setup steps for {newProvider === 'google' ? 'Google' : 'GitHub'}:
              </div>
              <ol style={{ margin: 0, paddingLeft: 18 }}>
                {(SETUP_STEPS[newProvider] ?? []).map((step, i) => (
                  <li key={i} style={{ marginBottom: 2 }}>
                    {step.replace('{origin}', origin)}
                  </li>
                ))}
              </ol>
              <div style={{ marginTop: 8 }}>
                <a
                  href={SETUP_LINKS[newProvider]}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--v2-purple-600)', fontWeight: 500, textDecoration: 'none' }}
                >
                  Open {newProvider === 'google' ? 'Google Cloud Console' : 'GitHub Developer Settings'} &rarr;
                </a>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 4 }}>Provider</label>
                <select
                  className="v2-select"
                  value={newProvider}
                  onChange={(e) => setNewProvider(e.target.value as 'google' | 'github')}
                >
                  {availableToAdd.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 4 }}>Client ID</label>
                <input
                  className="v2-input"
                  value={newClientId}
                  onChange={(e) => setNewClientId(e.target.value)}
                  placeholder={newProvider === 'google' ? 'xxxx.apps.googleusercontent.com' : 'Iv1.xxxxxxxxxx'}
                  style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12 }}
                />
              </div>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 4 }}>Client Secret</label>
                <input
                  className="v2-input"
                  type="password"
                  value={newClientSecret}
                  onChange={(e) => setNewClientSecret(e.target.value)}
                  placeholder={newProvider === 'google' ? 'GOCSPX-...' : 'your-client-secret'}
                  style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12 }}
                />
              </div>
              <div>
                <button
                  type="button"
                  className="v2-btn v2-btn-primary"
                  onClick={handleAddProvider}
                  disabled={saving || !newClientId.trim() || !newClientSecret.trim()}
                  style={{ opacity: saving || !newClientId.trim() || !newClientSecret.trim() ? 0.5 : 1 }}
                >
                  {saving ? 'Saving...' : 'Save Provider'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
