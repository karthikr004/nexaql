import { useState, useCallback, useEffect } from 'react';
import CloudStorageSettings from '../components/CloudStorageSettings';

interface ApiKeyInfo {
  provider: string;
  name: string;
  key_masked: string;
  created_at: string;
  is_active: boolean;
}

interface LLMConfig {
  provider: string;
  model: string;
}

interface Toast {
  message: string;
  type: 'success' | 'error' | 'info';
}

const MODEL_SUGGESTIONS: Record<string, string[]> = {
  anthropic: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1'],
  openrouter: ['anthropic/claude-sonnet-4-6', 'openai/gpt-4o', 'google/gemini-2.0-flash'],
  google: ['gemini-2.0-flash', 'gemini-2.5-pro'],
  meta: ['muse-spark-1.1'],
};

const PROVIDER_OPTIONS = [
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'google', label: 'Google' },
  { value: 'meta', label: 'Meta (Muse Spark)' },
];

export default function SettingsPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [provider, setProvider] = useState('anthropic');
  const [keyName, setKeyName] = useState('');
  const [keyVal, setKeyVal] = useState('');
  const [saving, setSaving] = useState(false);

  const [llmConfig, setLlmConfig] = useState<LLMConfig>({ provider: '', model: '' });
  const [activeProvider, setActiveProvider] = useState('');
  const [modelInput, setModelInput] = useState('');
  const [savingModel, setSavingModel] = useState(false);

  const [toast, setToast] = useState<Toast | null>(null);

  const showToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), 4000);
  }, []);

  const fetchKeys = useCallback(async () => {
    try {
      const res = await fetch('/api/api-keys');
      if (res.ok) {
        const data = await res.json();
        setKeys(data.api_keys ?? []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchLLMConfig = useCallback(async () => {
    try {
      const res = await fetch('/api/llm-config');
      if (res.ok) {
        const cfg = await res.json();
        setLlmConfig(cfg);
        setActiveProvider(cfg.provider || '');
        setModelInput(cfg.model || '');
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => { fetchKeys(); fetchLLMConfig(); }, [fetchKeys, fetchLLMConfig]);

  const handleSaveKey = useCallback(async () => {
    if (!provider.trim() || !keyVal.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/api-keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: keyName.trim() || provider.trim(),
          provider: provider.trim(),
          key: keyVal.trim(),
        }),
      });
      const body = await res.json();
      if (res.ok) {
        showToast({ message: `API key for "${provider}" saved`, type: 'success' });
        setShowAdd(false);
        setKeyName('');
        setProvider('anthropic');
        setKeyVal('');
        fetchKeys();
        fetchLLMConfig();
      } else {
        showToast({ message: body.error || 'Failed to save', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [keyName, provider, keyVal, fetchKeys, fetchLLMConfig, showToast]);

  const handleDeleteKey = useCallback(async (prov: string) => {
    try {
      const res = await fetch(`/api/api-keys/${encodeURIComponent(prov)}`, { method: 'DELETE' });
      if (res.ok) {
        showToast({ message: `Deleted "${prov}" key`, type: 'success' });
        fetchKeys();
        fetchLLMConfig();
      } else {
        const b = await res.json();
        showToast({ message: b.error || 'Delete failed', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    }
  }, [fetchKeys, fetchLLMConfig, showToast]);

  const handleSaveModel = useCallback(async () => {
    if (!modelInput.trim()) return;
    setSavingModel(true);
    try {
      const res = await fetch('/api/llm-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: activeProvider, model: modelInput.trim() }),
      });
      const body = await res.json();
      if (res.ok) {
        showToast({ message: `Model updated to "${modelInput.trim()}"`, type: 'success' });
        fetchLLMConfig();
      } else {
        showToast({ message: body.error || 'Failed to update model', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSavingModel(false);
    }
  }, [activeProvider, modelInput, fetchLLMConfig, showToast]);

  const suggestions = MODEL_SUGGESTIONS[activeProvider] || [];
  const configChanged = modelInput.trim() !== (llmConfig.model || '') || activeProvider !== (llmConfig.provider || '');
  const configuredProviders = keys.map((k) => k.provider);

  return (
    <div style={{ padding: 32, maxWidth: 960, margin: '0 auto' }}>
      {/* Toast */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 20,
            right: 20,
            zIndex: 1000,
            padding: '10px 16px',
            borderRadius: 'var(--v2-radius-md)',
            fontSize: 13,
            fontWeight: 500,
            maxWidth: 400,
            boxShadow: 'var(--v2-shadow-md)',
            background: toast.type === 'success' ? 'var(--v2-teal-50)' : toast.type === 'error' ? 'var(--v2-red-50)' : 'var(--v2-bg-elevated)',
            color: toast.type === 'success' ? 'var(--v2-teal-700)' : toast.type === 'error' ? 'var(--v2-red-700)' : 'var(--v2-text-primary)',
            border: `1px solid ${toast.type === 'success' ? 'var(--v2-teal-500)' : toast.type === 'error' ? 'var(--v2-red-500)' : 'var(--v2-border)'}`,
          }}
        >
          {toast.message}
        </div>
      )}

      {/* Page header */}
      <div style={{ marginBottom: 32 }}>
        <h1 className="v2-heading-lg">Settings</h1>
        <p className="v2-body-sm" style={{ marginTop: 4 }}>API keys, LLM provider, and cloud storage configuration</p>
      </div>

      {/* ── API Keys Section ─────────────────────────────────────── */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 className="v2-heading-md">API Keys</h2>
          {!showAdd && (
            <button
              type="button"
              className="v2-btn v2-btn-primary v2-btn-sm"
              onClick={() => setShowAdd(true)}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Add Key
            </button>
          )}
        </div>

        {/* Add key form */}
        {showAdd && (
          <div className="v2-card" style={{ padding: 24, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <h3 className="v2-heading-sm">Add API Key</h3>
              <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={() => setShowAdd(false)}>Cancel</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Provider</label>
                <select
                  className="v2-select"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                >
                  {PROVIDER_OPTIONS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Display Name</label>
                <input
                  className="v2-input"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder={`${provider} production`}
                />
              </div>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>API Key</label>
                <input
                  className="v2-input"
                  type="password"
                  value={keyVal}
                  onChange={(e) => setKeyVal(e.target.value)}
                  placeholder="sk-..."
                  style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13 }}
                />
              </div>
              <div>
                <button
                  type="button"
                  className="v2-btn v2-btn-primary"
                  onClick={handleSaveKey}
                  disabled={saving || !provider.trim() || !keyVal.trim()}
                  style={{ opacity: saving || !provider.trim() || !keyVal.trim() ? 0.5 : 1 }}
                >
                  {saving ? 'Saving...' : 'Save Key'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Key list */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <p className="v2-body-sm">Loading API keys...</p>
          </div>
        ) : keys.length === 0 ? (
          <div className="v2-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
            </svg>
            <p className="v2-heading-md" style={{ marginBottom: 4 }}>No API keys</p>
            <p className="v2-body-sm">Add an LLM provider key to enable Agent Chat</p>
          </div>
        ) : (
          <div className="v2-card">
            <table className="v2-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Provider</th>
                  <th>Key</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.provider}>
                    <td style={{ fontWeight: 500 }}>{k.name}</td>
                    <td>
                      <span className="v2-badge v2-badge-teal">{k.provider}</span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                        {k.key_masked}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="v2-btn v2-btn-ghost v2-btn-sm"
                          onClick={() => handleDeleteKey(k.provider)}
                          style={{ color: 'var(--v2-red-500)' }}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Active Model Section ─────────────────────────────────── */}
      {configuredProviders.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Active Model</h2>
          <div className="v2-card" style={{ padding: 24 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Provider</label>
                <select
                  className="v2-select"
                  value={activeProvider}
                  onChange={(e) => {
                    const newProv = e.target.value;
                    setActiveProvider(newProv);
                    const defaults = MODEL_SUGGESTIONS[newProv];
                    if (defaults && defaults.length > 0) {
                      setModelInput(defaults[0] ?? '');
                    } else {
                      setModelInput('');
                    }
                  }}
                >
                  {configuredProviders.map((p) => (
                    <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Model</label>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input
                    className="v2-input"
                    value={modelInput}
                    onChange={(e) => setModelInput(e.target.value)}
                    placeholder="e.g. claude-sonnet-4-6"
                    style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13, flex: 1 }}
                  />
                  <button
                    type="button"
                    className="v2-btn v2-btn-primary"
                    onClick={handleSaveModel}
                    disabled={savingModel || !modelInput.trim() || !configChanged}
                    style={{ opacity: savingModel || !modelInput.trim() || !configChanged ? 0.5 : 1 }}
                  >
                    {savingModel ? 'Saving...' : 'Update'}
                  </button>
                </div>
                {suggestions.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
                    {suggestions.map((m) => (
                      <button
                        key={m}
                        type="button"
                        className="v2-btn v2-btn-sm"
                        onClick={() => setModelInput(m)}
                        style={{
                          fontFamily: 'var(--v2-font-mono)',
                          fontSize: 11,
                          border: `1px solid ${modelInput === m ? 'var(--v2-accent)' : 'var(--v2-border)'}`,
                          background: modelInput === m ? 'var(--v2-accent-subtle)' : 'transparent',
                          color: modelInput === m ? 'var(--v2-accent-text)' : 'var(--v2-text-secondary)',
                        }}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Cloud Storage Section ──────────────────────────────── */}
      <div style={{ marginBottom: 32 }}>
        <CloudStorageSettings
          onToast={(message, type) => showToast({ message, type })}
        />
      </div>

      {/* Info box */}
      <div
        className="v2-card-flat"
        style={{
          padding: '12px 16px',
          fontSize: 12,
          color: 'var(--v2-text-secondary)',
          lineHeight: 1.5,
        }}
      >
        Keys are stored in <code style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, color: 'var(--v2-accent-text)' }}>~/.nexaql/nexaql.db</code> and never leave your machine.
      </div>
    </div>
  );
}
