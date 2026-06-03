import { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  OntologyData,
  NodeData,
  FieldData,
  EdgeData,
  JoinStepData,
  SpecialFilterData,
  RowPolicyData,
  AccessFunctionData,
} from '../types';

// ── Props ────────────────────────────────────────────────────────────────────

interface AdminViewProps {
  onBack: () => void;
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

function get<V>(rec: Record<string, V>, key: string): V {
  const v = rec[key];
  if (v === undefined) throw new Error(`Missing key: ${key}`);
  return v;
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
  return { condition: '', roles: [], mode: 'function' };
}

function makeEmptyAccessFunction(): AccessFunctionData {
  return { description: '', sql: '', requires: [] };
}

function makeEmptyNode(): NodeData {
  return {
    primary_key: 'id',
    description: '',
    fields: {},
  };
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

// ── Main Component ──────────────────────────────────────────────────────────

export default function AdminView({ onBack, onOntologyChanged }: AdminViewProps) {
  const [ontology, setOntology] = useState<OntologyData | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState<string>('');
  const [activeTab, setActiveTab] = useState<EditorTab>('general');
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [policyTestResults, setPolicyTestResults] = useState<Record<string, { valid: boolean; message: string } | null>>({});
  const [policyTesting, setPolicyTesting] = useState<Record<string, boolean>>({});

  // Sidebar state
  const [selectedItem, setSelectedItem] = useState<string | null>(null); // node name, '__policy_functions__', or null
  const [sidebarSearch, setSidebarSearch] = useState('');

  // Policy functions sub-selection
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);

  const isPolicyFunctions = selectedItem === '__policy_functions__';

  // Load ontology
  useEffect(() => {
    fetch('/api/admin/ontology')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((resp) => {
        const data: OntologyData = resp.ontology ?? resp;
        // Transform backend RowPolicy (function/field) to frontend format (function_name/function_field/mode)
        for (const node of Object.values(data.nodes)) {
          if (node.row_policies) {
            node.row_policies = node.row_policies.map((p: any) => ({
              condition: p.condition ?? '',
              roles: p.roles ?? [],
              except_roles: p.except_roles,
              mode: p.function ? 'function' as const : 'raw' as const,
              function_name: p.function,
              function_field: p.field,
            }));
          }
        }
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

  const filteredNodeNames = useMemo(() => {
    if (!sidebarSearch) return nodeNames;
    const q = sidebarSearch.toLowerCase();
    return nodeNames.filter((n) => n.toLowerCase().includes(q));
  }, [nodeNames, sidebarSearch]);

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
      if (!selectedItem || isPolicyFunctions) return;
      updateOntology((o) => {
        const nd = o.nodes[selectedItem];
        if (nd) updater(nd);
      });
    },
    [selectedItem, isPolicyFunctions, updateOntology],
  );

  // ── Save ───────────────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!ontology || !isDirty) return;
    setSaving(true);
    try {
      // Transform frontend RowPolicyData (function_name/function_field/mode)
      // to backend RowPolicy format (function/field/condition)
      const payload = deepClone(ontology);
      for (const node of Object.values(payload.nodes)) {
        if (node.row_policies) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (node as any).row_policies = node.row_policies.map((p: any) => {
            if (p.mode === 'function' && p.function_name) {
              return {
                function: p.function_name,
                field: p.function_field || '',
                roles: p.roles,
                ...(p.except_roles?.length ? { except_roles: p.except_roles } : {}),
              };
            }
            return {
              condition: p.condition,
              roles: p.roles,
              ...(p.except_roles?.length ? { except_roles: p.except_roles } : {}),
            };
          });
        }
      }
      const res = await fetch('/api/admin/ontology', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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

  // ── Add new node ──────────────────────────────────────────────────────────

  const handleNewNode = useCallback(() => {
    const name = `new_node_${nodeNames.length + 1}`;
    updateOntology((o) => {
      o.nodes[name] = makeEmptyNode();
    });
    setSelectedItem(name);
    setActiveTab('general');
  }, [nodeNames.length, updateOntology]);

  // ── Current node data ──────────────────────────────────────────────────────

  const node = selectedItem && !isPolicyFunctions && ontology ? ontology.nodes[selectedItem] ?? null : null;

  // ── Access functions from ontology ─────────────────────────────────────────

  const accessFunctions = ontology?.access_functions ?? {};
  const accessFunctionNames = Object.keys(accessFunctions);

  // ── Policy test helpers ────────────────────────────────────────────────────

  const handleTestPolicy = async (policyIndex: number, condition: string, fieldName?: string) => {
    const key = `${selectedItem}-${policyIndex}`;
    setPolicyTesting((prev) => ({ ...prev, [key]: true }));
    setPolicyTestResults((prev) => ({ ...prev, [key]: null }));

    // Client-side: validate field name exists on the node
    if (fieldName && node) {
      const nodeFields = Object.keys(node.fields);
      if (!nodeFields.includes(fieldName)) {
        setPolicyTestResults((prev) => ({
          ...prev,
          [key]: {
            valid: false,
            message: `Field '${fieldName}' does not exist on node '${selectedItem}'. Available fields: ${nodeFields.join(', ')}`,
          },
        }));
        setPolicyTesting((prev) => ({ ...prev, [key]: false }));
        return;
      }
    }

    try {
      const res = await fetch('/api/admin/validate-policy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          condition,
          node_name: selectedItem,
          sample_user: {
            user_id: 'test-user-1',
            roles: ['manager'],
            attributes: { region: 'US-EAST', manager_id: 'mgr-1', team_id: 'engineering' },
          },
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        setPolicyTestResults((prev) => ({
          ...prev,
          [key]: { valid: true, message: body.resolved_sql ?? 'Policy is valid' },
        }));
      } else {
        setPolicyTestResults((prev) => ({
          ...prev,
          [key]: { valid: false, message: body.error ?? `HTTP ${res.status}` },
        }));
      }
    } catch (err) {
      setPolicyTestResults((prev) => ({
        ...prev,
        [key]: { valid: false, message: String(err) },
      }));
    } finally {
      setPolicyTesting((prev) => ({ ...prev, [key]: false }));
    }
  };

  const resolvePolicyCondition = (pol: RowPolicyData): string => {
    if (pol.mode === 'function' && pol.function_name) {
      const fn = accessFunctions[pol.function_name];
      if (fn && pol.function_field) {
        return fn.sql.replace(/\{field\}/g, pol.function_field);
      }
      return fn?.sql ?? pol.condition;
    }
    return pol.condition;
  };

  // ── Loading / error states ─────────────────────────────────────────────────

  if (loadError) {
    return (
      <div className="flex h-screen flex-col bg-[#0f1117]">
        <div className="flex shrink-0 items-center justify-between border-b border-[#252d3d] px-4 py-2.5">
          <button type="button" onClick={onBack} className="text-sm text-[#4f8ef7] hover:underline">
            &larr; Back to Playground
          </button>
          <span className="text-sm text-red-400">Error</span>
        </div>
        <div className="flex flex-1 items-center justify-center text-sm text-red-400">
          Failed to load ontology: {loadError}
        </div>
      </div>
    );
  }

  if (!ontology) {
    return (
      <div className="flex h-screen flex-col bg-[#0f1117]">
        <div className="flex shrink-0 items-center justify-between border-b border-[#252d3d] px-4 py-2.5">
          <button type="button" onClick={onBack} className="text-sm text-[#4f8ef7] hover:underline">
            &larr; Back to Playground
          </button>
          <span className="text-sm text-slate-400">Loading...</span>
        </div>
        <div className="flex flex-1 items-center justify-center text-sm text-slate-600">Loading ontology...</div>
      </div>
    );
  }

  // ── Render: Policy Functions (list + detail) ──────────────────────────────

  const renderPolicyFunctions = () => {
    const fnEntries = Object.entries(accessFunctions);
    const selectedFnData = selectedFunction ? accessFunctions[selectedFunction] : null;

    return (
      <div className="flex flex-1 overflow-hidden">
        {/* Left: function name list */}
        <div className="flex w-[40%] shrink-0 flex-col border-r border-[#252d3d]">
          <div className="shrink-0 border-b border-[#252d3d] px-3 py-2">
            <span className="text-[10px] text-slate-500 uppercase tracking-widest">Functions</span>
            <span className="ml-2 rounded-full bg-[#1e2535] px-1.5 text-[10px] text-slate-500">{fnEntries.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {fnEntries.map(([fnName]) => (
              <button
                type="button"
                key={fnName}
                onClick={() => setSelectedFunction(fnName)}
                className={`flex w-full items-center justify-between border-b border-[#252d3d]/50 px-3 py-2.5 text-left transition-colors hover:bg-[#161b27] ${
                  selectedFunction === fnName ? 'border-l-2 border-l-amber-500 bg-[#161b27]' : ''
                }`}
              >
                <span className="truncate font-mono text-xs text-slate-300">{fnName}</span>
              </button>
            ))}
            {fnEntries.length === 0 && (
              <div className="py-6 text-center text-xs text-slate-600">No policy functions defined</div>
            )}
          </div>
          <div className="shrink-0 border-t border-[#252d3d] p-3">
            <button
              type="button"
              onClick={() => {
                const name = `fn_${accessFunctionNames.length + 1}`;
                updateOntology((o) => {
                  if (!o.access_functions) o.access_functions = {};
                  o.access_functions[name] = makeEmptyAccessFunction();
                });
                setSelectedFunction(name);
              }}
              className="w-full rounded border border-[#252d3d] py-1.5 text-[11px] text-slate-400 hover:border-amber-500 hover:text-amber-400"
            >
              + Add Function
            </button>
          </div>
        </div>

        {/* Right: selected function detail */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {selectedFnData && selectedFunction ? (
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Name</label>
                  <input
                    value={selectedFunction}
                    onChange={(e) => {
                      const newName = e.target.value;
                      if (newName === selectedFunction) return;
                      updateOntology((o) => {
                        const fns = o.access_functions ?? {};
                        const val = fns[selectedFunction];
                        if (!val) return;
                        delete fns[selectedFunction];
                        fns[newName] = val;
                        o.access_functions = fns;
                      });
                      setSelectedFunction(newName);
                    }}
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 font-mono text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                    placeholder="function_name"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Description</label>
                  <input
                    value={selectedFnData.description}
                    onChange={(e) =>
                      updateOntology((o) => {
                        const fn = o.access_functions?.[selectedFunction];
                        if (fn) fn.description = e.target.value;
                      })
                    }
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                    placeholder="What this function does"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">SQL Template</label>
                  <textarea
                    rows={3}
                    value={selectedFnData.sql}
                    onChange={(e) =>
                      updateOntology((o) => {
                        const fn = o.access_functions?.[selectedFunction];
                        if (fn) fn.sql = e.target.value;
                      })
                    }
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 font-mono text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none resize-none"
                    placeholder="e.g. {field} = current_user_attr('org_id')"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Requires (comma-separated user context attributes)</label>
                  <input
                    value={(selectedFnData.requires ?? []).join(', ')}
                    onChange={(e) =>
                      updateOntology((o) => {
                        const fn = o.access_functions?.[selectedFunction];
                        if (fn) {
                          const val = e.target.value.split(',').map((v) => v.trim()).filter(Boolean);
                          fn.requires = val.length ? val : undefined;
                        }
                      })
                    }
                    className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                    placeholder="e.g. org_id, user_id"
                  />
                </div>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      updateOntology((o) => {
                        if (o.access_functions) delete o.access_functions[selectedFunction];
                      });
                      setSelectedFunction(null);
                    }}
                    className="rounded border border-red-900/40 px-3 py-1.5 text-[11px] text-red-400 hover:bg-red-900/20"
                  >
                    Delete Function
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center">
                <div className="mb-2 text-lg text-slate-700">&#x1f512;</div>
                <div className="text-xs text-slate-600">Select a function to view details</div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  // ── Render helpers for node editor tabs ─────────────────────────────────────

  const renderGeneral = () => {
    if (!node || !selectedItem) return null;
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
    if (!node) return null;
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
          {/* Enum values row */}
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
    if (!node) return null;
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
    if (!node) return null;
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
    if (!node || !selectedItem) return null;
    const policies = node.row_policies ?? [];
    const fieldEntries = Object.entries(node.fields);
    return (
      <div className="space-y-5 p-4">
        {/* Node-level visible_to */}
        <div>
          <label className="mb-1 block text-[10px] text-slate-500 uppercase tracking-widest">Node visible_to (comma-separated roles)</label>
          <input
            defaultValue={(node.visible_to ?? []).join(', ')}
            key={`vt-${selectedItem}`}
            onBlur={(e) =>
              updateNode((n) => {
                const val = e.target.value
                  .split(',')
                  .map((v) => v.trim())
                  .filter(Boolean);
                n.visible_to = val.length ? val : undefined;
              })
            }
            className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-sm text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
            placeholder="e.g. analyst, manager, admin"
          />
        </div>

        {/* Row policies */}
        <div>
          <h4 className="mb-2 text-[10px] text-slate-500 uppercase tracking-widest">Row Policies</h4>
          {policies.map((pol, pi) => {
            const mode = pol.mode ?? 'raw';
            const testKey = `${selectedItem}-${pi}`;
            const testResult = policyTestResults[testKey] ?? null;
            const isTesting = policyTesting[testKey] ?? false;
            return (
              <div key={pi} className="mb-2 rounded-lg border border-[#252d3d] bg-[#131920] p-3">
                <div className="mb-2 flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500">Policy {pi + 1}</span>
                    <div className="inline-flex rounded-full border border-[#252d3d] bg-[#161b27] p-0.5">
                      <button
                        type="button"
                        onClick={() =>
                          updateNode((n) => {
                            const p = n.row_policies?.[pi];
                            if (p) p.mode = 'function';
                          })
                        }
                        className={`rounded-full px-2 py-0.5 text-[9px] font-semibold transition-colors ${
                          mode === 'function'
                            ? 'bg-[#4f8ef7] text-white'
                            : 'text-slate-500 hover:text-slate-300'
                        }`}
                      >
                        Function
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          updateNode((n) => {
                            const p = n.row_policies?.[pi];
                            if (p) p.mode = 'raw';
                          })
                        }
                        className={`rounded-full px-2 py-0.5 text-[9px] font-semibold transition-colors ${
                          mode === 'raw'
                            ? 'bg-[#4f8ef7] text-white'
                            : 'text-slate-500 hover:text-slate-300'
                        }`}
                      >
                        Raw SQL
                      </button>
                    </div>
                  </div>
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
                  {mode === 'function' ? (
                    <>
                      <div>
                        <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Policy Function</label>
                        <select
                          value={pol.function_name ?? ''}
                          onChange={(e) =>
                            updateNode((n) => {
                              const p = n.row_policies?.[pi];
                              if (p) {
                                p.function_name = e.target.value || undefined;
                                const fn = accessFunctions[e.target.value];
                                if (fn && p.function_field) {
                                  p.condition = fn.sql.replace(/\{field\}/g, p.function_field);
                                } else if (fn) {
                                  p.condition = fn.sql;
                                }
                              }
                            })
                          }
                          className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                        >
                          <option value="">-- select function --</option>
                          {accessFunctionNames.map((fn) => (
                            <option key={fn} value={fn}>{fn}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Field (column the function applies to)</label>
                        <select
                          value={pol.function_field ?? ''}
                          onChange={(e) =>
                            updateNode((n) => {
                              const p = n.row_policies?.[pi];
                              if (p) {
                                p.function_field = e.target.value || undefined;
                                if (p.function_name) {
                                  const fn = accessFunctions[p.function_name];
                                  if (fn) {
                                    p.condition = fn.sql.replace(/\{field\}/g, e.target.value);
                                  }
                                }
                              }
                            })
                          }
                          className="w-full rounded border border-[#252d3d] bg-[#161b27] px-1.5 py-1 font-mono text-xs text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
                        >
                          <option value="">-- select column --</option>
                          {node && Object.keys(node.fields).map((fname) => (
                            <option key={fname} value={fname}>{fname}</option>
                          ))}
                        </select>
                      </div>
                      {(() => {
                        const selFn = pol.function_name ? accessFunctions[pol.function_name] : undefined;
                        if (!selFn) return null;
                        return (
                          <div className="rounded border border-[#252d3d]/60 bg-[#0f1117] p-2">
                            <div className="mb-1 text-[9px] text-slate-500">{selFn.description}</div>
                            <div className="font-mono text-[10px] text-slate-600">{selFn.sql}</div>
                            {(selFn.requires ?? []).length > 0 && (
                              <div className="mt-1 text-[9px] text-slate-600">
                                Requires:{' '}
                                {selFn.requires!.map((r) => (
                                  <span key={r} className="mr-1 inline-block rounded bg-[#1e2535] px-1 py-0.5 font-mono text-[9px] text-slate-400">{r}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </>
                  ) : (
                    <>
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
                      <div className="flex items-center gap-1.5 rounded border border-yellow-700/30 bg-yellow-900/10 px-2 py-1">
                        <span className="text-[10px] text-yellow-600">Raw SQL -- use policy functions for better validation</span>
                      </div>
                    </>
                  )}
                  <div>
                    <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Roles (comma-separated)</label>
                    <input
                      key={`roles-${selectedItem}-${pi}`}
                      defaultValue={pol.roles.join(', ')}
                      onBlur={(e) =>
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
                      placeholder="e.g. analyst, manager"
                    />
                  </div>
                  <div>
                    <label className="mb-0.5 block text-[9px] text-slate-500 uppercase tracking-widest">Except Roles (comma-separated)</label>
                    <input
                      key={`except-${selectedItem}-${pi}`}
                      defaultValue={(pol.except_roles ?? []).join(', ')}
                      onBlur={(e) =>
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
                      placeholder="e.g. admin"
                    />
                  </div>
                  {/* Test Policy button */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={isTesting || !pol.condition}
                      onClick={() => handleTestPolicy(pi, resolvePolicyCondition(pol), pol.mode === 'function' ? pol.function_field : undefined)}
                      className="rounded border border-[#252d3d] px-3 py-1 text-[10px] font-semibold text-slate-400 hover:border-[#4f8ef7] hover:text-[#4f8ef7] disabled:opacity-40"
                    >
                      {isTesting ? 'Testing...' : 'Test Policy'}
                    </button>
                    {testResult && (
                      <div
                        className={`flex-1 rounded border px-2 py-1 font-mono text-[10px] ${
                          testResult.valid
                            ? 'border-[#3dd68c]/40 bg-[#1a2f25]/50 text-[#3dd68c]'
                            : 'border-red-500/40 bg-[#2f1a1a]/50 text-red-400'
                        }`}
                      >
                        {testResult.valid ? 'Valid' : 'Error'}: {testResult.message}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
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

  // ── Editor tabs config ─────────────────────────────────────────────────────

  const tabs: { key: EditorTab; label: string }[] = [
    { key: 'general', label: 'General' },
    { key: 'fields', label: 'Fields' },
    { key: 'edges', label: 'Edges' },
    { key: 'filters', label: 'Filters' },
    { key: 'access', label: 'Access' },
  ];

  // ── Main render ────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#0f1117]">
      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}

      {/* ── Header bar ─────────────────────────────────────────────── */}
      <header className="z-20 flex shrink-0 items-center justify-between border-[#252d3d] border-b bg-[#0f1117] px-4 py-2.5">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-1 text-sm text-[#4f8ef7] transition-colors hover:text-[#3b7de8]"
          >
            &larr; Back to Playground
          </button>
        </div>

        <span className="font-semibold text-slate-200 text-sm">NexaQL Admin</span>

        <button
          type="button"
          onClick={handleSave}
          disabled={!isDirty || saving}
          className={`rounded px-4 py-1.5 text-[12px] font-semibold transition-all ${
            isDirty
              ? 'bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577]'
              : 'border border-[#252d3d] bg-[#1e2535] text-slate-600'
          }`}
        >
          {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
        </button>
      </header>

      {/* ── Body: sidebar + content ────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Sidebar (250px) ──────────────────────────────────────── */}
        <div className="flex w-[250px] shrink-0 flex-col border-r border-[#252d3d] bg-[#131920]">
          {/* Sidebar header */}
          <div className="shrink-0 border-b border-[#252d3d] px-3 py-2">
            <span className="font-semibold text-[10px] text-slate-400 uppercase tracking-widest">Schemas</span>
          </div>

          {/* Search */}
          <div className="shrink-0 border-b border-[#252d3d] px-3 py-2">
            <input
              type="text"
              placeholder="Search..."
              value={sidebarSearch}
              onChange={(e) => setSidebarSearch(e.target.value)}
              className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-slate-300 text-xs placeholder-slate-600 focus:border-[#4f8ef7] focus:outline-none"
            />
          </div>

          {/* Policy Functions entry */}
          {!sidebarSearch && (
            <>
              <button
                type="button"
                onClick={() => {
                  setSelectedItem('__policy_functions__');
                  setSelectedFunction(null);
                }}
                className={`flex w-full items-center gap-2 border-b border-[#252d3d] px-3 py-2.5 text-left transition-colors hover:bg-[#1e2535] ${
                  isPolicyFunctions ? 'bg-[#1e2535] border-l-2 border-l-amber-500' : ''
                }`}
              >
                <span className="font-semibold text-amber-400/90 text-[12px]">Policy Functions</span>
                <span className="rounded bg-amber-950/30 px-1 py-0.5 text-[9px] text-amber-500 border border-amber-800/40">
                  ontology-level
                </span>
              </button>
              <div className="border-b border-[#252d3d]" />
            </>
          )}

          {/* Node list */}
          <div className="flex-1 overflow-y-auto">
            {filteredNodeNames.length === 0 && (
              <p className="px-3 py-3 text-[11px] text-slate-600">
                {sidebarSearch ? `No nodes match "${sidebarSearch}"` : 'No nodes defined'}
              </p>
            )}
            {filteredNodeNames.map((name) => (
              <button
                type="button"
                key={name}
                onClick={() => {
                  setSelectedItem(name);
                  setActiveTab('general');
                }}
                className={`flex w-full items-center justify-between border-b border-[#252d3d]/50 px-3 py-2.5 text-left transition-colors hover:bg-[#1e2535] ${
                  selectedItem === name ? 'bg-[#1e2535] border-l-2 border-l-[#4f8ef7]' : ''
                }`}
              >
                <span className="truncate font-mono text-[12px] text-slate-300">{name}</span>
                <span className="text-slate-600 text-sm">&rsaquo;</span>
              </button>
            ))}
          </div>

          {/* + New Schema */}
          <div className="shrink-0 border-t border-[#252d3d] p-3">
            <button
              type="button"
              onClick={handleNewNode}
              className="flex w-full items-center justify-center gap-1.5 rounded border border-[#252d3d] py-1.5 text-[11px] text-[#4f8ef7] hover:border-[#4f8ef7] hover:bg-[#1e2535]"
            >
              + New Schema
            </button>
          </div>
        </div>

        {/* ── Main content area ────────────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden bg-[#0f1117]">
          {isPolicyFunctions ? (
            /* Policy functions view */
            <>
              <div className="shrink-0 border-b border-[#252d3d] px-4 py-2">
                <span className="font-semibold text-amber-400/90 text-sm">Policy Functions</span>
                <span className="ml-2 text-[10px] text-slate-600">(ontology-level)</span>
              </div>
              {renderPolicyFunctions()}
            </>
          ) : node && selectedItem ? (
            /* Node editor view */
            <>
              {/* Node header */}
              <div className="shrink-0 border-b border-[#252d3d] px-4 py-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-slate-500">Editing:</span>
                  <span className="font-mono text-slate-200">{selectedItem}</span>
                </div>
              </div>

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
            /* Welcome / nothing selected */
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center">
                <div className="mb-3 text-3xl text-slate-700">&#x2699;</div>
                <p className="mb-1 text-sm text-slate-400">NexaQL Admin</p>
                <p className="text-xs text-slate-600">
                  Select a schema from the sidebar to edit, or create a new one.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
