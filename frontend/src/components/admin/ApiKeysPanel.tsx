/**
 * API Keys panel with model selector.
 */
import { useState, useCallback, useEffect } from 'react';
import { SectionHeader, inputStyle, labelStyle, type ToastData } from './shared';

export interface ApiKeyInfo {
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

const MODEL_SUGGESTIONS: Record<string, string[]> = {
  anthropic: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1'],
  openrouter: ['anthropic/claude-sonnet-4-6', 'openai/gpt-4o', 'google/gemini-2.0-flash'],
  google: ['gemini-2.0-flash', 'gemini-2.5-pro'],
  meta: ['muse-spark-1.1'],
};

interface Props {
  onToast: (t: ToastData) => void;
}

export default function ApiKeysPanel({ onToast }: Props) {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [provider, setProvider] = useState('anthropic');
  const [name, setName] = useState('');
  const [keyVal, setKeyVal] = useState('');
  const [saving, setSaving] = useState(false);

  // LLM model config
  const [llmConfig, setLlmConfig] = useState<LLMConfig>({ provider: '', model: '' });
  const [activeProvider, setActiveProvider] = useState('');
  const [modelInput, setModelInput] = useState('');
  const [savingModel, setSavingModel] = useState(false);

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/api-keys');
      if (res.ok) setKeys((await res.json()).api_keys ?? []);
    } catch { /* ignore */ } finally { setLoading(false); }
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
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchKeys(); fetchLLMConfig(); }, [fetchKeys, fetchLLMConfig]);

  const handleSave = useCallback(async () => {
    if (!provider.trim() || !keyVal.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/api-keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() || provider.trim(), provider: provider.trim(), key: keyVal.trim() }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: `API key for "${provider}" saved`, type: 'success' });
        setShowAdd(false); setName(''); setProvider('anthropic'); setKeyVal('');
        fetchKeys();
        fetchLLMConfig();
      } else {
        onToast({ message: body.error || 'Failed to save', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally { setSaving(false); }
  }, [name, provider, keyVal, fetchKeys, fetchLLMConfig, onToast]);

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
        onToast({ message: `Model updated to "${modelInput.trim()}"`, type: 'success' });
        fetchLLMConfig();
      } else {
        onToast({ message: body.error || 'Failed to update model', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally { setSavingModel(false); }
  }, [modelInput, fetchLLMConfig, onToast]);

  const handleDelete = useCallback(async (prov: string) => {
    try {
      const res = await fetch(`/api/api-keys/${encodeURIComponent(prov)}`, { method: 'DELETE' });
      if (res.ok) { onToast({ message: `Deleted "${prov}" key`, type: 'success' }); fetchKeys(); fetchLLMConfig(); }
      else { const b = await res.json(); onToast({ message: b.error || 'Delete failed', type: 'error' }); }
    } catch (err) { onToast({ message: `Error: ${err}`, type: 'error' }); }
  }, [fetchKeys, fetchLLMConfig, onToast]);

  const suggestions = MODEL_SUGGESTIONS[activeProvider] || [];
  const configChanged = modelInput.trim() !== (llmConfig.model || '') || activeProvider !== (llmConfig.provider || '');
  const configuredProviders = keys.map((k) => k.provider);

  return (
    <>
      <SectionHeader title="API Keys" subtitle="Manage LLM provider keys" />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Add key form */}
        {showAdd ? (
          <div className="rounded border p-4 space-y-3" style={{ borderColor: 'var(--badge-amber-border)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs" style={{ color: 'var(--text-primary)' }}>Add API Key</span>
              <button type="button" onClick={() => setShowAdd(false)} className="text-xs" style={{ color: 'var(--text-secondary)' }}>Cancel</button>
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Provider</label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle}>
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
                <option value="openrouter">OpenRouter</option>
                <option value="google">Google</option>
                <option value="meta">Meta (Muse Spark)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Display Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={`${provider} production`} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>API Key</label>
              <input type="password" value={keyVal} onChange={(e) => setKeyVal(e.target.value)} placeholder="sk-..." className="w-full rounded border px-2 py-1.5 text-sm font-mono focus:outline-none" style={inputStyle} />
            </div>
            <button type="button" onClick={handleSave} disabled={saving || !provider.trim() || !keyVal.trim()} className="rounded px-4 py-1.5 text-xs font-semibold bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577] disabled:opacity-50">
              {saving ? 'Saving...' : 'Save Key'}
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => setShowAdd(true)} className="rounded border border-dashed px-4 py-2 text-xs" style={{ borderColor: 'var(--border)', color: 'var(--badge-amber-text)' }}>
            + Add API Key
          </button>
        )}

        {/* Key list */}
        {loading ? <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Loading...</p> : (
          <div className="space-y-2">
            {keys.map((k) => (
              <div key={k.provider} className="flex items-center justify-between rounded border px-4 py-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{k.name}</span>
                    <span className="rounded px-1.5 py-0.5 text-[9px] uppercase border" style={{ borderColor: 'var(--badge-green-border)', backgroundColor: 'var(--badge-green-bg)', color: 'var(--badge-green-text)' }}>{k.provider}</span>
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>{k.key_masked}</span>
                </div>
                <button type="button" onClick={() => handleDelete(k.provider)} className="rounded px-2 py-1 text-[10px] border" style={{ borderColor: 'var(--border)', color: 'var(--error)' }}>Delete</button>
              </div>
            ))}
          </div>
        )}

        {/* Active Model selector */}
        {configuredProviders.length > 0 && (
          <div className="rounded border p-4 space-y-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
            <span className="font-semibold text-xs" style={{ color: 'var(--text-primary)' }}>Active Model</span>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>
                Provider
              </label>
              <select
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
                className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
                style={inputStyle}
              >
                {configuredProviders.map((p) => (
                  <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>
                Model
              </label>
              <div className="flex gap-2">
                <input
                  value={modelInput}
                  onChange={(e) => setModelInput(e.target.value)}
                  placeholder="e.g. claude-sonnet-4-6"
                  className="flex-1 rounded border px-2 py-1.5 text-sm font-mono focus:outline-none"
                  style={inputStyle}
                  list="model-suggestions"
                />
                <datalist id="model-suggestions">
                  {suggestions.map((m) => <option key={m} value={m} />)}
                </datalist>
                <button
                  type="button"
                  onClick={handleSaveModel}
                  disabled={savingModel || !modelInput.trim() || !configChanged}
                  className="rounded px-4 py-1.5 text-xs font-semibold bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577] disabled:opacity-50"
                >
                  {savingModel ? 'Saving...' : 'Update'}
                </button>
              </div>
              {suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {suggestions.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setModelInput(m)}
                      className="rounded px-2 py-0.5 text-[10px] font-mono border hover:opacity-80"
                      style={{
                        borderColor: modelInput === m ? 'var(--badge-green-border)' : 'var(--border)',
                        backgroundColor: modelInput === m ? 'var(--badge-green-bg)' : 'transparent',
                        color: modelInput === m ? 'var(--badge-green-text)' : 'var(--text-secondary)',
                      }}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Info box */}
        <div className="rounded border px-4 py-3 text-[11px] leading-relaxed space-y-1" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
          <div>Keys are stored in <code style={{ color: 'var(--accent)' }}>~/.nexaql/nexaql.db</code> and never leave your machine.</div>
        </div>
      </div>
    </>
  );
}
