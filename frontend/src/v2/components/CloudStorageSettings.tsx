import { useState, useCallback, useEffect } from 'react';

interface CloudProvider {
  provider: string;
  client_id: string;
  enabled: boolean;
}

interface CloudAccount {
  id: number;
  provider: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

interface CloudStorageSettingsProps {
  onToast: (message: string, type: 'success' | 'error') => void;
}

const PROVIDER_OPTIONS = [
  { value: 'google_drive', label: 'Google Drive' },
];

export default function CloudStorageSettings({ onToast }: CloudStorageSettingsProps) {
  const [providers, setProviders] = useState<CloudProvider[]>([]);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState('google_drive');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [provRes, accRes] = await Promise.all([
        fetch('/api/cloud-drive/providers'),
        fetch('/api/cloud-drive/accounts'),
      ]);
      if (provRes.ok) {
        const data = await provRes.json();
        setProviders(data.providers ?? []);
      }
      if (accRes.ok) {
        const data = await accRes.json();
        setAccounts(data.accounts ?? []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = useCallback(async () => {
    if (!clientId.trim() || !clientSecret.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/cloud-drive/providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          client_id: clientId.trim(),
          client_secret: clientSecret.trim(),
        }),
      });
      if (res.ok) {
        onToast(`${selectedProvider} credentials saved`, 'success');
        setShowAdd(false);
        setClientId('');
        setClientSecret('');
        fetchData();
      } else {
        const body = await res.json();
        onToast(body.detail || 'Failed to save', 'error');
      }
    } catch (err) {
      onToast(`Error: ${err}`, 'error');
    } finally {
      setSaving(false);
    }
  }, [selectedProvider, clientId, clientSecret, fetchData, onToast]);

  const handleDeleteProvider = useCallback(async (provider: string) => {
    try {
      const res = await fetch(`/api/cloud-drive/providers/${encodeURIComponent(provider)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        onToast(`Removed ${provider} configuration`, 'success');
        fetchData();
      } else {
        onToast('Failed to remove provider', 'error');
      }
    } catch (err) {
      onToast(`Error: ${err}`, 'error');
    }
  }, [fetchData, onToast]);

  const handleDisconnect = useCallback(async (accountId: number) => {
    try {
      const res = await fetch(`/api/cloud-drive/accounts/${accountId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        onToast('Account disconnected', 'success');
        fetchData();
      } else {
        onToast('Failed to disconnect', 'error');
      }
    } catch (err) {
      onToast(`Error: ${err}`, 'error');
    }
  }, [fetchData, onToast]);

  const providerLabel = (value: string) =>
    PROVIDER_OPTIONS.find((p) => p.value === value)?.label ?? value;

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <p className="v2-body-sm">Loading cloud storage settings...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="v2-heading-md">Cloud Storage</h2>
        {!showAdd && (
          <button
            type="button"
            className="v2-btn v2-btn-primary v2-btn-sm"
            onClick={() => setShowAdd(true)}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Provider
          </button>
        )}
      </div>

      {/* Add provider form */}
      {showAdd && (
        <div className="v2-card" style={{ padding: 24, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 className="v2-heading-sm">Configure Cloud Provider</h3>
            <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Provider</label>
              <select
                className="v2-select"
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
              >
                {PROVIDER_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Client ID</label>
              <input
                className="v2-input"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Your OAuth client ID"
                style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13 }}
              />
            </div>
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Client Secret</label>
              <input
                className="v2-input"
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder="Your OAuth client secret"
                style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13 }}
              />
            </div>
            <div
              className="v2-card-flat"
              style={{ padding: '10px 14px', fontSize: 12, color: 'var(--v2-text-secondary)', lineHeight: 1.5 }}
            >
              Create OAuth credentials in the{' '}
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--v2-accent-text)' }}
              >
                Google Cloud Console
              </a>
              . Enable the Google Drive API and set the redirect URI to{' '}
              <code style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11 }}>
                {window.location.origin}/api/cloud-drive/callback/google_drive
              </code>
            </div>
            <div>
              <button
                type="button"
                className="v2-btn v2-btn-primary"
                onClick={handleSave}
                disabled={saving || !clientId.trim() || !clientSecret.trim()}
                style={{ opacity: saving || !clientId.trim() || !clientSecret.trim() ? 0.5 : 1 }}
              >
                {saving ? 'Saving...' : 'Save Credentials'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Configured providers */}
      {providers.length === 0 && !showAdd ? (
        <div className="v2-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
            <path d="M22 12H2" /><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z" />
          </svg>
          <p className="v2-heading-md" style={{ marginBottom: 4 }}>No cloud providers</p>
          <p className="v2-body-sm">Add Google Drive credentials to enable cloud file import</p>
        </div>
      ) : providers.length > 0 && (
        <div className="v2-card" style={{ marginBottom: 16 }}>
          <table className="v2-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Client ID</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.provider}>
                  <td style={{ fontWeight: 500 }}>{providerLabel(p.provider)}</td>
                  <td>
                    <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                      {p.client_id}
                    </span>
                  </td>
                  <td>
                    <span className={`v2-badge ${p.enabled ? 'v2-badge-teal' : 'v2-badge'}`}>
                      {p.enabled ? 'Active' : 'Disabled'}
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
      )}

      {/* Connected accounts */}
      {accounts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3 className="v2-heading-sm" style={{ marginBottom: 12 }}>Connected Accounts</h3>
          <div className="v2-card">
            <table className="v2-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Email</th>
                  <th>Connected</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 500 }}>{providerLabel(a.provider)}</td>
                    <td>{a.email}</td>
                    <td>
                      <span className="v2-body-sm" style={{ color: 'var(--v2-text-tertiary)' }}>
                        {new Date(a.created_at).toLocaleDateString()}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="v2-btn v2-btn-ghost v2-btn-sm"
                          onClick={() => handleDisconnect(a.id)}
                          style={{ color: 'var(--v2-red-500)' }}
                        >
                          Disconnect
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
