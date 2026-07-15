/**
 * Schema detail view — rich editor for nodes in a schema's ontology.
 * Split layout: node list (left) + NodeEditor (right) with save functionality.
 */
import { useState, useEffect, useCallback } from 'react';
import { SectionHeader, inputStyle } from './shared';
import NodeEditor from './NodeEditor';
import RolesEditor from './RolesEditor';
import PolicyFunctionsPanel from './PolicyFunctionsPanel';
import type {
  OntologyData,
  NodeData,
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

interface Props {
  domainName: string;
  schema: SchemaInfo;
  connectors: ConnectorInfo[];
  onBack: () => void;
  onRegenerate: () => void;
  regenerating: boolean;
  onToast: (t: { message: string; type: 'success' | 'error' }) => void;
  onOntologyChanged?: () => void;
}

// ── Deep clone helper ──────────────────────────────────────────────────────

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}

// ── Row policy transform: strip UI-only fields before saving ──────────────

function stripRowPolicyUIFields(ontology: OntologyData): OntologyData {
  const cleaned = deepClone(ontology);
  for (const node of Object.values(cleaned.nodes)) {
    if (node.row_policies) {
      node.row_policies = node.row_policies.map((p) => {
        const { mode, function_name, function_field, ...rest } = p;
        void mode; void function_name; void function_field;
        return rest;
      });
    }
  }
  return cleaned;
}

// ── Main component ──────────────────────────────────────────────────────────

export default function SchemaDetailView({
  domainName, schema: _schema, connectors, onBack,
  onRegenerate: _onRegenerate, regenerating: _regeneratingProp, onToast, onOntologyChanged,
}: Props) {
  void _onRegenerate; void _regeneratingProp;
  const [ontology, setOntology] = useState<OntologyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [viewTab, setViewTab] = useState<'nodes' | 'roles' | 'access'>('nodes');

  const fetchOntology = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/ontology?domain=${encodeURIComponent(domainName)}`);
      if (res.ok) {
        const data = await res.json();
        setOntology(data.ontology ?? null);
        setDirty(false);
      } else {
        setError('Failed to load ontology');
      }
    } catch (err) {
      setError(`Error: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [domainName]);

  useEffect(() => { fetchOntology(); }, [fetchOntology]);

  // Auto-select first node
  useEffect(() => {
    if (ontology && !selectedNode) {
      const names = Object.keys(ontology.nodes);
      if (names.length > 0) setSelectedNode(names[0]!);
    }
  }, [ontology, selectedNode]);

  // ── Ontology mutation helpers ────────────────────────────────────────────

  const updateOntology = useCallback((updater: (draft: OntologyData) => void) => {
    setOntology((prev) => {
      if (!prev) return prev;
      const clone = deepClone(prev);
      updater(clone);
      return clone;
    });
    setDirty(true);
  }, []);

  const updateNode = useCallback((nodeName: string, updater: (draft: NodeData) => void) => {
    updateOntology((o) => {
      const node = o.nodes[nodeName];
      if (node) updater(node);
    });
  }, [updateOntology]);

  // ── Save ─────────────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!ontology) return;
    setSaving(true);
    try {
      const cleaned = stripRowPolicyUIFields(ontology);
      const res = await fetch('/api/admin/ontology', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cleaned),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: 'Ontology saved', type: 'success' });
        setDirty(false);
        onOntologyChanged?.();
      } else {
        const msg = body.details?.join('\n') || body.message || body.error || 'Save failed';
        onToast({ message: msg, type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [ontology, onToast, onOntologyChanged]);

  const nodeEntries = Object.entries(ontology?.nodes ?? {});
  const nodeNames = nodeEntries.map(([n]) => n);
  const roleNames = Object.keys(ontology?.roles ?? {});
  const accessFunctions: Record<string, AccessFunctionData> = ontology?.access_functions ?? {};
  const selectedNodeData = selectedNode ? ontology?.nodes[selectedNode] : null;
  const nodeToConnector: Record<string, number> = (ontology as any)?.node_to_connector ?? {};

  // Build connector ID → name lookup
  const connectorIdToName: Record<number, string> = {};
  for (const c of connectors) {
    if (c.id != null) connectorIdToName[c.id] = c.name;
  }

  // ── Regenerate selected schema (single node) from its connector ─────────

  const handleRegenerateSchema = useCallback(async () => {
    if (!selectedNode) return;
    const connectorId = nodeToConnector[selectedNode];
    if (connectorId == null) {
      onToast({ message: `No connector mapped for "${selectedNode}"`, type: 'error' });
      return;
    }
    const connectorName = connectorIdToName[connectorId];
    if (!connectorName) {
      onToast({ message: `Connector not found for "${selectedNode}"`, type: 'error' });
      return;
    }
    const tableName = selectedNodeData?.table || selectedNode;
    setRegenerating(true);
    try {
      const res = await fetch('/api/generate-ontology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connector_name: connectorName,
          domain: domainName,
          description: '',
          include_tables: [tableName],
          replace: true,
        }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: `Regenerated "${selectedNode}" from ${connectorName}`, type: 'success' });
        fetchOntology();
        onOntologyChanged?.();
      } else {
        onToast({ message: body.error || `Failed to regenerate ${selectedNode}`, type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setRegenerating(false);
    }
  }, [selectedNode, selectedNodeData, nodeToConnector, connectorIdToName, domainName, fetchOntology, onOntologyChanged, onToast]);
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <SectionHeader
        title={domainName}
        subtitle={`${nodeEntries.length} node(s)`}
      />

      {/* Top bar: back + actions */}
      <div className="shrink-0 border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center justify-between">
          <button type="button" onClick={onBack} className="text-xs" style={{ color: 'var(--accent)' }}>
            &larr; Back
          </button>
          <div className="flex items-center gap-3 text-[11px]">
            <span className="font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>{domainName}</span>
            <span style={{ color: 'var(--text-muted)' }}>
              {nodeEntries.length} nodes
            </span>
          </div>
          <div className="flex items-center gap-2">
            {viewTab === 'nodes' && (
              <>
                <button
                  type="button"
                  onClick={() => setShowAddModal(true)}
                  className="rounded border border-dashed px-2 py-1 text-[10px]"
                  style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}
                >
                  + Add Schema
                </button>
                <button
                  type="button"
                  onClick={handleRegenerateSchema}
                  disabled={regenerating || !selectedNode}
                  className="rounded border px-2 py-1 text-[10px] font-semibold disabled:opacity-50"
                  style={{ borderColor: 'var(--border)', color: 'var(--badge-green-text)' }}
                >
                  {regenerating ? 'Regenerating...' : 'Regenerate Schema'}
                </button>
              </>
            )}
            {dirty && (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="rounded px-3 py-1 text-[10px] font-semibold disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)', color: '#0f1117' }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* View tabs: Nodes | Roles | Access Functions */}
      <div className="flex shrink-0 border-b" style={{ borderColor: 'var(--border)' }}>
        {([
          { key: 'nodes' as const, label: 'Nodes', count: nodeEntries.length },
          { key: 'roles' as const, label: 'Roles', count: roleNames.length },
          { key: 'access' as const, label: 'Access Functions', count: Object.keys(accessFunctions).length },
        ]).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setViewTab(t.key)}
            className="relative px-4 py-2 text-[11px] font-semibold transition-colors"
            style={{ color: viewTab === t.key ? 'var(--accent)' : 'var(--text-secondary)' }}
          >
            {t.label} {t.count > 0 && <span className="opacity-60">({t.count})</span>}
            {viewTab === t.key && (
              <span className="absolute right-0 bottom-0 left-0 h-[2px]" style={{ backgroundColor: 'var(--accent)' }} />
            )}
          </button>
        ))}
      </div>

      {loading && <p className="p-4 text-xs" style={{ color: 'var(--text-secondary)' }}>Loading ontology...</p>}
      {error && <p className="p-4 text-xs" style={{ color: '#f87171' }}>{error}</p>}

      {ontology && !loading && viewTab === 'nodes' && (
        <div className="flex flex-1 overflow-hidden">
          {/* Node list sidebar */}
          <div className="flex w-[220px] shrink-0 flex-col border-r" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: 'var(--border)' }}>
              <span className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: 'var(--text-muted)' }}>
                Nodes
              </span>
              <span className="ml-2 rounded-full px-1.5 text-[10px]" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                {nodeEntries.length}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {nodeEntries.map(([name, node]) => (
                  <button
                    type="button"
                    key={name}
                    onClick={() => setSelectedNode(name)}
                    className={`flex w-full items-center border-b px-3 py-2.5 text-left transition-colors ${
                      selectedNode === name ? 'border-l-2' : ''
                    }`}
                    style={{
                      borderBottomColor: 'var(--border)',
                      borderLeftColor: selectedNode === name ? 'var(--accent)' : 'transparent',
                      backgroundColor: selectedNode === name ? 'var(--bg-input)' : 'transparent',
                    }}
                    onMouseEnter={(e) => { if (selectedNode !== name) e.currentTarget.style.backgroundColor = 'var(--bg-input)'; }}
                    onMouseLeave={(e) => { if (selectedNode !== name) e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="truncate font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{name}</span>
                      <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>
                        {Object.keys(node.fields).length}f
                        {node.edges ? ` · ${Object.keys(node.edges).length}e` : ''}
                        {node.visible_to?.length ? ` · ${node.visible_to.join(',')}` : ''}
                        {nodeToConnector[name] != null && connectorIdToName[nodeToConnector[name]!]
                          ? ` · ${connectorIdToName[nodeToConnector[name]!]}`
                          : ''}
                      </span>
                    </div>
                  </button>
              ))}
              {nodeEntries.length === 0 && (
                <div className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>
                  No nodes. Regenerate or add a schema.
                </div>
              )}
            </div>
          </div>

          {/* Node editor */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {selectedNode && selectedNodeData ? (
              <NodeEditor
                nodeName={selectedNode}
                node={selectedNodeData}
                nodeNames={nodeNames}
                allNodes={ontology?.nodes ?? {}}
                connectorNames={connectors.map((c) => c.name)}
                roleNames={roleNames}
                accessFunctions={accessFunctions}
                onUpdateNode={(updater) => updateNode(selectedNode, updater)}
                onUpdateOntology={updateOntology}
              />
            ) : (
              <div className="flex flex-1 items-center justify-center">
                <div className="text-center">
                  <div className="mb-2 text-2xl" style={{ color: 'var(--text-muted)' }}>&#x1F4DD;</div>
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Select a node to edit</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {ontology && !loading && viewTab === 'roles' && (
        <RolesEditor
          ontology={ontology}
          onUpdate={updateOntology}
          onToast={onToast}
        />
      )}

      {ontology && !loading && viewTab === 'access' && (
        <PolicyFunctionsPanel
          ontology={ontology}
          onUpdate={updateOntology}
        />
      )}

      {/* Add Schema modal */}
      {showAddModal && (
        <AddSchemaModal
          domainName={domainName}
          connectors={connectors}
          onToast={onToast}
          onGenerated={() => {
            setShowAddModal(false);
            fetchOntology();
            onOntologyChanged?.();
          }}
          onClose={() => setShowAddModal(false)}
        />
      )}
    </div>
  );
}

// ── Add Schema modal dialog ─────────────────────────────────────────────────

function AddSchemaModal({
  domainName, connectors, onToast, onGenerated, onClose,
}: {
  domainName: string;
  connectors: ConnectorInfo[];
  onToast: (t: { message: string; type: 'success' | 'error' }) => void;
  onGenerated: () => void;
  onClose: () => void;
}) {
  const [connector, setConnector] = useState('');
  const [schemaName, setSchemaName] = useState('');
  const [description, setDescription] = useState('');
  const [tables, setTables] = useState<{ name: string; column_count: number; row_count_estimate: number | null }[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [introspecting, setIntrospecting] = useState(false);
  const [generating, setGenerating] = useState(false);

  const handleIntrospect = useCallback(async () => {
    if (!connector) return;
    setIntrospecting(true);
    setTables([]);
    setSelected(new Set());
    try {
      const res = await fetch(`/api/connectors/${encodeURIComponent(connector)}/introspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema_name: 'public' }),
      });
      const body = await res.json();
      if (res.ok) {
        const t = body.tables ?? [];
        setTables(t);
        setSelected(new Set(t.map((x: { name: string }) => x.name)));
      } else {
        onToast({ message: body.error || 'Introspection failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setIntrospecting(false);
    }
  }, [connector, onToast]);

  const handleGenerate = useCallback(async () => {
    const name = schemaName.trim() || connector;
    if (!connector || !name) return;
    setGenerating(true);
    try {
      const includeTables = selected.size < tables.length ? Array.from(selected) : undefined;
      const res = await fetch('/api/generate-ontology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connector_name: connector,
          domain: domainName,
          description,
          include_tables: includeTables,
          output_schema_name: name,
          replace: false,
        }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: `Schema "${name}" generated (${body.node_count} nodes, ${body.total_fields} fields)`, type: 'success' });
        onGenerated();
      } else {
        onToast({ message: body.error || 'Generation failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setGenerating(false);
    }
  }, [connector, schemaName, domainName, description, selected, tables.length, onGenerated, onToast]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="rounded-lg border shadow-xl w-full max-w-lg max-h-[80vh] overflow-y-auto p-5 space-y-4"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="flex items-center justify-between">
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            Add Schema to "{domainName}"
          </span>
          <button type="button" onClick={onClose} className="text-lg leading-none" style={{ color: 'var(--text-secondary)' }}>&times;</button>
        </div>

        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Schema Name</label>
          <input
            value={schemaName}
            onChange={(e) => setSchemaName(e.target.value)}
            placeholder="e.g. products, inventory (defaults to connector name)"
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>

        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Description (optional)</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Analytics tables from warehouse"
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>

        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Connector</label>
          {connectors.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>No connectors available.</p>
          ) : (
            <select
              value={connector}
              onChange={(e) => { setConnector(e.target.value); setTables([]); setSelected(new Set()); }}
              className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
              style={inputStyle}
            >
              <option value="">Choose a connector...</option>
              {connectors.map((c) => (
                <option key={c.name} value={c.name}>{c.name} ({c.db_type})</option>
              ))}
            </select>
          )}
        </div>

        {connector && tables.length === 0 && (
          <button
            type="button"
            onClick={handleIntrospect}
            disabled={introspecting}
            className="rounded px-4 py-1.5 text-xs font-semibold"
            style={{ backgroundColor: 'var(--accent)', color: '#0f1117' }}
          >
            {introspecting ? 'Loading tables...' : 'Load Tables'}
          </button>
        )}

        {tables.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                Tables ({selected.size}/{tables.length})
              </label>
              <div className="flex gap-2">
                <button type="button" onClick={() => setSelected(new Set(tables.map((t) => t.name)))} className="text-[10px] underline" style={{ color: 'var(--accent)' }}>All</button>
                <button type="button" onClick={() => setSelected(new Set())} className="text-[10px] underline" style={{ color: 'var(--text-secondary)' }}>None</button>
              </div>
            </div>
            <div className="rounded border max-h-[200px] overflow-y-auto" style={{ borderColor: 'var(--border)' }}>
              {tables.map((t) => (
                <label key={t.name} className="flex items-center gap-2 border-b px-3 py-1.5 cursor-pointer hover:bg-[var(--bg-elevated)]" style={{ borderColor: 'var(--border)' }}>
                  <input
                    type="checkbox"
                    checked={selected.has(t.name)}
                    onChange={(e) => {
                      const next = new Set(selected);
                      if (e.target.checked) next.add(t.name); else next.delete(t.name);
                      setSelected(next);
                    }}
                  />
                  <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t.name}</span>
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    ({t.column_count} cols{t.row_count_estimate ? `, ~${t.row_count_estimate} rows` : ''})
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
          <button
            type="button"
            onClick={onClose}
            className="rounded border px-4 py-1.5 text-xs"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            Cancel
          </button>
          {tables.length > 0 && selected.size > 0 && (
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              className="rounded px-4 py-1.5 text-xs font-semibold bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577] disabled:opacity-50"
            >
              {generating ? 'Generating...' : `Generate (${selected.size} tables)`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
