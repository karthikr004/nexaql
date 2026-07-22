import { useState, useCallback, useEffect } from 'react';
import type {
  OntologyData,
  NodeData,
  FieldData,
  EdgeData,
  SpecialFilterData,
  RowPolicyData,
  RoleDefData,
  AccessFunctionData,
} from '../../types';

// ── Types ────────────────────────────────────────────────────────────────────

interface SchemaInfo {
  id: number;
  name: string;
  connector_id: number;
  connector_name?: string;
  node_count: number;
  created_at: string;
  updated_at: string;
}

interface ConnectorInfo {
  id?: number;
  name: string;
  db_type: string;
}

interface ToastData {
  message: string;
  type: 'success' | 'error';
}

type TopTab = 'nodes' | 'roles' | 'access';
type NodeTab = 'general' | 'fields' | 'edges' | 'filters' | 'access';

interface Props {
  domainName: string;
  schema: SchemaInfo;
  connectors: ConnectorInfo[];
  onToast: (t: ToastData) => void;
  onOntologyChanged: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const FIELD_TYPES = ['string', 'integer', 'numeric', 'boolean', 'date', 'enum'];
const JOIN_TYPES = ['JOIN', 'LEFT JOIN'];

function countFields(node: NodeData): number {
  return Object.keys(node.fields ?? {}).length;
}

function countEdges(node: NodeData): number {
  return Object.keys(node.edges ?? {}).length;
}

function countFilters(node: NodeData): number {
  return Object.keys(node.special_filters ?? {}).length;
}

// ── Inline editable input ────────────────────────────────────────────────────

function InlineInput({
  value,
  onChange,
  placeholder,
  mono,
  multiline,
  style,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
  multiline?: boolean;
  style?: React.CSSProperties;
}) {
  const baseStyle: React.CSSProperties = {
    width: '100%',
    padding: '6px 10px',
    borderRadius: 'var(--v2-radius-sm)',
    border: '1px solid var(--v2-border)',
    background: 'var(--v2-bg-input)',
    color: 'var(--v2-text-primary)',
    fontFamily: mono ? 'var(--v2-font-mono)' : 'var(--v2-font-sans)',
    fontSize: 13,
    outline: 'none',
    transition: 'border-color var(--v2-transition-fast)',
    ...style,
  };

  if (multiline) {
    return (
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={3}
        style={{ ...baseStyle, resize: 'vertical', lineHeight: 1.5 }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--v2-border-focus)'; }}
        onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--v2-border)'; }}
      />
    );
  }

  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={baseStyle}
      onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--v2-border-focus)'; }}
      onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--v2-border)'; }}
    />
  );
}

// ── Tab bar ──────────────────────────────────────────────────────────────────

function TabBar<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: T; label: string; count?: number }[];
  active: T;
  onChange: (t: T) => void;
}) {
  return (
    <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--v2-border)' }}>
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            style={{
              padding: '8px 16px',
              fontSize: 13,
              fontWeight: 500,
              fontFamily: 'var(--v2-font-sans)',
              color: isActive ? 'var(--v2-accent-text)' : 'var(--v2-text-secondary)',
              background: 'none',
              border: 'none',
              borderBottom: isActive ? '2px solid var(--v2-accent)' : '2px solid transparent',
              cursor: 'pointer',
              transition: 'all var(--v2-transition-fast)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {t.label}
            {t.count !== undefined && (
              <span
                style={{
                  fontSize: 11,
                  padding: '1px 6px',
                  borderRadius: 'var(--v2-radius-full)',
                  background: isActive ? 'var(--v2-accent-subtle)' : 'var(--v2-bg-hover)',
                  color: isActive ? 'var(--v2-accent-text)' : 'var(--v2-text-tertiary)',
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── General Tab ──────────────────────────────────────────────────────────────

function GeneralTab({
  node,
  connectorNames,
  onUpdate,
}: {
  node: NodeData;
  connectorNames: string[];
  onUpdate: (updater: (n: NodeData) => NodeData) => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 600 }}>
      <div>
        <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Table</label>
        <InlineInput
          value={node.table ?? ''}
          onChange={(v) => onUpdate((n) => ({ ...n, table: v }))}
          placeholder="Database table name"
          mono
        />
      </div>
      <div>
        <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Primary key</label>
        <InlineInput
          value={node.primary_key ?? ''}
          onChange={(v) => onUpdate((n) => ({ ...n, primary_key: v }))}
          placeholder="e.g. id"
          mono
        />
      </div>
      <div>
        <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Description</label>
        <InlineInput
          value={node.description ?? ''}
          onChange={(v) => onUpdate((n) => ({ ...n, description: v }))}
          placeholder="What this node represents"
          multiline
        />
      </div>
      <div>
        <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Datasource</label>
        <select
          className="v2-select"
          value={node.datasource ?? ''}
          onChange={(e) => onUpdate((n) => ({ ...n, datasource: e.target.value || undefined }))}
          style={{ maxWidth: 300 }}
        >
          <option value="">Default</option>
          {connectorNames.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

// ── Fields Tab ───────────────────────────────────────────────────────────────

function FieldsTab({
  node,
  onUpdate,
}: {
  node: NodeData;
  onUpdate: (updater: (n: NodeData) => NodeData) => void;
}) {
  const [newFieldName, setNewFieldName] = useState('');
  const fields = node.fields ?? {};
  const fieldNames = Object.keys(fields);

  const addField = () => {
    const name = newFieldName.trim();
    if (!name || fields[name]) return;
    onUpdate((n) => ({
      ...n,
      fields: {
        ...n.fields,
        [name]: { type: 'string', description: '', filterable: false },
      },
    }));
    setNewFieldName('');
  };

  const updateField = (fname: string, updater: (f: FieldData) => FieldData) => {
    onUpdate((n) => {
      const existing = n.fields[fname];
      if (!existing) return n;
      const updated = { ...n.fields };
      updated[fname] = updater(existing);
      return { ...n, fields: updated };
    });
  };

  const removeField = (fname: string) => {
    if (!window.confirm(`Delete field "${fname}"?`)) return;
    onUpdate((n) => {
      const updated = { ...n.fields };
      delete updated[fname];
      return { ...n, fields: updated };
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Add field */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <InlineInput
          value={newFieldName}
          onChange={setNewFieldName}
          placeholder="New field name"
          mono
          style={{ maxWidth: 240 }}
        />
        <button
          type="button"
          onClick={addField}
          disabled={!newFieldName.trim()}
          className="v2-btn v2-btn-primary v2-btn-sm"
        >
          + Add field
        </button>
      </div>

      {fieldNames.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13 }}>
          No fields defined yet.
        </div>
      ) : (
        <div className="v2-card" style={{ overflow: 'auto' }}>
          <table className="v2-table" style={{ minWidth: 700 }}>
            <thead>
              <tr>
                <th style={{ width: 160 }}>Name</th>
                <th style={{ width: 110 }}>Type</th>
                <th>Description</th>
                <th style={{ width: 80, textAlign: 'center' }}>Filterable</th>
                <th style={{ width: 60 }} />
              </tr>
            </thead>
            <tbody>
              {fieldNames.map((fname) => {
                const f = fields[fname];
                if (!f) return null;
                return (
                  <tr key={fname}>
                    <td>
                      <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, fontWeight: 500 }}>
                        {fname}
                      </span>
                      {f.derived && (
                        <span className="v2-badge v2-badge-amber" style={{ marginLeft: 6, fontSize: 10 }}>derived</span>
                      )}
                      {f.pii && (
                        <span className="v2-badge v2-badge-red" style={{ marginLeft: 6, fontSize: 10 }}>PII</span>
                      )}
                    </td>
                    <td>
                      <select
                        className="v2-select"
                        value={f.type}
                        onChange={(e) => updateField(fname, (fld) => ({ ...fld, type: e.target.value }))}
                        style={{ fontSize: 12, padding: '3px 6px', minWidth: 90 }}
                      >
                        {FIELD_TYPES.map((t) => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <InlineInput
                        value={f.description}
                        onChange={(v) => updateField(fname, (fld) => ({ ...fld, description: v }))}
                        placeholder="Field description"
                        style={{ fontSize: 12, padding: '3px 8px' }}
                      />
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={f.filterable ?? false}
                        onChange={(e) => updateField(fname, (fld) => ({ ...fld, filterable: e.target.checked }))}
                        style={{ accentColor: 'var(--v2-accent)' }}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => removeField(fname)}
                        className="v2-icon-btn"
                        style={{ width: 24, height: 24, color: 'var(--v2-red-500)' }}
                        title="Delete field"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Enum values for enum fields */}
      {fieldNames
        .filter((fname) => fields[fname]?.type === 'enum')
        .map((fname) => {
          const fld = fields[fname];
          if (!fld) return null;
          return (
            <div key={fname} style={{ padding: 12, borderRadius: 'var(--v2-radius-md)', background: 'var(--v2-bg-surface)', border: '1px solid var(--v2-border-light)' }}>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>
                Enum values for <span style={{ fontFamily: 'var(--v2-font-mono)' }}>{fname}</span>
              </label>
              <InlineInput
                value={(fld.values ?? []).join(', ')}
                onChange={(v) => {
                  const vals = v.split(',').map((s) => s.trim()).filter(Boolean);
                  updateField(fname, (f) => ({ ...f, values: vals }));
                }}
                placeholder="value1, value2, value3"
              />
            </div>
          );
        })
      }
    </div>
  );
}

// ── Edges Tab ────────────────────────────────────────────────────────────────

function EdgesTab({
  node,
  nodeNames,
  onUpdate,
}: {
  node: NodeData;
  nodeNames: string[];
  onUpdate: (updater: (n: NodeData) => NodeData) => void;
}) {
  const [newEdgeName, setNewEdgeName] = useState('');
  const edges = node.edges ?? {};
  const edgeNames = Object.keys(edges);

  const addEdge = () => {
    const name = newEdgeName.trim();
    if (!name || edges[name]) return;
    onUpdate((n) => ({
      ...n,
      edges: {
        ...(n.edges ?? {}),
        [name]: { node: '', description: '', join_type: 'JOIN', join_steps: [{ table: '', alias_key: '', condition: '' }] },
      },
    }));
    setNewEdgeName('');
  };

  const updateEdge = (ename: string, updater: (e: EdgeData) => EdgeData) => {
    onUpdate((n) => {
      const existing = (n.edges ?? {})[ename];
      if (!existing) return n;
      const updated = { ...(n.edges ?? {}) };
      updated[ename] = updater(existing);
      return { ...n, edges: updated };
    });
  };

  const removeEdge = (ename: string) => {
    if (!window.confirm(`Delete edge "${ename}"?`)) return;
    onUpdate((n) => {
      const updated = { ...(n.edges ?? {}) };
      delete updated[ename];
      return { ...n, edges: updated };
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <InlineInput
          value={newEdgeName}
          onChange={setNewEdgeName}
          placeholder="New edge name"
          mono
          style={{ maxWidth: 240 }}
        />
        <button
          type="button"
          onClick={addEdge}
          disabled={!newEdgeName.trim()}
          className="v2-btn v2-btn-primary v2-btn-sm"
        >
          + Add edge
        </button>
      </div>

      {edgeNames.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13 }}>
          No edges defined yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {edgeNames.map((ename) => {
            const edge = edges[ename];
            if (!edge) return null;
            return (
              <div
                key={ename}
                className="v2-card"
                style={{ padding: 14 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--v2-text-primary)' }}>
                    {ename}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeEdge(ename)}
                    className="v2-icon-btn"
                    style={{ width: 24, height: 24, color: 'var(--v2-red-500)' }}
                    title="Delete edge"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Target node</label>
                    <select
                      className="v2-select"
                      value={edge.node}
                      onChange={(e) => updateEdge(ename, (ed) => ({ ...ed, node: e.target.value }))}
                      style={{ fontSize: 12 }}
                    >
                      <option value="">Select target...</option>
                      {nodeNames.map((n) => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Join type</label>
                    <select
                      className="v2-select"
                      value={edge.join_type ?? 'JOIN'}
                      onChange={(e) => updateEdge(ename, (ed) => ({ ...ed, join_type: e.target.value }))}
                      style={{ fontSize: 12 }}
                    >
                      {JOIN_TYPES.map((jt) => (
                        <option key={jt} value={jt}>{jt}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div style={{ marginTop: 10 }}>
                  <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Description</label>
                  <InlineInput
                    value={edge.description}
                    onChange={(v) => updateEdge(ename, (ed) => ({ ...ed, description: v }))}
                    placeholder="Edge description"
                    style={{ fontSize: 12 }}
                  />
                </div>

                <div style={{ marginTop: 10 }}>
                  <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Join condition</label>
                  <InlineInput
                    value={(edge.join_steps ?? []).map((s) => s.condition).join(' AND ')}
                    onChange={(v) => {
                      updateEdge(ename, (ed) => ({
                        ...ed,
                        join_steps: [{ table: ed.node || '', alias_key: ed.node || '', condition: v }],
                      }));
                    }}
                    placeholder="e.g. users.id = orders.user_id"
                    mono
                    style={{ fontSize: 12 }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Filters Tab ──────────────────────────────────────────────────────────────

function FiltersTab({
  node,
  onUpdate,
}: {
  node: NodeData;
  onUpdate: (updater: (n: NodeData) => NodeData) => void;
}) {
  const [newFilterName, setNewFilterName] = useState('');
  const filters = node.special_filters ?? {};
  const filterNames = Object.keys(filters);

  const addFilter = () => {
    const name = newFilterName.trim();
    if (!name || filters[name]) return;
    onUpdate((n) => ({
      ...n,
      special_filters: {
        ...(n.special_filters ?? {}),
        [name]: { description: '', sql: '', type: 'none' },
      },
    }));
    setNewFilterName('');
  };

  const updateFilter = (fname: string, updater: (f: SpecialFilterData) => SpecialFilterData) => {
    onUpdate((n) => {
      const updated = { ...(n.special_filters ?? {}) };
      const existing = updated[fname];
      if (!existing) return n;
      updated[fname] = updater(existing);
      return { ...n, special_filters: updated };
    });
  };

  const removeFilter = (fname: string) => {
    if (!window.confirm(`Delete filter "${fname}"?`)) return;
    onUpdate((n) => {
      const updated = { ...(n.special_filters ?? {}) };
      delete updated[fname];
      return { ...n, special_filters: updated };
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <InlineInput
          value={newFilterName}
          onChange={setNewFilterName}
          placeholder="New filter name"
          mono
          style={{ maxWidth: 240 }}
        />
        <button
          type="button"
          onClick={addFilter}
          disabled={!newFilterName.trim()}
          className="v2-btn v2-btn-primary v2-btn-sm"
        >
          + Add filter
        </button>
      </div>

      {filterNames.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13 }}>
          No special filters defined yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filterNames.map((fname) => {
            const f = filters[fname];
            if (!f) return null;
            return (
              <div key={fname} className="v2-card" style={{ padding: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--v2-text-primary)' }}>
                    {fname}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFilter(fname)}
                    className="v2-icon-btn"
                    style={{ width: 24, height: 24, color: 'var(--v2-red-500)' }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Description</label>
                    <InlineInput
                      value={f.description}
                      onChange={(v) => updateFilter(fname, (fl) => ({ ...fl, description: v }))}
                      placeholder="What this filter does"
                      style={{ fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>SQL expression</label>
                    <InlineInput
                      value={f.sql}
                      onChange={(v) => updateFilter(fname, (fl) => ({ ...fl, sql: v }))}
                      placeholder="e.g. created_at >= NOW() - INTERVAL '7 days'"
                      mono
                      style={{ fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Parameter type</label>
                    <select
                      className="v2-select"
                      value={f.type ?? 'none'}
                      onChange={(e) => updateFilter(fname, (fl) => ({ ...fl, type: e.target.value }))}
                      style={{ fontSize: 12, maxWidth: 160 }}
                    >
                      <option value="none">None</option>
                      <option value="integer">Integer</option>
                    </select>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Access Tab ────────────────────────────────────────────────────────────────

function AccessTab({
  node,
  onUpdate,
}: {
  node: NodeData;
  roleNames: string[];
  onUpdate: (updater: (n: NodeData) => NodeData) => void;
}) {
  const policies = node.row_policies ?? [];

  const addPolicy = () => {
    onUpdate((n) => ({
      ...n,
      row_policies: [
        ...(n.row_policies ?? []),
        { condition: '', roles: [], except_roles: [] },
      ],
    }));
  };

  const updatePolicy = (idx: number, updater: (p: RowPolicyData) => RowPolicyData) => {
    onUpdate((n) => {
      const updated = [...(n.row_policies ?? [])];
      const existing = updated[idx];
      if (!existing) return n;
      updated[idx] = updater(existing);
      return { ...n, row_policies: updated };
    });
  };

  const removePolicy = (idx: number) => {
    onUpdate((n) => {
      const updated = [...(n.row_policies ?? [])];
      updated.splice(idx, 1);
      return { ...n, row_policies: updated };
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Node-level visible_to */}
      <div style={{ maxWidth: 500 }}>
        <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>
          Visible to roles
        </label>
        <InlineInput
          value={(node.visible_to ?? []).join(', ')}
          onChange={(v) => {
            const roles = v.split(',').map((s) => s.trim()).filter(Boolean);
            onUpdate((n) => ({ ...n, visible_to: roles.length > 0 ? roles : undefined }));
          }}
          placeholder="All roles (leave blank for no restriction)"
        />
        <p style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 4 }}>
          Comma-separated role names. Leave empty to allow all roles.
        </p>
      </div>

      {/* Row policies */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span className="v2-heading-sm">Row policies</span>
          <button type="button" onClick={addPolicy} className="v2-btn v2-btn-primary v2-btn-sm">
            + Add policy
          </button>
        </div>

        {policies.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13, borderRadius: 'var(--v2-radius-md)', border: '1px dashed var(--v2-border)' }}>
            No row policies. All rows are visible to all allowed roles.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {policies.map((policy, idx) => (
              <div key={idx} className="v2-card" style={{ padding: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <span className="v2-label">Policy {idx + 1}</span>
                  <button
                    type="button"
                    onClick={() => removePolicy(idx)}
                    className="v2-icon-btn"
                    style={{ width: 24, height: 24, color: 'var(--v2-red-500)' }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>SQL condition</label>
                    <InlineInput
                      value={policy.condition}
                      onChange={(v) => updatePolicy(idx, (p) => ({ ...p, condition: v }))}
                      placeholder="e.g. department = :user_department"
                      mono
                      style={{ fontSize: 12 }}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Applies to roles</label>
                      <InlineInput
                        value={policy.roles.join(', ')}
                        onChange={(v) => {
                          const roles = v.split(',').map((s) => s.trim()).filter(Boolean);
                          updatePolicy(idx, (p) => ({ ...p, roles }));
                        }}
                        placeholder="e.g. analyst, viewer"
                        style={{ fontSize: 12 }}
                      />
                    </div>
                    <div>
                      <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Except roles</label>
                      <InlineInput
                        value={(policy.except_roles ?? []).join(', ')}
                        onChange={(v) => {
                          const roles = v.split(',').map((s) => s.trim()).filter(Boolean);
                          updatePolicy(idx, (p) => ({ ...p, except_roles: roles.length > 0 ? roles : undefined }));
                        }}
                        placeholder="e.g. admin"
                        style={{ fontSize: 12 }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-field access */}
      <div>
        <span className="v2-heading-sm" style={{ display: 'block', marginBottom: 10 }}>Field-level access</span>
        {Object.keys(node.fields ?? {}).length === 0 ? (
          <p className="v2-caption">No fields to configure.</p>
        ) : (
          <div className="v2-card" style={{ overflow: 'auto' }}>
            <table className="v2-table" style={{ minWidth: 500 }}>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Visible to</th>
                  <th style={{ width: 60, textAlign: 'center' }}>PII</th>
                  <th style={{ width: 140 }}>Mask with</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(node.fields ?? {}).map((fname) => {
                  const f = node.fields[fname];
                  if (!f) return null;
                  return (
                    <tr key={fname}>
                      <td>
                        <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12 }}>{fname}</span>
                      </td>
                      <td>
                        <InlineInput
                          value={(f.visible_to ?? []).join(', ')}
                          onChange={(v) => {
                            const roles = v.split(',').map((s) => s.trim()).filter(Boolean);
                            onUpdate((n) => {
                              const existing = n.fields[fname];
                              if (!existing) return n;
                              const updated = { ...n.fields };
                              updated[fname] = { ...existing, visible_to: roles.length > 0 ? roles : undefined };
                              return { ...n, fields: updated };
                            });
                          }}
                          placeholder="All"
                          style={{ fontSize: 12, padding: '2px 6px' }}
                        />
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={f.pii ?? false}
                          onChange={(e) => {
                            onUpdate((n) => {
                              const existing = n.fields[fname];
                              if (!existing) return n;
                              const updated = { ...n.fields };
                              updated[fname] = { ...existing, pii: e.target.checked || undefined };
                              return { ...n, fields: updated };
                            });
                          }}
                          style={{ accentColor: 'var(--v2-accent)' }}
                        />
                      </td>
                      <td>
                        <InlineInput
                          value={f.mask_with ?? ''}
                          onChange={(v) => {
                            onUpdate((n) => {
                              const existing = n.fields[fname];
                              if (!existing) return n;
                              const updated = { ...n.fields };
                              updated[fname] = { ...existing, mask_with: v || undefined };
                              return { ...n, fields: updated };
                            });
                          }}
                          placeholder="e.g. ***"
                          mono
                          style={{ fontSize: 12, padding: '2px 6px' }}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Roles editor ─────────────────────────────────────────────────────────────

function RolesEditor({
  roles,
  onUpdate,
}: {
  roles: Record<string, RoleDefData>;
  onUpdate: (roles: Record<string, RoleDefData>) => void;
}) {
  const [newRoleName, setNewRoleName] = useState('');
  const roleNames = Object.keys(roles);

  const addRole = () => {
    const name = newRoleName.trim();
    if (!name || roles[name]) return;
    onUpdate({ ...roles, [name]: { description: '' } });
    setNewRoleName('');
  };

  const removeRole = (name: string) => {
    if (!window.confirm(`Delete role "${name}"?`)) return;
    const updated = { ...roles };
    delete updated[name];
    onUpdate(updated);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 600 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <InlineInput
          value={newRoleName}
          onChange={setNewRoleName}
          placeholder="New role name"
          style={{ maxWidth: 240 }}
        />
        <button
          type="button"
          onClick={addRole}
          disabled={!newRoleName.trim()}
          className="v2-btn v2-btn-primary v2-btn-sm"
        >
          + Add role
        </button>
      </div>

      {roleNames.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13 }}>
          No roles defined yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {roleNames.map((rname) => (
            <div
              key={rname}
              className="v2-card"
              style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}
            >
              <span style={{ fontWeight: 500, fontSize: 13, minWidth: 100, color: 'var(--v2-text-primary)' }}>
                {rname}
              </span>
              <InlineInput
                value={roles[rname]?.description ?? ''}
                onChange={(v) => {
                  const updated = { ...roles };
                  updated[rname] = { description: v };
                  onUpdate(updated);
                }}
                placeholder="Role description"
                style={{ fontSize: 12 }}
              />
              <button
                type="button"
                onClick={() => removeRole(rname)}
                className="v2-icon-btn"
                style={{ width: 24, height: 24, color: 'var(--v2-red-500)', flexShrink: 0 }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Access Functions editor ──────────────────────────────────────────────────

function AccessFunctionsEditor({
  funcs,
  onUpdate,
}: {
  funcs: Record<string, AccessFunctionData>;
  onUpdate: (funcs: Record<string, AccessFunctionData>) => void;
}) {
  const [newFuncName, setNewFuncName] = useState('');
  const funcNames = Object.keys(funcs);

  const addFunc = () => {
    const name = newFuncName.trim();
    if (!name || funcs[name]) return;
    onUpdate({ ...funcs, [name]: { description: '', sql: '' } });
    setNewFuncName('');
  };

  const removeFunc = (name: string) => {
    if (!window.confirm(`Delete function "${name}"?`)) return;
    const updated = { ...funcs };
    delete updated[name];
    onUpdate(updated);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <InlineInput
          value={newFuncName}
          onChange={setNewFuncName}
          placeholder="New function name"
          mono
          style={{ maxWidth: 240 }}
        />
        <button
          type="button"
          onClick={addFunc}
          disabled={!newFuncName.trim()}
          className="v2-btn v2-btn-primary v2-btn-sm"
        >
          + Add function
        </button>
      </div>

      {funcNames.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13 }}>
          No access functions defined yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {funcNames.map((fname) => {
            const fn = funcs[fname];
            if (!fn) return null;
            return (
              <div key={fname} className="v2-card" style={{ padding: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--v2-text-primary)' }}>
                    {fname}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFunc(fname)}
                    className="v2-icon-btn"
                    style={{ width: 24, height: 24, color: 'var(--v2-red-500)' }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>Description</label>
                    <InlineInput
                      value={fn.description}
                      onChange={(v) => {
                        const updated = { ...funcs };
                        updated[fname] = { description: v, sql: fn.sql, requires: fn.requires };
                        onUpdate(updated);
                      }}
                      placeholder="What this function does"
                      style={{ fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label className="v2-label" style={{ display: 'block', marginBottom: 4, fontSize: 11 }}>SQL</label>
                    <InlineInput
                      value={fn.sql}
                      onChange={(v) => {
                        const updated = { ...funcs };
                        updated[fname] = { description: fn.description, sql: v, requires: fn.requires };
                        onUpdate(updated);
                      }}
                      placeholder="SQL function body"
                      mono
                      multiline
                      style={{ fontSize: 12 }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main SchemaDetailPage ────────────────────────────────────────────────────

export default function SchemaDetailPage({ domainName, schema, connectors, onToast, onOntologyChanged }: Props) {
  const [ontology, setOntology] = useState<OntologyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [topTab, setTopTab] = useState<TopTab>('nodes');
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [nodeTab, setNodeTab] = useState<NodeTab>('general');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchOntology = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/ontology?domain=${encodeURIComponent(domainName)}`);
      if (res.ok) {
        const data = await res.json();
        setOntology(data.ontology ?? data);
      } else {
        onToast({ message: 'Failed to load ontology', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [domainName, onToast]);

  useEffect(() => { fetchOntology(); }, [fetchOntology]);

  const stripUIFields = (ont: OntologyData): OntologyData => {
    const cleaned = JSON.parse(JSON.stringify(ont));
    for (const nodeName of Object.keys(cleaned.nodes ?? {})) {
      const node = cleaned.nodes[nodeName];
      if (node.row_policies) {
        for (const policy of node.row_policies) {
          delete policy.mode;
          delete policy.function_name;
          delete policy.function_field;
        }
      }
    }
    return cleaned;
  };

  const handleSave = useCallback(async () => {
    if (!ontology) return;
    setSaving(true);
    try {
      const cleaned = stripUIFields(ontology);
      const res = await fetch('/api/admin/ontology', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cleaned),
      });
      if (res.ok) {
        setDirty(false);
        onToast({ message: 'Ontology saved', type: 'success' });
        onOntologyChanged();
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Save failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [ontology, onToast, onOntologyChanged]);

  const updateNode = useCallback((nodeName: string, updater: (n: NodeData) => NodeData) => {
    setOntology((prev) => {
      if (!prev) return prev;
      const updated = { ...prev.nodes };
      const existing = updated[nodeName];
      if (!existing) return prev;
      updated[nodeName] = updater({ ...existing });
      return { ...prev, nodes: updated };
    });
    setDirty(true);
  }, []);

  const updateRoles = useCallback((roles: Record<string, RoleDefData>) => {
    setOntology((prev) => {
      if (!prev) return prev;
      return { ...prev, roles };
    });
    setDirty(true);
  }, []);

  const updateAccessFunctions = useCallback((funcs: Record<string, AccessFunctionData>) => {
    setOntology((prev) => {
      if (!prev) return prev;
      return { ...prev, access_functions: funcs };
    });
    setDirty(true);
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ textAlign: 'center' }}>
          <div
            style={{
              width: 20,
              height: 20,
              margin: '0 auto 8px',
              borderRadius: '50%',
              border: '2px solid var(--v2-border)',
              borderTopColor: 'var(--v2-accent)',
              animation: 'v2-spin 0.8s linear infinite',
            }}
          />
          <span className="v2-caption">Loading ontology...</span>
        </div>
      </div>
    );
  }

  if (!ontology) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <p className="v2-body-sm" style={{ color: 'var(--v2-red-500)' }}>Failed to load ontology data.</p>
      </div>
    );
  }

  const nodes = ontology.nodes ?? {};
  const nodeNames = Object.keys(nodes);
  const roles = ontology.roles ?? {};
  const accessFuncs = ontology.access_functions ?? {};
  const connectorNames = connectors.map((c) => c.name);

  // ── Node detail view ───────────────────────────────────────────────────────
  if (selectedNode && nodes[selectedNode]) {
    const node = nodes[selectedNode];
    const nodeTabs: { key: NodeTab; label: string; count?: number }[] = [
      { key: 'general', label: 'General' },
      { key: 'fields', label: 'Fields', count: countFields(node) },
      { key: 'edges', label: 'Edges', count: countEdges(node) },
      { key: 'filters', label: 'Filters', count: countFilters(node) },
      { key: 'access', label: 'Access' },
    ];

    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Node header */}
        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                type="button"
                onClick={() => { setSelectedNode(null); setNodeTab('general'); }}
                className="v2-icon-btn"
                style={{ width: 28, height: 28 }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
              <span className="v2-heading-md" style={{ fontFamily: 'var(--v2-font-mono)' }}>
                {selectedNode}
              </span>
              {node.table && node.table !== selectedNode && (
                <span className="v2-badge v2-badge-gray">{node.table}</span>
              )}
            </div>
            {dirty && (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="v2-btn v2-btn-primary v2-btn-sm"
              >
                {saving ? 'Saving...' : 'Save changes'}
              </button>
            )}
          </div>
        </div>

        {/* Node tabs */}
        <div style={{ padding: '0 20px', flexShrink: 0 }}>
          <TabBar tabs={nodeTabs} active={nodeTab} onChange={setNodeTab} />
        </div>

        {/* Node tab content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
          {nodeTab === 'general' && (
            <GeneralTab
              node={node}
              connectorNames={connectorNames}
              onUpdate={(updater) => updateNode(selectedNode, updater)}
            />
          )}
          {nodeTab === 'fields' && (
            <FieldsTab
              node={node}
              onUpdate={(updater) => updateNode(selectedNode, updater)}
            />
          )}
          {nodeTab === 'edges' && (
            <EdgesTab
              node={node}
              nodeNames={nodeNames}
              onUpdate={(updater) => updateNode(selectedNode, updater)}
            />
          )}
          {nodeTab === 'filters' && (
            <FiltersTab
              node={node}
              onUpdate={(updater) => updateNode(selectedNode, updater)}
            />
          )}
          {nodeTab === 'access' && (
            <AccessTab
              node={node}
              roleNames={Object.keys(roles)}
              onUpdate={(updater) => updateNode(selectedNode, updater)}
            />
          )}
        </div>
      </div>
    );
  }

  // ── Top-level schema view ──────────────────────────────────────────────────

  const topTabs: { key: TopTab; label: string; count?: number }[] = [
    { key: 'nodes', label: 'Nodes', count: nodeNames.length },
    { key: 'roles', label: 'Roles', count: Object.keys(roles).length },
    { key: 'access', label: 'Access Functions', count: Object.keys(accessFuncs).length },
  ];

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '12px 20px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="v2-heading-md">{schema.name}</span>
            {schema.connector_name && (
              <span className="v2-badge v2-badge-gray">{schema.connector_name}</span>
            )}
            <span className="v2-badge v2-badge-purple">{nodeNames.length} nodes</span>
          </div>
          {dirty && (
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="v2-btn v2-btn-primary v2-btn-sm"
            >
              {saving ? 'Saving...' : 'Save changes'}
            </button>
          )}
        </div>
      </div>

      {/* Top tabs */}
      <div style={{ padding: '0 20px', flexShrink: 0 }}>
        <TabBar tabs={topTabs} active={topTab} onChange={setTopTab} />
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {topTab === 'nodes' && (
          nodeNames.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--v2-text-tertiary)', fontSize: 13 }}>
              No nodes in this schema.
            </div>
          ) : (
            <div className="v2-card" style={{ overflow: 'auto' }}>
              <table className="v2-table">
                <thead>
                  <tr>
                    <th>Node</th>
                    <th>Table</th>
                    <th>Description</th>
                    <th style={{ width: 80, textAlign: 'center' }}>Fields</th>
                    <th style={{ width: 80, textAlign: 'center' }}>Edges</th>
                    <th style={{ width: 80, textAlign: 'center' }}>Filters</th>
                  </tr>
                </thead>
                <tbody>
                  {nodeNames.map((nname) => {
                    const n = nodes[nname];
                    if (!n) return null;
                    return (
                      <tr
                        key={nname}
                        style={{ cursor: 'pointer' }}
                        onClick={() => setSelectedNode(nname)}
                      >
                        <td>
                          <span style={{ fontWeight: 500, color: 'var(--v2-text-primary)' }}>{nname}</span>
                        </td>
                        <td>
                          <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-secondary)' }}>
                            {n.table ?? nname}
                          </span>
                        </td>
                        <td>
                          <span className="v2-body-sm" style={{
                            display: '-webkit-box',
                            WebkitLineClamp: 1,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                            maxWidth: 300,
                          }}>
                            {n.description || '—'}
                          </span>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span className="v2-badge v2-badge-blue">{countFields(n)}</span>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          {countEdges(n) > 0 ? (
                            <span className="v2-badge v2-badge-teal">{countEdges(n)}</span>
                          ) : (
                            <span className="v2-caption">—</span>
                          )}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          {countFilters(n) > 0 ? (
                            <span className="v2-badge v2-badge-amber">{countFilters(n)}</span>
                          ) : (
                            <span className="v2-caption">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}

        {topTab === 'roles' && (
          <RolesEditor roles={roles} onUpdate={updateRoles} />
        )}

        {topTab === 'access' && (
          <AccessFunctionsEditor funcs={accessFuncs} onUpdate={updateAccessFunctions} />
        )}
      </div>
    </div>
  );
}
