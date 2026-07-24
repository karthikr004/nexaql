import { useState, useCallback, useEffect, useRef } from 'react';
import Markdown from 'react-markdown';

interface Toast {
  message: string;
  type: 'success' | 'error';
}

const STEPS = [
  { key: 'connector', label: 'Connect Database', icon: 'db' },
  { key: 'llm', label: 'Configure LLM', icon: 'key' },
  { key: 'domain', label: 'Define Domain', icon: 'schema' },
  { key: 'test', label: 'Try It Out', icon: 'chat' },
] as const;

const PROVIDER_OPTIONS = [
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'google', label: 'Google' },
  { value: 'meta', label: 'Meta (Muse Spark)' },
];

const MODEL_SUGGESTIONS: Record<string, string[]> = {
  anthropic: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1'],
  openrouter: ['anthropic/claude-sonnet-4-6', 'openai/gpt-4o', 'google/gemini-2.0-flash'],
  google: ['gemini-2.0-flash', 'gemini-2.5-pro'],
  meta: ['muse-spark-1.1'],
};

function StepIcon({ step, size = 18 }: { step: string; size?: number }) {
  const props = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (step) {
    case 'db':
      return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" /></svg>;
    case 'key':
      return <svg {...props}><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78Zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4" /></svg>;
    case 'schema':
      return <svg {...props}><rect width="18" height="18" x="3" y="3" rx="2" /><path d="M3 9h18" /><path d="M9 21V9" /></svg>;
    case 'play':
      return <svg {...props}><polygon points="5 3 19 12 5 21 5 3" /></svg>;
    case 'chat':
      return <svg {...props}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>;
    case 'check':
      return <svg {...props}><polyline points="20 6 9 17 4 12" /></svg>;
    default:
      return null;
  }
}

// ── Step 1: Connect Database ────────────────────────────────────────────────

function ConnectorStep({ onComplete, showToast }: { onComplete: (name: string) => void; showToast: (t: Toast) => void }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [schema, setSchema] = useState('public');
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);
  const [existing, setExisting] = useState<string[]>([]);

  useEffect(() => {
    fetch('/api/connectors')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.connectors?.length) {
          const names: string[] = [];
          for (const c of d.connectors) names.push(c.name);
          setExisting(names);
        }
      })
      .catch(() => {});
  }, []);

  const submit = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), connection_url: url.trim(), schema_name: schema.trim() || 'public', description: desc.trim() }),
      });
      const body = await res.json();
      if (!res.ok) {
        showToast({ message: body.error || 'Failed to connect', type: 'error' });
        return;
      }
      showToast({ message: `Connected — ${body.table_count ?? 0} tables found`, type: 'success' });
      onComplete(name.trim());
    } catch {
      showToast({ message: 'Network error', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const canSubmit = name.trim() && url.trim();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', margin: 0 }}>
        Connect to your database so NexaQL can introspect tables and generate a query schema.
      </p>

      {existing.length > 0 && (
        <div className="v2-card-flat" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div className="v2-label">Existing connectors</div>
            <div className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', marginTop: 2 }}>
              {existing.join(', ')}
            </div>
          </div>
          <button type="button" className="v2-btn v2-btn-secondary v2-btn-sm" onClick={() => { if (existing[0]) onComplete(existing[0]); }}>
            Use existing
          </button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label className="v2-label">Connector name</label>
          <input className="v2-input" placeholder="e.g. my-postgres" value={name} onChange={e => setName(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
        </div>
        <div>
          <label className="v2-label">Connection URL</label>
          <input className="v2-input" placeholder="postgresql://user:pass@host:5432/db" value={url} onChange={e => setUrl(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label className="v2-label">Schema</label>
            <input className="v2-input" placeholder="public" value={schema} onChange={e => setSchema(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
          </div>
          <div style={{ flex: 2 }}>
            <label className="v2-label">Description (optional)</label>
            <input className="v2-input" placeholder="Production read replica" value={desc} onChange={e => setDesc(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          type="button"
          className="v2-btn v2-btn-primary"
          disabled={!canSubmit || saving}
          onClick={submit}
          style={{ opacity: canSubmit && !saving ? 1 : 0.5 }}
        >
          {saving ? 'Connecting...' : 'Connect & continue'}
        </button>
      </div>
    </div>
  );
}

// ── Step 2: Configure LLM ───────────────────────────────────────────────────

function LLMStep({ onComplete, showToast }: { onComplete: () => void; showToast: (t: Toast) => void }) {
  const [provider, setProvider] = useState('anthropic');
  const [model, setModel] = useState('claude-sonnet-4-6');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    fetch('/api/api-keys')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.api_keys?.length) setHasKey(true);
      })
      .catch(() => {});

    fetch('/api/llm-config')
      .then(r => r.ok ? r.json() : null)
      .then(cfg => {
        if (cfg?.provider) {
          setProvider(cfg.provider);
          if (cfg.model) setModel(cfg.model);
        }
      })
      .catch(() => {});
  }, []);

  const submit = async () => {
    setSaving(true);
    try {
      if (apiKey.trim()) {
        const keyRes = await fetch('/api/api-keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: provider, provider, key: apiKey.trim() }),
        });
        if (!keyRes.ok) {
          const body = await keyRes.json();
          showToast({ message: body.error || 'Failed to save API key', type: 'error' });
          setSaving(false);
          return;
        }
      }

      const cfgRes = await fetch('/api/llm-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model }),
      });
      if (!cfgRes.ok) {
        const body = await cfgRes.json();
        showToast({ message: body.error || 'Failed to save LLM config', type: 'error' });
        setSaving(false);
        return;
      }

      showToast({ message: `LLM configured: ${provider} / ${model}`, type: 'success' });
      onComplete();
    } catch {
      showToast({ message: 'Network error', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const suggestions = MODEL_SUGGESTIONS[provider] ?? [];
  const canSubmit = provider && model.trim() && (apiKey.trim() || hasKey);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', margin: 0 }}>
        NexaQL uses an LLM to translate natural language into queries. Configure your preferred provider.
      </p>

      {hasKey && (
        <div className="v2-card-flat" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--v2-teal-500)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span className="v2-body-sm" style={{ color: 'var(--v2-teal-500)' }}>API key already configured</span>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label className="v2-label">Provider</label>
          <select
            className="v2-select"
            value={provider}
            onChange={e => {
              setProvider(e.target.value);
              const models = MODEL_SUGGESTIONS[e.target.value];
              if (models?.length) setModel(models[0] ?? '');
            }}
            style={{ marginTop: 4, width: '100%' }}
          >
            {PROVIDER_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="v2-label">Model</label>
          <select className="v2-select" value={model} onChange={e => setModel(e.target.value)} style={{ marginTop: 4, width: '100%' }}>
            {suggestions.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {!hasKey && (
          <div>
            <label className="v2-label">API key</label>
            <input
              className="v2-input"
              type="password"
              placeholder={`sk-...`}
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              style={{ marginTop: 4, width: '100%' }}
            />
            <div className="v2-caption" style={{ marginTop: 4, color: 'var(--v2-text-tertiary)' }}>
              Stored locally — never sent to NexaQL servers.
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          type="button"
          className="v2-btn v2-btn-primary"
          disabled={!canSubmit || saving}
          onClick={submit}
          style={{ opacity: canSubmit && !saving ? 1 : 0.5 }}
        >
          {saving ? 'Saving...' : 'Save & continue'}
        </button>
      </div>
    </div>
  );
}

// ── Step 3: Define Domain ───────────────────────────────────────────────────

function DomainStep({ connectorName, onComplete, showToast }: { connectorName: string; onComplete: (domain: string) => void; showToast: (t: Toast) => void }) {
  const [domain, setDomain] = useState('');
  const [description, setDescription] = useState('');
  const [schemaName, setSchemaName] = useState('default');
  const [saving, setSaving] = useState(false);
  const [existing, setExisting] = useState<string[]>([]);

  useEffect(() => {
    fetch('/api/domains')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.domains?.length) {
          const names: string[] = [];
          for (const dm of d.domains) names.push(dm.domain ?? dm.name ?? dm);
          setExisting(names);
        }
      })
      .catch(() => {});
  }, []);

  const submit = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/generate-ontology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connector_name: connectorName,
          domain: domain.trim(),
          description: description.trim(),
          output_schema_name: schemaName.trim() || 'default',
          replace: true,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        showToast({ message: body.error || 'Failed to generate domain', type: 'error' });
        setSaving(false);
        return;
      }

      await fetch('/api/domains/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: domain.trim() }),
      });

      showToast({ message: `Domain "${domain.trim()}" created`, type: 'success' });
      onComplete(domain.trim());
    } catch {
      showToast({ message: 'Network error', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const canSubmit = domain.trim() && description.trim();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', margin: 0 }}>
        A domain defines the query schema — which tables, fields, and relationships NexaQL exposes.
        The LLM will auto-generate it from your database structure.
      </p>

      {existing.length > 0 && (
        <div className="v2-card-flat" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div className="v2-label">Existing domains</div>
            <div className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', marginTop: 2 }}>
              {existing.join(', ')}
            </div>
          </div>
          <button type="button" className="v2-btn v2-btn-secondary v2-btn-sm" onClick={() => { if (existing[0]) onComplete(existing[0]); }}>
            Use existing
          </button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label className="v2-label">Domain name</label>
          <input className="v2-input" placeholder="e.g. ecommerce, hr, analytics" value={domain} onChange={e => setDomain(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
        </div>
        <div>
          <label className="v2-label">Description</label>
          <input className="v2-input" placeholder="What kind of data does this domain represent?" value={description} onChange={e => setDescription(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
        </div>
        <div>
          <label className="v2-label">Schema name</label>
          <input className="v2-input" placeholder="default" value={schemaName} onChange={e => setSchemaName(e.target.value)} style={{ marginTop: 4, width: '100%' }} />
        </div>
        <div className="v2-card-flat" style={{ padding: '12px 16px' }}>
          <div className="v2-caption" style={{ color: 'var(--v2-text-tertiary)' }}>
            Using connector: <strong style={{ color: 'var(--v2-text-primary)' }}>{connectorName}</strong>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          type="button"
          className="v2-btn v2-btn-primary"
          disabled={!canSubmit || saving}
          onClick={submit}
          style={{ opacity: canSubmit && !saving ? 1 : 0.5 }}
        >
          {saving ? 'Generating schema...' : 'Generate & continue'}
        </button>
      </div>
    </div>
  );
}

// ── Step 4: Try It Out (Agent Chat) ─────────────────────────────────────────

interface ChatResult {
  question: string;
  summary: string;
  rows: Record<string, unknown>[];
  columnNames: string[];
  rowCount: number;
  nexaqlQuery: string | null;
  error: string | null;
  loading: boolean;
}

const SUGGESTIONS = [
  'Show me all available data',
  'What tables and fields are available?',
  'Show me the first 10 records',
  'Summarize the key metrics',
];

function TryItStep({ domain }: { domain: string }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatResult[]>([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async (question: string) => {
    if (!question.trim() || loading) return;
    setInput('');

    const placeholder: ChatResult = {
      question,
      summary: '',
      rows: [],
      columnNames: [],
      rowCount: 0,
      nexaqlQuery: null,
      error: null,
      loading: true,
    };
    setMessages(prev => [...prev, placeholder]);
    setLoading(true);

    const history = messages.flatMap(m => [
      { role: 'user' as const, content: m.question },
      { role: 'assistant' as const, content: m.summary },
    ]);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history }),
      });
      const data = await res.json();

      const colNames: string[] = [];
      if (data.columns?.length) {
        for (const col of data.columns) {
          colNames.push(typeof col === 'string' ? col : col.name);
        }
      } else if (data.rows?.length) {
        for (const k of Object.keys(data.rows[0])) colNames.push(k);
      }

      const completed: ChatResult = {
        question,
        summary: data.summary ?? data.explanation ?? '',
        rows: data.rows ?? [],
        columnNames: colNames,
        rowCount: data.rowCount ?? 0,
        nexaqlQuery: data.nexaqlQuery ?? null,
        error: data.error ?? null,
        loading: false,
      };
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? completed : m));
    } catch {
      const errResult: ChatResult = {
        question,
        summary: '',
        rows: [],
        columnNames: [],
        rowCount: 0,
        nexaqlQuery: null,
        error: 'Network error — check that the server is running.',
        loading: false,
      };
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? errResult : m));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', margin: 0 }}>
        Ask a question in plain English — NexaQL translates it to a query and returns data from your <strong>{domain}</strong> domain.
      </p>

      {messages.length === 0 && (
        <div>
          <div className="v2-label" style={{ marginBottom: 8 }}>Try asking</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                style={{
                  background: 'var(--v2-bg-hover)',
                  border: '1px solid var(--v2-border)',
                  borderRadius: 'var(--v2-radius-md)',
                  padding: '8px 14px',
                  fontSize: 13,
                  color: 'var(--v2-text-secondary)',
                  cursor: 'pointer',
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--v2-accent)'; e.currentTarget.style.color = 'var(--v2-accent)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--v2-border)'; e.currentTarget.style.color = 'var(--v2-text-secondary)'; }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat messages */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxHeight: 400, overflowY: 'auto' }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* User question */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <div style={{
                background: 'var(--v2-accent)', color: '#fff',
                padding: '8px 14px', borderRadius: '16px 16px 4px 16px',
                fontSize: 13, maxWidth: '80%',
              }}>
                {msg.question}
              </div>
            </div>

            {/* Assistant response */}
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{
                background: 'var(--v2-bg-hover)',
                padding: '12px 16px', borderRadius: '16px 16px 16px 4px',
                fontSize: 13, maxWidth: '100%', width: '100%',
                color: 'var(--v2-text-primary)',
              }}>
                {msg.loading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--v2-text-tertiary)' }}>
                    <div style={{
                      width: 14, height: 14, borderRadius: '50%',
                      border: '2px solid var(--v2-accent)', borderTopColor: 'transparent',
                      animation: 'v2-spin 0.8s linear infinite',
                    }} />
                    Thinking...
                  </div>
                )}

                {!msg.loading && msg.error && (
                  <div style={{ color: 'var(--v2-red-600)', fontSize: 13 }}>{msg.error}</div>
                )}

                {!msg.loading && !msg.error && (
                  <>
                    {msg.summary && (
                      <div style={{ marginBottom: msg.rows.length > 0 ? 12 : 0, lineHeight: 1.6 }}>
                        <Markdown>{msg.summary}</Markdown>
                      </div>
                    )}

                    {msg.nexaqlQuery && (
                      <details style={{ margin: msg.rows.length > 0 ? '0 0 12px' : 0 }}>
                        <summary style={{
                          cursor: 'pointer', fontSize: 11, color: 'var(--v2-text-tertiary)',
                          fontFamily: 'var(--v2-font-mono)', userSelect: 'none',
                        }}>
                          Show NexaQL query
                        </summary>
                        <pre className="v2-code-block" style={{ marginTop: 6, fontSize: 11 }}>
                          {msg.nexaqlQuery}
                        </pre>
                      </details>
                    )}

                    {msg.rows.length > 0 && (
                      <div style={{ overflowX: 'auto' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--v2-teal-500)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                          <span style={{ fontSize: 11, color: 'var(--v2-teal-500)', fontWeight: 500 }}>
                            {msg.rowCount} row{msg.rowCount === 1 ? '' : 's'}
                          </span>
                        </div>
                        <table className="v2-table" style={{ fontSize: 12 }}>
                          <thead>
                            <tr>
                              {msg.columnNames.map(c => (
                                <th key={c} style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 10 }}>{c.replace(/__/g, '.')}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {msg.rows.slice(0, 5).map((row, ri) => (
                              <tr key={ri}>
                                {msg.columnNames.map(c => (
                                  <td key={c} style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11 }}>
                                    {row[c] === null || row[c] === undefined
                                      ? <span style={{ color: 'var(--v2-text-tertiary)', fontStyle: 'italic' }}>null</span>
                                      : String(row[c])}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {msg.rows.length > 5 && (
                          <div style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 4 }}>
                            ...and {msg.rows.length - 5} more rows
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          className="v2-input"
          placeholder="Ask a question about your data..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
          disabled={loading}
          style={{ flex: 1 }}
        />
        <button
          type="button"
          className="v2-btn v2-btn-primary"
          disabled={!input.trim() || loading}
          onClick={() => send(input)}
          style={{ opacity: input.trim() && !loading ? 1 : 0.5, flexShrink: 0 }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── Main Setup Wizard ───────────────────────────────────────────────────────

export default function SetupPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [connectorName, setConnectorName] = useState('');
  const [domainName, setDomainName] = useState('');
  const [toast, setToast] = useState<Toast | null>(null);

  const showToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), t.type === 'error' ? 6000 : 4000);
  }, []);

  const completeStep = (step: number) => {
    setCompletedSteps(prev => {
      const next = new Set(prev);
      next.add(step);
      return next;
    });
    if (step < STEPS.length - 1) {
      setCurrentStep(step + 1);
    }
  };

  const allDone = completedSteps.size >= STEPS.length - 1 && currentStep === STEPS.length - 1;

  return (
    <div style={{ display: 'flex', flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          {/* Header */}
          <div style={{ marginBottom: 32 }}>
            <h1 className="v2-heading-lg" style={{ margin: '0 0 6px' }}>Setup wizard</h1>
            <p className="v2-body-sm" style={{ color: 'var(--v2-text-secondary)', margin: 0 }}>
              Get NexaQL running in 4 steps — connect your data, configure LLM, and start querying.
            </p>
          </div>

          {/* Progress bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 32 }}>
            {STEPS.map((step, i) => {
              const isCompleted = completedSteps.has(i);
              const isCurrent = i === currentStep;
              const isClickable = i <= currentStep || completedSteps.has(i) || (i > 0 && completedSteps.has(i - 1));

              return (
                <div key={step.key} style={{ display: 'flex', alignItems: 'center', flex: i < STEPS.length - 1 ? 1 : undefined }}>
                  <button
                    type="button"
                    onClick={() => { if (isClickable) setCurrentStep(i); }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      background: 'none', border: 'none', cursor: isClickable ? 'pointer' : 'default',
                      padding: '6px 0', whiteSpace: 'nowrap',
                      opacity: isClickable ? 1 : 0.4,
                    }}
                  >
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: isCompleted ? 'var(--v2-teal-500)' : isCurrent ? 'var(--v2-accent)' : 'var(--v2-bg-hover)',
                      color: isCompleted || isCurrent ? '#fff' : 'var(--v2-text-tertiary)',
                      fontSize: 12, fontWeight: 600,
                      transition: 'background 0.2s',
                    }}>
                      {isCompleted ? <StepIcon step="check" size={14} /> : i + 1}
                    </div>
                    <span style={{
                      fontSize: 13, fontWeight: isCurrent ? 600 : 400,
                      color: isCurrent ? 'var(--v2-text-primary)' : 'var(--v2-text-secondary)',
                    }}>
                      {step.label}
                    </span>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div style={{
                      flex: 1, height: 2, marginLeft: 8, marginRight: 8,
                      background: completedSteps.has(i) ? 'var(--v2-teal-500)' : 'var(--v2-border)',
                      borderRadius: 1,
                      transition: 'background 0.3s',
                    }} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Step content */}
          <div className="v2-card" style={{ padding: '24px 28px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 'var(--v2-radius-md)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--v2-accent-subtle)', color: 'var(--v2-accent)',
              }}>
                <StepIcon step={STEPS[currentStep]!.icon} />
              </div>
              <span className="v2-heading-sm">{STEPS[currentStep]!.label}</span>
            </div>

            {currentStep === 0 && (
              <ConnectorStep
                onComplete={(name) => { setConnectorName(name); completeStep(0); }}
                showToast={showToast}
              />
            )}
            {currentStep === 1 && (
              <LLMStep onComplete={() => completeStep(1)} showToast={showToast} />
            )}
            {currentStep === 2 && (
              <DomainStep
                connectorName={connectorName}
                onComplete={(d) => { setDomainName(d); completeStep(2); }}
                showToast={showToast}
              />
            )}
            {currentStep === 3 && (
              <TryItStep domain={domainName} />
            )}
          </div>

          {/* Done banner */}
          {allDone && (
            <div className="v2-card" style={{ marginTop: 20, padding: '20px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', border: '1px solid var(--v2-teal-500)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--v2-teal-500)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className="v2-heading-sm" style={{ color: 'var(--v2-teal-500)' }}>All set! NexaQL is ready.</span>
              </div>
              <a href="/chat" className="v2-btn v2-btn-primary" style={{ textDecoration: 'none' }}>
                Done
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 100,
          padding: '10px 16px', borderRadius: 'var(--v2-radius-md)',
          background: toast.type === 'error' ? 'var(--v2-red-600)' : 'var(--v2-teal-600)',
          color: '#fff', fontSize: 13, fontWeight: 500,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        }}>
          {toast.message}
        </div>
      )}
    </div>
  );
}
