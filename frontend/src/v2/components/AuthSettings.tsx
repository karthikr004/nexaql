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
        <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Authentication</h2>
        <div className="v2-card" style={{ padding: 24, textAlign: 'center' }}>
          <p className="v2-body-sm">Loading auth configuration...</p>
        </div>
      </div>
    );
  }

  const isOAuth = config.auth_mode === 'oauth';
  const configuredProviders = config.providers.map((p) => p.provider);
  const availableToAdd = OAUTH_PROVIDERS.filter((p) => !configuredProviders.includes(p.value));

  return (
    <div style={{ marginBottom: 32 }}>
      <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Authentication</h2>

      <div className="v2-card" style={{ padding: 24 }}>
        {/* Auth mode toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: config.providers.length > 0 ? 20 : 0 }}>
          <div>
            <div className="v2-heading-sm">Auth Mode</div>
            <p className="v2-body-sm" style={{ marginTop: 2 }}>
              {isOAuth
                ? 'OAuth enabled — users must sign in'
                : 'Dev mode — open access, no authentication'}
            </p>
          </div>
          <button
            type="button"
            className={`v2-btn v2-btn-sm ${isOAuth ? 'v2-btn-primary' : ''}`}
            onClick={handleToggleMode}
            disabled={switchingMode}
            style={{
              minWidth: 100,
              ...(isOAuth ? {} : { border: '1px solid var(--v2-border)', background: 'var(--v2-bg-surface)' }),
            }}
          >
            {switchingMode ? '...' : isOAuth ? 'OAuth' : 'Dev'}
          </button>
        </div>

        {/* Configured providers */}
        {config.providers.length > 0 && (
          <div style={{ marginBottom: availableToAdd.length > 0 ? 16 : 0 }}>
            <div className="v2-label" style={{ marginBottom: 8 }}>OAuth Providers</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {config.providers.map((p) => (
                <div
                  key={p.provider}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    borderRadius: 'var(--v2-radius-sm)',
                    border: '1px solid var(--v2-border)',
                    background: 'var(--v2-bg-surface)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className="v2-badge v2-badge-teal">{p.provider}</span>
                    <span className="v2-body-sm" style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12 }}>
                      {p.client_id}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="v2-btn v2-btn-ghost v2-btn-sm"
                    onClick={() => handleDeleteProvider(p.provider)}
                    style={{ color: 'var(--v2-red-500)' }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Add provider */}
        {availableToAdd.length > 0 && !showAddProvider && (
          <button
            type="button"
            className="v2-btn v2-btn-sm"
            onClick={() => {
              setNewProvider(availableToAdd[0]?.value ?? 'google');
              setShowAddProvider(true);
            }}
            style={{ border: '1px solid var(--v2-border)', background: 'transparent' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add OAuth Provider
          </button>
        )}

        {showAddProvider && (
          <div style={{ borderTop: '1px solid var(--v2-border)', paddingTop: 16, marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div className="v2-heading-sm">Add OAuth Provider</div>
              <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={() => setShowAddProvider(false)}>Cancel</button>
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
                  placeholder="your-client-id.apps.googleusercontent.com"
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
                  placeholder="GOCSPX-..."
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
    </div>
  );
}
