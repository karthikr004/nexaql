import { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  OntologyData,
  NodeData,
  FieldData,
  EdgeData,
  JoinStepData,
  SpecialFilterData,
  RowPolicyData,
} from '../types';

// ── Props ────────────────────────────────────────────────────────────────────

interface OntologyAdminProps {
  onOntologyChanged?: () => void;
}

// ── Tabs ─────────────────────────────────────────────────────────────────────

type EditorTab = 'general' | 'fields' | 'edges' | 'filters' | 'access';

const FIELD_TYPES = ['string', 'integer', 'numeric', 'boolean', 'date', 'enum'];
const JOIN_TYPES = ['JOIN', 'LEFT', 'LEFT JOIN'];

// ── Helpers ──────────────────────────────────────────────────────────────────

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}

/** Safe record lookup — returns the value or throws (use where key is known to exist). */
function get<V>(rec: Record<string, V>, key: string): V {
  const v = rec[key];
  if (v === undefined) throw new Error(`Missing key: ${key}`);
  return v;
}

function makeEmptyNode(): NodeData {
  return {
    table: '',
    primary_key: 'id',
    description: '',
    fields: {},
  };
}

function makeEmptyField(): FieldData {
  return { type: 'string', description: '', filterable: false };
}

function makeEmptyEdge(): EdgeData {
  return { node: '', description: '', join_steps: [] };
}

function makeEmptyJoinStep(): JoinStepData {
  return { table: '', alias_key: '', condition: '' };
}

function makeEmptyFilter(): SpecialFilterData {
  return { description: '', sql: '' };
}

function makeEmptyRowPolicy(): RowPolicyData {
  return { condition: '', roles: [] };
}

// ── Toast ────────────────────────────────────────────────────────────────────

function Toast({ message, type, onDismiss }: { message: string; type: 'success' | 'error'; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 3500);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div
      className={`fixed top-4 right-4 z-50 rounded border px-4 py-2 text-sm shadow-lg ${
        type === 'success'
          ? 'border-[#3dd68c]/40 bg-[#1a2f25] text-[#3dd68c]'
          : 'border-red-500/40 bg-[#2f1a1a] text-red-400'
      }`}
    >
      {message}
    </div>
  );
}

// ── Add Node Dialog ──────────────────────────────────────────────────────────

function AddNodeDialog({
  onAdd,
  onCancel,
  existingNames,
}: {
  onAdd: (name: string, data: NodeData) => void;
  onCancel: () => void;
  existingNames: string[];
}) {
  const [name, setName] = useState('');
  const [table, setTable] = useState('');
  const [pk, setPk] = useState('id');
  const [desc, setDesc] = useState('');
  const nameError = existingNames.includes(name) ? 'Name already exists' : name && !/^[a-z_]\w*$/i.test(name) ? 'Invalid identifier' : '';

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
      <div className="w-[420px] rounded-lg border border-[#252d3d] bg-[#131920] p-5">
        <h3 className="mb-4 font-semibold text-sm text-slate-200">Add New Node</h3>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
              placeholder="e.g. customer"
              autoFocus
            />
            {nameError && <span className="text-[10px] text-red-400">{nameError}</span>}
          </div>
          <div>
            <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Table</label>
            <input
              value={table}
              onChange={(e) => setTable(e.target.value)}
              className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
              placeholder="e.g. customers"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Primary Key</label>
            <input
              value={pk}
              onChange={(e) => setPk(e.target.value)}
              className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Description</label>
            <input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
            />
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-[#252d3d] px-3 py-1.5 text-[11px] text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name || !!nameError}
            onClick={() => onAdd(name, { ...makeEmptyNode(), table: table || name, primary_key: pk, description: desc })}
            className="rounded bg-[#4f8ef7] px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-40"
          >
            Add Node
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Confirm Dialog ───────────────────────────────────────────────────────────

function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
      <div className="w-[340px] rounded-lg border border-[#252d3d] bg-[#131920] p-5">
        <p className="mb-4 text-sm text-slate-300">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-[#252d3d] px-3 py-1.5 text-[11px] text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded bg-red-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-red-500"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function OntologyAdmin({ onOntologyChanged }: OntologyAdminProps) {
  const [ontology, setOntology] = useState<OntologyData | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState<string>('');
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<EditorTab>('general');
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddNode, setShowAddNode] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load ontology
  useEffect(() => {
    fetch('/api/admin/ontology')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: OntologyData) => {
        setOntology(data);
        setSavedSnapshot(JSON.stringify(data));
      })
      .catch((err) => setLoadError(String(err)));
  }, []);

  const isDirty = useMemo(() => {
    if (!ontology) return false;
    return JSON.stringify(ontology) !== savedSnapshot;
  }, [ontology, savedSnapshot]);

  const nodeNames = useMemo(() => {
    if (!ontology) return [];
    return Object.keys(ontology.nodes);
  }, [ontology]);

  const filteredNodes = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return nodeNames.filter((n) => {
      if (!q) return true;
      const nd = ontology?.nodes[n];
      if (!nd) return false;
      return n.toLowerCase().includes(q) || (nd.table ?? '').toLowerCase().includes(q);
    });
  }, [nodeNames, searchQuery, ontology]);

  // ── Mutation helpers ───────────────────────────────────────────────────────

  const updateOntology = useCallback((updater: (draft: OntologyData) => void) => {
    setOntology((prev) => {
      if (!prev) return prev;
      const next = deepClone(prev);
      updater(next);
      return next;
    });
  }, []);

  const updateNode = useCallback(
    (updater: (draft: NodeData) => void) => {
      if (!selectedNode) return;
      updateOntology((o) => {
        const nd = o.nodes[selectedNode];
        if (nd) updater(nd);
      });
    },
    [selectedNode, updateOntology],
  );

  // ── Save ───────────────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!ontology || !isDirty) return;
    setSaving(true);
    try {
      const res = await fetch('/api/admin/ontology', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ontology),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      setSavedSnapshot(JSON.stringify(ontology));
      setToast({ message: 'Ontology saved successfully', type: 'success' });
      onOntologyChanged?.();
    } catch (err) {
      setToast({ message: `Save failed: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [ontology, isDirty, onOntologyChanged]);

  // ── Node CRUD ──────────────────────────────────────────────────────────────

  const handleAddNode = useCallback(
    (name: string, data: NodeData) => {
      updateOntology((o) => {
        o.nodes[name] = data;
      });
      setSelectedNode(name);
      setShowAddNode(false);
      setActiveTab('general');
    },
    [updateOntology],
  );

  const handleDeleteNode = useCallback(
    (name: string) => {
      updateOntology((o) => {
        delete o.nodes[name];
      });
      if (selectedNode === name) setSelectedNode(null);
      setConfirmDelete(null);
    },
    [selectedNode, updateOntology],
  );

  // ── Current node data ──────────────────────────────────────────────────────

  const node = selectedNode && ontology ? ontology.nodes[selectedNode] ?? null : null;

  // ── Loading / error states ─────────────────────────────────────────────────

  if (loadError) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-red-400">
        Failed to load ontology: {loadError}
      </div>
    );
  }

  if (!ontology) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-600">Loading ontology...</div>
    );
  }

  // ── Render helpers for each tab ────────────────────────────────────────────

  const renderGeneral = () => {
    if (!node || !selectedNode) return null;
    return (
      <div className="space-y-4 p-4">
        <div>
          <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Table</label>
          <input
            value={node.table ?? ''}
            onChange={(e) => updateNode((n) => { n.table = e.target.value; })}
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Primary Key</label>
          <input
            value={node.primary_key}
            onChange={(e) => updateNode((n) => { n.primary_key = e.target.value; })}
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Description</label>
          <textarea
            rows={3}
            value={node.description}
            onChange={(e) => updateNode((n) => { n.description = e.target.value; })}
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none resize-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Datasource (optional)</label>
          <input
            value={node.datasource ?? ''}
            onChange={(e) => updateNode((n) => { n.datasource = e.target.value || undefined; })}
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
          />
        </div>
      </div>
    );
  };

  const renderFields = () => {
    if (!node || !selectedNode) return null;
    const fieldEntries = Object.entries(node.fields);
    return (
      <div className="p-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#252d3d] text-[10px] text-slate-500 uppercase tracking-widest">
                <th className="py-2 pr-2 text-left">Name</th>
                <th className="py-2 pr-2 text-left">Type</th>
                <th className="py-2 pr-2 text-left">Description</th>
                <th className="py-2 pr-2 text-center">Filterable</th>
                <th className="w-8 py-2" />
              </tr>
            </thead>
            <tbody>
              {fieldEntries.map(([fname, fdata]) => (
                <tr key={fname} className="border-b border-[#252d3d]/50 hover:bg-[#161b27]">
                  <td className="py-1.5 pr-2">
                    <input
                      value={fname}
                      onChange={(e) => {
                        const newName = e.target.value;
                        if (newName === fname) return;
                        updateNode((n) => {
                          const val = get(n.fields, fname);
                          delete n.fields[fname];
                          n.fields[newName] = val;
                        });
                      }}
                      className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                    />
                  </td>
                  <td className="py-1.5 pr-2">
                    <select
                      value={fdata.type}
                      onChange={(e) => updateNode((n) => { get(n.fields, fname).type = e.target.value; })}
                      className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                    >
                      {FIELD_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-1.5 pr-2">
                    <input
                      value={fdata.description}
                      onChange={(e) => updateNode((n) => { get(n.fields, fname).description = e.target.value; })}
                      className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                    />
                  </td>
                  <td className="py-1.5 pr-2 text-center">
                    <input
                      type="checkbox"
                      checked={fdata.filterable ?? false}
                      onChange={(e) => updateNode((n) => { get(n.fields, fname).filterable = e.target.checked; })}
                      className="accent-[#4f8ef7]"
                    />
                  </td>
                  <td className="py-1.5 text-center">
                    <button
                      type="button"
                      onClick={() => updateNode((n) => { delete n.fields[fname]; })}
                      className="text-slate-600 hover:text-red-400"
                      title="Delete field"
                    >
                      x
                    </button>
                  </td>
                </tr>
              ))}
              {fieldEntries.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-xs text-slate-600">No fields defined</td>
                </tr>
              )}
            </tbody>
          </table>
          {/* Enum values row — show for enum fields */}
          {fieldEntries
            .filter(([, fd]) => fd.type === 'enum')
            .map(([fname, fdata]) => (
              <div key={`enum-${fname}`} className="mt-2 rounded border border-[#252d3d] bg-[#131920] p-2">
                <label className="text-[10px] text-slate-500 uppercase tracking-widest">
                  Enum values for <span className="font-mono text-slate-400">{fname}</span>
                </label>
                <input
                  value={(fdata.values ?? []).join(', ')}
                  onChange={(e) =>
                    updateNode((n) => {
                      get(n.fields, fname).values = e.target.value
                        .split(',')
                        .map((v) => v.trim())
                        .filter(Boolean);
                    })
                  }
                  placeholder="value1, value2, ..."
                  className="mt-1 w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                />
              </div>
            ))}
        </div>
        <button
          type="button"
          onClick={() => {
            const name = `field_${Object.keys(node.fields).length + 1}`;
            updateNode((n) => { n.fields[name] = makeEmptyField(); });
          }}
          className="mt-3 rounded border border-[#252d3d] px-3 py-1.5 text-[11px] text-slate-400 hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
        >
          + Add Field
        </button>
      </div>
    );
  };

  const renderEdges = () => {
    if (!node || !selectedNode) return null;
    const edges = node.edges ?? {};
    const edgeEntries = Object.entries(edges);
    return (
      <div className="space-y-3 p-4">
        {edgeEntries.map(([ename, edata]) => (
          <div key={ename} className="rounded-lg border border-[#252d3d] bg-[#131920] p-3">
            <div className="mb-2 flex items-center justify-between">
              <input
                value={ename}
                onChange={(e) => {
                  const newName = e.target.value;
                  if (newName === ename) return;
                  updateNode((n) => {
                    const ed = n.edges ?? {};
                    const val = get(ed, ename);
                    delete ed[ename];
                    ed[newName] = val;
                    n.edges = ed;
                  });
                }}
                className="rounded border border-[#252d3d] bg-[#161b27] px-2 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                placeholder="Edge name"
              />
              <button
                type="button"
                onClick={() => updateNode((n) => { if (n.edges) delete n.edges[ename]; })}
                className="text-slate-600 hover:text-red-400"
                title="Delete edge"
              >
                x
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Target Node</label>
                <select
                  value={edata.node}
                  onChange={(e) => updateNode((n) => { const ed = n.edges?.[ename]; if (ed) ed.node = e.target.value; })}
                  className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                >
                  <option value="">-- select --</option>
                  {nodeNames.map((nn) => (
                    <option key={nn} value={nn}>{nn}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Description</label>
                <input
                  value={edata.description}
                  onChange={(e) => updateNode((n) => { const ed = n.edges?.[ename]; if (ed) ed.description = e.target.value; })}
                  className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Join Type</label>
                <select
                  value={edata.join_type ?? 'JOIN'}
                  onChange={(e) => updateNode((n) => { const ed = n.edges?.[ename]; if (ed) ed.join_type = e.target.value; })}
                  className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                >
                  {JOIN_TYPES.map((jt) => (
                    <option key={jt} value={jt}>{jt}</option>
                  ))}
                </select>
              </div>
            </div>
            {/* Join Steps */}
            <div className="mt-2">
              <label className="mb-1 block text-[9px] text-slate-500 uppercase tracking-widest">Join Steps</label>
              {edata.join_steps.map((step, si) => (
                <div key={si} className="mb-1 grid grid-cols-[1fr_1fr_2fr_auto] gap-1.5">
                  <input
                    value={step.table}
                    onChange={(e) =>
                      updateNode((n) => {
                        const ed = n.edges?.[ename];
                        const s = ed?.join_steps[si]; if (s) s.table = e.target.value;
                      })
                    }
                    placeholder="table"
                    className="rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-[10px] text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                  />
                  <input
                    value={step.alias_key}
                    onChange={(e) =>
                      updateNode((n) => {
                        const ed = n.edges?.[ename];
                        const s = ed?.join_steps[si]; if (s) s.alias_key = e.target.value;
                      })
                    }
                    placeholder="alias_key"
                    className="rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-[10px] text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                  />
                  <input
                    value={step.condition}
                    onChange={(e) =>
                      updateNode((n) => {
                        const ed = n.edges?.[ename];
                        const s = ed?.join_steps[si]; if (s) s.condition = e.target.value;
                      })
                    }
                    placeholder="condition"
                    className="rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-[10px] text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      updateNode((n) => {
                        const ed = n.edges?.[ename];
                        if (ed) ed.join_steps.splice(si, 1);
                      })
                    }
                    className="text-slate-600 hover:text-red-400"
                  >
                    x
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  updateNode((n) => {
                    const ed = n.edges?.[ename];
                    if (ed) ed.join_steps.push(makeEmptyJoinStep());
                  })
                }
                className="mt-1 text-[10px] text-slate-500 hover:text-[#4f8ef7]"
              >
                + Add Join Step
              </button>
            </div>
          </div>
        ))}
        {edgeEntries.length === 0 && (
          <div className="py-6 text-center text-xs text-slate-600">No edges defined</div>
        )}
        <button
          type="button"
          onClick={() => {
            const name = `edge_${Object.keys(edges).length + 1}`;
            updateNode((n) => {
              if (!n.edges) n.edges = {};
              n.edges[name] = makeEmptyEdge();
            });
          }}
          className="rounded border border-[#252d3d] px-3 py-1.5 text-[11px] text-slate-400 hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
        >
          + Add Edge
        </button>
      </div>
    );
  };

  const renderFilters = () => {
    if (!node || !selectedNode) return null;
    const filters = node.special_filters ?? {};
    const filterEntries = Object.entries(filters);
    return (
      <div className="space-y-3 p-4">
        {filterEntries.map(([fname, fdata]) => (
          <div key={fname} className="rounded-lg border border-[#252d3d] bg-[#131920] p-3">
            <div className="mb-2 flex items-center justify-between">
              <input
                value={fname}
                onChange={(e) => {
                  const newName = e.target.value;
                  if (newName === fname) return;
                  updateNode((n) => {
                    const sf = n.special_filters ?? {};
                    const val = get(sf, fname);
                    delete sf[fname];
                    sf[newName] = val;
                    n.special_filters = sf;
                  });
                }}
                className="rounded border border-[#252d3d] bg-[#161b27] px-2 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                placeholder="Filter name"
              />
              <button
                type="button"
                onClick={() => updateNode((n) => { if (n.special_filters) delete n.special_filters[fname]; })}
                className="text-slate-600 hover:text-red-400"
              >
                x
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Description</label>
                <input
                  value={fdata.description}
                  onChange={(e) =>
                    updateNode((n) => {
                      const sf = n.special_filters?.[fname];
                      if (sf) sf.description = e.target.value;
                    })
                  }
                  className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">SQL Expression</label>
                <input
                  value={fdata.sql}
                  onChange={(e) =>
                    updateNode((n) => {
                      const sf = n.special_filters?.[fname];
                      if (sf) sf.sql = e.target.value;
                    })
                  }
                  className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Type (optional)</label>
                <select
                  value={fdata.type ?? ''}
                  onChange={(e) =>
                    updateNode((n) => {
                      const sf = n.special_filters?.[fname];
                      if (sf) sf.type = e.target.value || undefined;
                    })
                  }
                  className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                >
                  <option value="">none</option>
                  <option value="integer">integer</option>
                </select>
              </div>
            </div>
          </div>
        ))}
        {filterEntries.length === 0 && (
          <div className="py-6 text-center text-xs text-slate-600">No special filters defined</div>
        )}
        <button
          type="button"
          onClick={() => {
            const name = `filter_${Object.keys(filters).length + 1}`;
            updateNode((n) => {
              if (!n.special_filters) n.special_filters = {};
              n.special_filters[name] = makeEmptyFilter();
            });
          }}
          className="rounded border border-[#252d3d] px-3 py-1.5 text-[11px] text-slate-400 hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
        >
          + Add Filter
        </button>
      </div>
    );
  };

  const renderAccess = () => {
    if (!node || !selectedNode) return null;
    const policies = node.row_policies ?? [];
    const fieldEntries = Object.entries(node.fields);
    return (
      <div className="space-y-5 p-4">
        {/* Node-level visible_to */}
        <div>
          <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Node visible_to (comma-separated roles)</label>
          <input
            value={(node.visible_to ?? []).join(', ')}
            onChange={(e) =>
              updateNode((n) => {
                const val = e.target.value
                  .split(',')
                  .map((v) => v.trim())
                  .filter(Boolean);
                n.visible_to = val.length ? val : undefined;
              })
            }
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
            placeholder="e.g. analyst, admin"
          />
        </div>

        {/* Row policies */}
        <div>
          <h4 className="mb-2 text-[10px] text-slate-500 uppercase tracking-widest">Row Policies</h4>
          {policies.map((pol, pi) => (
            <div key={pi} className="mb-2 rounded-lg border border-[#252d3d] bg-[#131920] p-3">
              <div className="mb-2 flex items-start justify-between">
                <span className="text-[10px] text-slate-500">Policy {pi + 1}</span>
                <button
                  type="button"
                  onClick={() =>
                    updateNode((n) => {
                      if (n.row_policies) n.row_policies.splice(pi, 1);
                    })
                  }
                  className="text-slate-600 hover:text-red-400"
                >
                  x
                </button>
              </div>
              <div className="space-y-2">
                <div>
                  <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Condition</label>
                  <input
                    value={pol.condition}
                    onChange={(e) =>
                      updateNode((n) => {
                        const p = n.row_policies?.[pi];
                        if (p) p.condition = e.target.value;
                      })
                    }
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Roles (comma-separated)</label>
                  <input
                    value={pol.roles.join(', ')}
                    onChange={(e) =>
                      updateNode((n) => {
                        const p = n.row_policies?.[pi];
                        if (p)
                          p.roles = e.target.value
                            .split(',')
                            .map((v) => v.trim())
                            .filter(Boolean);
                      })
                    }
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Except Roles (comma-separated)</label>
                  <input
                    value={(pol.except_roles ?? []).join(', ')}
                    onChange={(e) =>
                      updateNode((n) => {
                        const p = n.row_policies?.[pi];
                        if (p) {
                          const val = e.target.value
                            .split(',')
                            .map((v) => v.trim())
                            .filter(Boolean);
                          p.except_roles = val.length ? val : undefined;
                        }
                      })
                    }
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                  />
                </div>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              updateNode((n) => {
                if (!n.row_policies) n.row_policies = [];
                n.row_policies.push(makeEmptyRowPolicy());
              })
            }
            className="rounded border border-[#252d3d] px-3 py-1.5 text-[11px] text-slate-400 hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
          >
            + Add Row Policy
          </button>
        </div>

        {/* Per-field access table */}
        <div>
          <h4 className="mb-2 text-[10px] text-slate-500 uppercase tracking-widest">Per-Field Access</h4>
          {fieldEntries.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#252d3d] text-[10px] text-slate-500 uppercase tracking-widest">
                    <th className="py-2 pr-2 text-left">Field</th>
                    <th className="py-2 pr-2 text-left">visible_to</th>
                    <th className="py-2 pr-2 text-center">PII</th>
                    <th className="py-2 pr-2 text-left">Mask Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {fieldEntries.map(([fname, fdata]) => (
                    <tr key={fname} className="border-b border-[#252d3d]/50 hover:bg-[#161b27]">
                      <td className="py-1.5 pr-2 font-mono text-xs text-slate-400">{fname}</td>
                      <td className="py-1.5 pr-2">
                        <input
                          value={(fdata.visible_to ?? []).join(', ')}
                          onChange={(e) =>
                            updateNode((n) => {
                              const f = n.fields[fname];
                              if (f) {
                                const val = e.target.value
                                  .split(',')
                                  .map((v) => v.trim())
                                  .filter(Boolean);
                                f.visible_to = val.length ? val : undefined;
                              }
                            })
                          }
                          className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                          placeholder="all"
                        />
                      </td>
                      <td className="py-1.5 pr-2 text-center">
                        <input
                          type="checkbox"
                          checked={fdata.pii ?? false}
                          onChange={(e) => updateNode((n) => { const f = n.fields[fname]; if (f) f.pii = e.target.checked || undefined; })}
                          className="accent-[#4f8ef7]"
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <input
                          value={fdata.mask_with ?? ''}
                          onChange={(e) =>
                            updateNode((n) => {
                              const f = n.fields[fname];
                              if (f) f.mask_with = e.target.value || undefined;
                            })
                          }
                          className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                          placeholder="e.g. hash, redact"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-4 text-center text-xs text-slate-600">Add fields first to configure access</div>
          )}
        </div>
      </div>
    );
  };

  // ── Main render ────────────────────────────────────────────────────────────

  const tabs: { key: EditorTab; label: string }[] = [
    { key: 'general', label: 'General' },
    { key: 'fields', label: 'Fields' },
    { key: 'edges', label: 'Edges' },
    { key: 'filters', label: 'Filters' },
    { key: 'access', label: 'Access' },
  ];

  return (
    <div className="flex h-full overflow-hidden bg-[#0f1117]">
      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
      {showAddNode && (
        <AddNodeDialog
          existingNames={nodeNames}
          onAdd={handleAddNode}
          onCancel={() => setShowAddNode(false)}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          message={`Delete node "${confirmDelete}"? This cannot be undone.`}
          onConfirm={() => handleDeleteNode(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {/* ── Left column: Node list ──────────────────────────────────── */}
      <div className="flex w-[30%] shrink-0 flex-col border-r border-[#252d3d]">
        <div className="shrink-0 border-b border-[#252d3d] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[10px] text-slate-500 uppercase tracking-widest">Nodes</span>
            <span className="rounded-full bg-[#1e2535] px-1.5 text-[10px] text-slate-500">{nodeNames.length}</span>
          </div>
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search nodes..."
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-xs text-slate-300 placeholder-slate-600 focus:border-[#4f8ef7] focus:outline-none"
          />
        </div>
        <div className="flex-1 overflow-y-auto">
          {filteredNodes.map((name) => {
            const nd = ontology.nodes[name];
            if (!nd) return null;
            const isSelected = selectedNode === name;
            return (
              <div
                key={name}
                onClick={() => {
                  setSelectedNode(name);
                  setActiveTab('general');
                }}
                className={`group flex cursor-pointer items-center justify-between border-b border-[#252d3d]/50 px-3 py-2.5 transition-colors hover:bg-[#161b27] ${
                  isSelected ? 'border-l-2 border-l-[#4f8ef7] bg-[#161b27]' : ''
                }`}
              >
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs text-slate-300">{name}</div>
                  <div className="truncate text-[10px] text-slate-600">{nd.table ?? name}</div>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmDelete(name);
                  }}
                  className="hidden text-slate-600 hover:text-red-400 group-hover:block"
                  title="Delete node"
                >
                  x
                </button>
              </div>
            );
          })}
          {filteredNodes.length === 0 && searchQuery && (
            <div className="py-6 text-center text-xs text-slate-600">No matching nodes</div>
          )}
        </div>
        <div className="shrink-0 border-t border-[#252d3d] p-3">
          <button
            type="button"
            onClick={() => setShowAddNode(true)}
            className="w-full rounded border border-[#252d3d] py-1.5 text-[11px] text-slate-400 hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
          >
            + Add Node
          </button>
        </div>
      </div>

      {/* ── Right column: Node editor ───────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Save bar */}
        <div className="flex shrink-0 items-center justify-between border-b border-[#252d3d] px-4 py-2">
          <div className="text-sm text-slate-400">
            {selectedNode ? (
              <>
                Editing <span className="font-mono text-slate-200">{selectedNode}</span>
              </>
            ) : (
              <span className="text-slate-600">Select a node to edit</span>
            )}
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={!isDirty || saving}
            className={`rounded px-4 py-1.5 text-[11px] font-semibold transition-all ${
              isDirty
                ? 'bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577]'
                : 'border border-[#252d3d] bg-[#1e2535] text-slate-600'
            }`}
          >
            {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
          </button>
        </div>

        {node && selectedNode ? (
          <>
            {/* Tabs */}
            <div className="flex shrink-0 border-b border-[#252d3d] bg-[#0f1117]">
              {tabs.map((t) => (
                <button
                  type="button"
                  key={t.key}
                  onClick={() => setActiveTab(t.key)}
                  className={`relative px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest transition-colors ${
                    activeTab === t.key ? 'text-[#4f8ef7]' : 'text-slate-600 hover:text-slate-400'
                  }`}
                >
                  {t.label}
                  {activeTab === t.key && <span className="absolute right-0 bottom-0 left-0 h-[2px] bg-[#4f8ef7]" />}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto">
              {activeTab === 'general' && renderGeneral()}
              {activeTab === 'fields' && renderFields()}
              {activeTab === 'edges' && renderEdges()}
              {activeTab === 'filters' && renderFilters()}
              {activeTab === 'access' && renderAccess()}
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <div className="mb-2 text-2xl text-slate-700">{ '⬡' }</div>
              <div className="text-sm text-slate-600">Select a node from the list to begin editing</div>
              <div className="mt-1 text-[10px] text-slate-700">or click "+ Add Node" to create a new one</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
