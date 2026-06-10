/**
 * API Keys + LLM Configuration panel.
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

interface LlmStatus {
  provider: string;
  model: string;
  base_url: string;
  has_api_key: boolean;
  ollama?: { running: boolean; models: string[]; has_default_model: boolean; default_model: string };
}

interface Props {
  onToast: (t: ToastData) => void;
}

export default function ApiKeysPanel({ onToast }: Props) {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [provider, setProvider] = useState('openrouter');
  const [name, setName] = useState('');
  const [keyVal, setKeyVal] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/api-keys');
      if (res.ok) setKeys((await res.json()).api_keys ?? []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  const fetchLlm = useCallback(async () => {
    try {
      const res = await fetch('/api/llm/status');
      if (res.ok) setLlm(await res.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchKeys(); fetchLlm(); }, [fetchKeys, fetchLlm]);

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
        setShowAdd(false); setName(''); setProvider('openrouter'); setKeyVal('');
        fetchKeys(); fetchLlm();
      } else {
        onToast({ message: body.error || 'Failed to save', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally { setSaving(false); }
  }, [name, provider, keyVal, fetchKeys, fetchLlm, onToast]);

  const handleDelete = useCallback(async (prov: string) => {
    try {
      const res = await fetch(`/api/api-keys/${encodeURIComponent(prov)}`, { method: 'DELETE' });
      if (res.ok) { onToast({ message: `Deleted "${prov}" key`, type: 'success' }); fetchKeys(); }
      else { const b = await res.json(); onToast({ message: b.error || 'Delete failed', type: 'error' }); }
    } catch (err) { onToast({ message: `Error: ${err}`, type: 'error' }); }
  }, [fetchKeys, onToast]);

  return (
    <>
      <SectionHeader title="LLM Configuration" subtitle="Model provider settings" />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Active provider card */}
        {llm && (
          <div className="rounded border p-4 space-y-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs" style={{ color: 'var(--text-primary)' }}>Active Provider</span>
              <span className="rounded px-1.5 py-0.5 text-[9px] uppercase border font-semibold" style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>{llm.provider || 'none'}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div><span style={{ color: 'var(--text-muted)' }}>Model: </span><span className="font-mono" style={{ color: 'var(--text-primary)' }}>{llm.model || '(not set)'}</span></div>
              <div><span style={{ color: 'var(--text-muted)' }}>API Key: </span><span style={{ color: llm.has_api_key ? 'var(--badge-green-text)' : 'var(--error)' }}>{llm.has_api_key ? 'configured' : 'missing'}</span></div>
            </div>
          </div>
        )}

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
                <option value="openrouter">OpenRouter (all models)</option>
                <option value="anthropic">Anthropic (direct)</option>
                <option value="openai">OpenAI (direct)</option>
                <option value="google">Google (direct)</option>
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

        {/* Info box */}
        <div className="rounded border px-4 py-3 text-[11px] leading-relaxed space-y-1" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
          <div>Keys are stored in <code style={{ color: 'var(--accent)' }}>~/.nexaql/nexaql.db</code> and never leave your machine.</div>
        </div>
      </div>
    </>
  );
}
