import { useState, useCallback, useEffect } from 'react';
import Toast from './Toast';
import type { ToastData } from './Toast';

interface BizEntry {
  id: number;
  term: string;
  definition: string;
  sql_hint: string | null;
  tags: string[];
}

interface BusinessOntologyEditorProps {
  domainName: string;
}

const EMPTY_FORM = { term: '', definition: '', sql_hint: '', tags: '' };

export default function BusinessOntologyEditor({ domainName }: BusinessOntologyEditorProps) {
  const [entries, setEntries] = useState<BizEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastData | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const fetchEntries = useCallback(async () => {
    try {
      const res = await fetch(`/api/domains/${domainName}/ontology/business`, { credentials: 'include' });
      if (res.ok) setEntries(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, [domainName]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setShowForm(false);
    setEditingId(null);
  };

  const handleSave = async () => {
    if (!form.term.trim() || !form.definition.trim()) {
      setToast({ type: 'error', message: 'Term and definition are required' });
      return;
    }
    const body = {
      term: form.term.trim(),
      definition: form.definition.trim(),
      sql_hint: form.sql_hint.trim() || null,
      tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
    };

    const url = editingId
      ? `/api/domains/${domainName}/ontology/business/${editingId}`
      : `/api/domains/${domainName}/ontology/business`;
    const method = editingId ? 'PATCH' : 'POST';

    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'include',
    });

    if (res.ok) {
      setToast({ type: 'success', message: editingId ? 'Entry updated' : 'Entry created' });
      resetForm();
      fetchEntries();
    } else {
      const data = await res.json().catch(() => ({}));
      setToast({ type: 'error', message: data.detail || 'Failed to save' });
    }
  };

  const handleEdit = (entry: BizEntry) => {
    setForm({
      term: entry.term,
      definition: entry.definition,
      sql_hint: entry.sql_hint || '',
      tags: entry.tags.join(', '),
    });
    setEditingId(entry.id);
    setShowForm(true);
  };

  const handleDelete = async (entry: BizEntry) => {
    const res = await fetch(`/api/domains/${domainName}/ontology/business/${entry.id}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    if (res.ok) {
      setToast({ type: 'success', message: `Deleted "${entry.term}"` });
      fetchEntries();
    }
  };

  if (loading) {
    return <p className="v2-body-sm" style={{ color: 'var(--v2-text-tertiary)', padding: 16 }}>Loading...</p>;
  }

  return (
    <div>
      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <p className="v2-body-sm">
          Domain-specific terms, rules, and definitions that help the agent understand your data.
        </p>
        {!showForm && (
          <button
            type="button"
            className="v2-btn v2-btn-primary v2-btn-sm"
            onClick={() => { resetForm(); setShowForm(true); }}
          >
            Add entry
          </button>
        )}
      </div>

      {showForm && (
        <div
          style={{
            padding: 16,
            marginBottom: 16,
            borderRadius: 'var(--v2-radius-md)',
            border: '1px solid var(--v2-border)',
            background: 'var(--v2-bg-surface)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="v2-body-sm" style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Term</label>
              <input
                className="v2-input"
                value={form.term}
                onChange={(e) => setForm({ ...form, term: e.target.value })}
                placeholder="e.g. 2DP, AOV, active customer"
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <label className="v2-body-sm" style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>Definition</label>
              <textarea
                className="v2-input"
                value={form.definition}
                onChange={(e) => setForm({ ...form, definition: e.target.value })}
                placeholder="Plain English definition of what this term means"
                rows={2}
                style={{ width: '100%', resize: 'vertical', fontFamily: 'var(--v2-font-sans)' }}
              />
            </div>
            <div>
              <label className="v2-body-sm" style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>
                SQL Hint <span style={{ fontWeight: 400, color: 'var(--v2-text-tertiary)' }}>(optional)</span>
              </label>
              <input
                className="v2-input"
                value={form.sql_hint}
                onChange={(e) => setForm({ ...form, sql_hint: e.target.value })}
                placeholder="e.g. orders.total - orders.refund_amount"
                style={{ width: '100%', fontFamily: 'var(--v2-font-mono)', fontSize: 12 }}
              />
            </div>
            <div>
              <label className="v2-body-sm" style={{ fontWeight: 600, marginBottom: 4, display: 'block' }}>
                Tags <span style={{ fontWeight: 400, color: 'var(--v2-text-tertiary)' }}>(comma-separated, optional)</span>
              </label>
              <input
                className="v2-input"
                value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
                placeholder="e.g. shipping, sla, delivery"
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="v2-btn v2-btn-secondary v2-btn-sm" onClick={resetForm}>
                Cancel
              </button>
              <button type="button" className="v2-btn v2-btn-primary v2-btn-sm" onClick={handleSave}>
                {editingId ? 'Update' : 'Add'}
              </button>
            </div>
          </div>
        </div>
      )}

      {entries.length === 0 && !showForm ? (
        <div
          style={{
            padding: 32,
            textAlign: 'center',
            color: 'var(--v2-text-tertiary)',
            border: '1px dashed var(--v2-border)',
            borderRadius: 'var(--v2-radius-md)',
          }}
        >
          <p style={{ fontSize: 13, marginBottom: 4 }}>No business context defined yet</p>
          <p style={{ fontSize: 12 }}>Add terms, rules, and definitions to help the agent understand your domain</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {entries.map((entry) => (
            <div
              key={entry.id}
              style={{
                padding: '12px 16px',
                borderRadius: 'var(--v2-radius-md)',
                border: '1px solid var(--v2-border)',
                background: 'var(--v2-bg-surface)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--v2-text-primary)' }}>
                      {entry.term}
                    </span>
                    {entry.tags.length > 0 && (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {entry.tags.map((tag) => (
                          <span
                            key={tag}
                            style={{
                              fontSize: 10,
                              padding: '1px 6px',
                              borderRadius: 'var(--v2-radius-full)',
                              background: 'var(--v2-purple-50)',
                              color: 'var(--v2-purple-700)',
                              fontWeight: 500,
                            }}
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <p style={{ fontSize: 13, color: 'var(--v2-text-secondary)', margin: 0 }}>
                    {entry.definition}
                  </p>
                  {entry.sql_hint && (
                    <code
                      style={{
                        display: 'inline-block',
                        marginTop: 6,
                        fontSize: 11,
                        fontFamily: 'var(--v2-font-mono)',
                        padding: '2px 8px',
                        borderRadius: 'var(--v2-radius-sm)',
                        background: 'var(--v2-bg-hover)',
                        color: 'var(--v2-text-secondary)',
                      }}
                    >
                      {entry.sql_hint}
                    </code>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                  <button
                    type="button"
                    className="v2-thread-action-btn"
                    onClick={() => handleEdit(entry)}
                    title="Edit"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className="v2-thread-action-btn v2-thread-delete"
                    onClick={() => handleDelete(entry)}
                    title="Delete"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
