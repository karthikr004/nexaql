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
    const duration = type === 'error' ? 8000 : 3500;
    const t = setTimeout(onDismiss, duration);
    return () => clearTimeout(t);
  }, [onDismiss, type]);

  return (
    <div
      className={`fixed top-4 right-4 z-50 max-w-lg rounded border px-4 py-3 text-sm shadow-lg ${
        type === 'success'
          ? 'border-[#3dd68c]/40 bg-[#1a2f25] text-[#3dd68c]'
          : 'border-red-500/40 bg-[#2f1a1a] text-red-400'
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="whitespace-pre-wrap text-[12px] leading-relaxed">{message}</div>
        <button type="button" onClick={onDismiss} className="shrink-0 text-[10px] opacity-60 hover:opacity-100">✕</button>
      </div>
    </div>
  );
}

// ── Shared input style helper ───────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  borderColor: 'var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-primary)',
};

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
};

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

    // ── Client-side validation ──────────────────────────────────────────
    const clientErrors: string[] = [];
    for (const [nodeName, nodeData] of Object.entries(ontology.nodes)) {
      if (!nodeData.primary_key) {
        clientErrors.push(`Node '${nodeName}': primary_key is required`);
      }
      if (!nodeData.description) {
        clientErrors.push(`Node '${nodeName}': description is required`);
      }
      for (const [fname, fdef] of Object.entries(nodeData.fields)) {
        if (!fdef.type) {
          clientErrors.push(`Node '${nodeName}' → field '${fname}': type is required`);
        }
        if (!fdef.description) {
          clientErrors.push(`Node '${nodeName}' → field '${fname}': description is required`);
        }
      }
      for (const [ename, edef] of Object.entries(nodeData.edges ?? {})) {
        if (!edef.node) {
          clientErrors.push(`Node '${nodeName}' → edge '${ename}': target node is required`);
        }
        if (!edef.join_steps || edef.join_steps.length === 0) {
          clientErrors.push(`Node '${nodeName}' → edge '${ename}': at least one join step is required`);
        }
      }
      for (const [sfname, sfdef] of Object.entries(nodeData.special_filters ?? {})) {
        if (!sfdef.sql) {
          clientErrors.push(`Node '${nodeName}' → filter '${sfname}': SQL expression is required`);
        }
      }
      // Validate row policies
      for (const [pi, pol] of (nodeData.row_policies ?? []).entries()) {
        if (pol.mode === 'function') {
          if (!pol.function_name) {
            clientErrors.push(`Node '${nodeName}' → row policy ${pi + 1}: policy function is required`);
          }
          if (!pol.function_field) {
            clientErrors.push(`Node '${nodeName}' → row policy ${pi + 1}: field (column) is required`);
          } else if (!nodeData.fields[pol.function_field]) {
            clientErrors.push(`Node '${nodeName}' → row policy ${pi + 1}: field '${pol.function_field}' does not exist on this node`);
          }
        } else if (!pol.condition) {
          clientErrors.push(`Node '${nodeName}' → row policy ${pi + 1}: SQL condition is required`);
        }
      }
    }
    // Validate access functions
    for (const [fname, fdef] of Object.entries(ontology.access_functions ?? {})) {
      if (!fdef.sql) {
        clientErrors.push(`Access function '${fname}': SQL template is required`);
      }
      if (!fdef.sql?.includes('{field}')) {
        clientErrors.push(`Access function '${fname}': SQL template must include {field} placeholder`);
      }
    }
    if (clientErrors.length > 0) {
      setToast({
        message: `Validation errors:\n${clientErrors.map((e) => `• ${e}`).join('\n')}`,
        type: 'error',
      });
      return;
    }

    setSaving(true);
    try {
      // Transform frontend RowPolicyData (function_name/function_field/mode)
      // to backend RowPolicy format (function/field/condition)
      const payload = deepClone(ontology);
      for (const node of Object.values(payload.nodes)) {
        if (node.row_policies) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (node as any).row_policies = node.row_policies.map((p: any) => {
            const roles = Array.isArray(p.roles) && p.roles.length > 0 ? p.roles : ['*'];
            if (p.mode === 'function' && p.function_name) {
              return {
                function: p.function_name,
                field: p.function_field || '',
                roles,
                ...(p.except_roles?.length ? { except_roles: p.except_roles } : {}),
              };
            }
            return {
              condition: p.condition || '',
              roles,
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
        const details: string[] = body.details ?? [];
        const msg = details.length > 0
          ? `Validation errors:\n${details.map((d: string) => `• ${d}`).join('\n')}`
          : body.message || body.error || `HTTP ${res.status}`;
        setToast({ message: msg, type: 'error' });
        return;
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

  // ── Roles + Access functions from ontology ──────────────────────────────────

  const roleNames = Object.keys(ontology?.roles ?? {});
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
      <div className="flex h-screen flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2.5" style={{ borderColor: 'var(--border)' }}>
          <button type="button" onClick={onBack} className="text-sm hover:underline" style={{ color: 'var(--accent)' }}>
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
      <div className="flex h-screen flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-2.5" style={{ borderColor: 'var(--border)' }}>
          <button type="button" onClick={onBack} className="text-sm hover:underline" style={{ color: 'var(--accent)' }}>
            &larr; Back to Playground
          </button>
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>Loading...</span>
        </div>
        <div className="flex flex-1 items-center justify-center text-sm" style={{ color: 'var(--text-secondary)' }}>Loading ontology...</div>
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
        <div className="flex w-[40%] shrink-0 flex-col border-r" style={{ borderColor: 'var(--border)' }}>
          <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: 'var(--border)' }}>
            <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Functions</span>
            <span className="ml-2 rounded-full px-1.5 text-[10px]" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>{fnEntries.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {fnEntries.map(([fnName]) => (
              <button
                type="button"
                key={fnName}
                onClick={() => setSelectedFunction(fnName)}
                className={`flex w-full items-center justify-between border-b px-3 py-2.5 text-left transition-colors ${
                  selectedFunction === fnName ? 'border-l-2 border-l-amber-500' : ''
                }`}
                style={{
                  borderBottomColor: 'var(--border)',
                  backgroundColor: selectedFunction === fnName ? 'var(--bg-input)' : 'transparent',
                }}
                onMouseEnter={(e) => { if (selectedFunction !== fnName) e.currentTarget.style.backgroundColor = 'var(--bg-input)'; }}
                onMouseLeave={(e) => { if (selectedFunction !== fnName) e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <span className="truncate font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{fnName}</span>
              </button>
            ))}
            {fnEntries.length === 0 && (
              <div className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No policy functions defined</div>
            )}
          </div>
          <div className="shrink-0 border-t p-3" style={{ borderColor: 'var(--border)' }}>
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
              className="w-full rounded border py-1.5 text-[11px] hover:border-amber-500 hover:text-amber-400"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
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
                  <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Name</label>
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
                    className="w-full rounded border px-2 py-1.5 font-mono text-sm focus:outline-none"
                    style={inputStyle}
                    placeholder="function_name"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Description</label>
                  <input
                    value={selectedFnData.description}
                    onChange={(e) =>
                      updateOntology((o) => {
                        const fn = o.access_functions?.[selectedFunction];
                        if (fn) fn.description = e.target.value;
                      })
                    }
                    className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
                    style={inputStyle}
                    placeholder="What this function does"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>SQL Template</label>
                  <textarea
                    rows={3}
                    value={selectedFnData.sql}
                    onChange={(e) =>
                      updateOntology((o) => {
                        const fn = o.access_functions?.[selectedFunction];
                        if (fn) fn.sql = e.target.value;
                      })
                    }
                    className="w-full rounded border px-2 py-1.5 font-mono text-sm focus:outline-none resize-none"
                    style={inputStyle}
                    placeholder="e.g. {field} = current_user_attr('org_id')"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Requires (comma-separated user context attributes)</label>
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
                    className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
                    style={inputStyle}
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
                <div className="mb-2 text-lg" style={{ color: 'var(--text-muted)' }}>&#x1f512;</div>
                <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>Select a function to view details</div>
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
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Table</label>
          <input
            value={node.table ?? ''}
            onChange={(e) => updateNode((n) => { n.table = e.target.value; })}
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Primary Key</label>
          <input
            value={node.primary_key}
            onChange={(e) => updateNode((n) => { n.primary_key = e.target.value; })}
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Description</label>
          <textarea
            rows={3}
            value={node.description}
            onChange={(e) => updateNode((n) => { n.description = e.target.value; })}
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none resize-none"
            style={inputStyle}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Datasource (optional)</label>
          <input
            value={node.datasource ?? ''}
            onChange={(e) => updateNode((n) => { n.datasource = e.target.value || undefined; })}
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
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
              <tr className="border-b text-[10px] uppercase tracking-widest" style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
                <th className="py-2 pr-2 text-left">Name</th>
                <th className="py-2 pr-2 text-left">Type</th>
                <th className="py-2 pr-2 text-left">Description</th>
                <th className="py-2 pr-2 text-center">Filterable</th>
                <th className="w-8 py-2" />
              </tr>
            </thead>
            <tbody>
              {fieldEntries.map(([fname, fdata]) => (
                <tr
                  key={fname}
                  className="border-b"
                  style={{ borderColor: 'var(--border)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-input)')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
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
                      className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none"
                      style={inputStyle}
                    />
                  </td>
                  <td className="py-1.5 pr-2">
                    <select
                      value={fdata.type}
                      onChange={(e) => updateNode((n) => { get(n.fields, fname).type = e.target.value; })}
                      className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                      style={inputStyle}
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
                      className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                      style={inputStyle}
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
                      className="hover:text-red-400"
                      style={{ color: 'var(--text-secondary)' }}
                      title="Delete field"
                    >
                      x
                    </button>
                  </td>
                </tr>
              ))}
              {fieldEntries.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No fields defined</td>
                </tr>
              )}
            </tbody>
          </table>
          {/* Enum values row */}
          {fieldEntries
            .filter(([, fd]) => fd.type === 'enum')
            .map(([fname, fdata]) => (
              <div key={`enum-${fname}`} className="mt-2 rounded border p-2" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
                <label className="text-[10px] uppercase tracking-widest" style={labelStyle}>
                  Enum values for <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{fname}</span>
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
                  className="mt-1 w-full rounded border px-2 py-1 font-mono text-xs focus:outline-none"
                  style={inputStyle}
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
          className="mt-3 rounded border px-3 py-1.5 text-[11px] transition-colors"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
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
          <div key={ename} className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
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
                className="rounded border px-2 py-1 font-mono text-xs focus:outline-none"
                style={inputStyle}
                placeholder="Edge name"
              />
              <button
                type="button"
                onClick={() => updateNode((n) => { if (n.edges) delete n.edges[ename]; })}
                className="hover:text-red-400"
                style={{ color: 'var(--text-secondary)' }}
                title="Delete edge"
              >
                x
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Target Node</label>
                <select
                  value={edata.node}
                  onChange={(e) => updateNode((n) => { const ed = n.edges?.[ename]; if (ed) ed.node = e.target.value; })}
                  className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                  style={inputStyle}
                >
                  <option value="">-- select --</option>
                  {nodeNames.map((nn) => (
                    <option key={nn} value={nn}>{nn}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Description</label>
                <input
                  value={edata.description}
                  onChange={(e) => updateNode((n) => { const ed = n.edges?.[ename]; if (ed) ed.description = e.target.value; })}
                  className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                  style={inputStyle}
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Join Type</label>
                <select
                  value={edata.join_type ?? 'JOIN'}
                  onChange={(e) => updateNode((n) => { const ed = n.edges?.[ename]; if (ed) ed.join_type = e.target.value; })}
                  className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                  style={inputStyle}
                >
                  {JOIN_TYPES.map((jt) => (
                    <option key={jt} value={jt}>{jt}</option>
                  ))}
                </select>
              </div>
            </div>
            {/* Join Steps */}
            <div className="mt-2">
              <label className="mb-1 block text-[9px] uppercase tracking-widest" style={labelStyle}>Join Steps</label>
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
                    className="rounded border px-1.5 py-1 font-mono text-[10px] focus:outline-none"
                    style={inputStyle}
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
                    className="rounded border px-1.5 py-1 font-mono text-[10px] focus:outline-none"
                    style={inputStyle}
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
                    className="rounded border px-1.5 py-1 font-mono text-[10px] focus:outline-none"
                    style={inputStyle}
                  />
                  <button
                    type="button"
                    onClick={() =>
                      updateNode((n) => {
                        const ed = n.edges?.[ename];
                        if (ed) ed.join_steps.splice(si, 1);
                      })
                    }
                    className="hover:text-red-400"
                    style={{ color: 'var(--text-secondary)' }}
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
                className="mt-1 text-[10px]"
                style={{ color: 'var(--text-muted)' }}
              >
                + Add Join Step
              </button>
            </div>
          </div>
        ))}
        {edgeEntries.length === 0 && (
          <div className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No edges defined</div>
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
          className="rounded border px-3 py-1.5 text-[11px] transition-colors"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
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
          <div key={fname} className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
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
                className="rounded border px-2 py-1 font-mono text-xs focus:outline-none"
                style={inputStyle}
                placeholder="Filter name"
              />
              <button
                type="button"
                onClick={() => updateNode((n) => { if (n.special_filters) delete n.special_filters[fname]; })}
                className="hover:text-red-400"
                style={{ color: 'var(--text-secondary)' }}
              >
                x
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Description</label>
                <input
                  value={fdata.description}
                  onChange={(e) =>
                    updateNode((n) => {
                      const sf = n.special_filters?.[fname];
                      if (sf) sf.description = e.target.value;
                    })
                  }
                  className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                  style={inputStyle}
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>SQL Expression</label>
                <input
                  value={fdata.sql}
                  onChange={(e) =>
                    updateNode((n) => {
                      const sf = n.special_filters?.[fname];
                      if (sf) sf.sql = e.target.value;
                    })
                  }
                  className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none"
                  style={inputStyle}
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Type (optional)</label>
                <select
                  value={fdata.type ?? ''}
                  onChange={(e) =>
                    updateNode((n) => {
                      const sf = n.special_filters?.[fname];
                      if (sf) sf.type = e.target.value || undefined;
                    })
                  }
                  className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                  style={inputStyle}
                >
                  <option value="">none</option>
                  <option value="integer">integer</option>
                </select>
              </div>
            </div>
          </div>
        ))}
        {filterEntries.length === 0 && (
          <div className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No special filters defined</div>
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
          className="rounded border px-3 py-1.5 text-[11px] transition-colors"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
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
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Node visible_to (comma-separated roles)</label>
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
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
            placeholder="e.g. analyst, manager, admin"
          />
        </div>

        {/* Row policies */}
        <div>
          <h4 className="mb-2 text-[10px] uppercase tracking-widest" style={labelStyle}>Row Policies</h4>
          {policies.map((pol, pi) => {
            const mode = pol.mode ?? 'raw';
            const testKey = `${selectedItem}-${pi}`;
            const testResult = policyTestResults[testKey] ?? null;
            const isTesting = policyTesting[testKey] ?? false;
            return (
              <div key={pi} className="mb-2 rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
                <div className="mb-2 flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Policy {pi + 1}</span>
                    <div className="inline-flex rounded-full border p-0.5" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-input)' }}>
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
                            : ''
                        }`}
                        style={mode !== 'function' ? { color: 'var(--text-muted)' } : undefined}
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
                            : ''
                        }`}
                        style={mode !== 'raw' ? { color: 'var(--text-muted)' } : undefined}
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
                    className="hover:text-red-400"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    x
                  </button>
                </div>
                <div className="space-y-2">
                  {mode === 'function' ? (
                    <>
                      <div>
                        <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Policy Function</label>
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
                          className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                          style={inputStyle}
                        >
                          <option value="">-- select function --</option>
                          {accessFunctionNames.map((fn) => (
                            <option key={fn} value={fn}>{fn}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Field (column the function applies to)</label>
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
                          className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none"
                          style={inputStyle}
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
                          <div className="rounded border p-2" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
                            <div className="mb-1 text-[9px]" style={{ color: 'var(--text-muted)' }}>{selFn.description}</div>
                            <div className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{selFn.sql}</div>
                            {(selFn.requires ?? []).length > 0 && (
                              <div className="mt-1 text-[9px]" style={{ color: 'var(--text-secondary)' }}>
                                Requires:{' '}
                                {selFn.requires!.map((r) => (
                                  <span key={r} className="mr-1 inline-block rounded px-1 py-0.5 font-mono text-[9px]" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>{r}</span>
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
                        <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Condition</label>
                        <input
                          value={pol.condition}
                          onChange={(e) =>
                            updateNode((n) => {
                              const p = n.row_policies?.[pi];
                              if (p) p.condition = e.target.value;
                            })
                          }
                          className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none"
                          style={inputStyle}
                        />
                      </div>
                      <div className="flex items-center gap-1.5 rounded border border-yellow-700/30 bg-yellow-900/10 px-2 py-1">
                        <span className="text-[10px] text-yellow-600">Raw SQL -- use policy functions for better validation</span>
                      </div>
                    </>
                  )}
                  <div>
                    <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Applies to Roles</label>
                    <div className="flex flex-wrap gap-1.5 rounded border px-2 py-1.5 min-h-[32px]" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-input)' }}>
                      {roleNames.length === 0 ? (
                        <span className="text-[10px] italic" style={{ color: 'var(--text-secondary)' }}>No roles defined — add roles in the Roles section</span>
                      ) : roleNames.map((rn) => {
                        const selected = pol.roles.includes(rn);
                        return (
                          <button
                            key={rn}
                            type="button"
                            onClick={() =>
                              updateNode((n) => {
                                const p = n.row_policies?.[pi];
                                if (!p) return;
                                if (selected) {
                                  p.roles = p.roles.filter((r) => r !== rn);
                                } else {
                                  p.roles = [...p.roles, rn];
                                }
                              })
                            }
                            className={`rounded px-2 py-0.5 text-[10px] font-medium border transition-colors ${
                              selected
                                ? 'bg-[#4f8ef7]/20 border-[#4f8ef7] text-[#4f8ef7]'
                                : ''
                            }`}
                            style={!selected ? { backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-muted)' } : undefined}
                          >
                            {rn}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div>
                    <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Except Roles</label>
                    <div className="flex flex-wrap gap-1.5 rounded border px-2 py-1.5 min-h-[32px]" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-input)' }}>
                      {roleNames.length === 0 ? (
                        <span className="text-[10px] italic" style={{ color: 'var(--text-secondary)' }}>No roles defined</span>
                      ) : roleNames.map((rn) => {
                        const selected = (pol.except_roles ?? []).includes(rn);
                        return (
                          <button
                            key={rn}
                            type="button"
                            onClick={() =>
                              updateNode((n) => {
                                const p = n.row_policies?.[pi];
                                if (!p) return;
                                const current = p.except_roles ?? [];
                                if (selected) {
                                  p.except_roles = current.filter((r) => r !== rn);
                                } else {
                                  p.except_roles = [...current, rn];
                                }
                              })
                            }
                            className={`rounded px-2 py-0.5 text-[10px] font-medium border transition-colors ${
                              selected
                                ? 'bg-red-500/20 border-red-500 text-red-400'
                                : ''
                            }`}
                            style={!selected ? { backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-muted)' } : undefined}
                          >
                            {rn}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  {/* Test Policy button */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={isTesting || !pol.condition}
                      onClick={() => handleTestPolicy(pi, resolvePolicyCondition(pol), pol.mode === 'function' ? pol.function_field : undefined)}
                      className="rounded border px-3 py-1 text-[10px] font-semibold disabled:opacity-40"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
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
            className="rounded border px-3 py-1.5 text-[11px] transition-colors"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            + Add Row Policy
          </button>
        </div>

        {/* Per-field access table */}
        <div>
          <h4 className="mb-2 text-[10px] uppercase tracking-widest" style={labelStyle}>Per-Field Access</h4>
          {fieldEntries.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-[10px] uppercase tracking-widest" style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
                    <th className="py-2 pr-2 text-left">Field</th>
                    <th className="py-2 pr-2 text-left">visible_to</th>
                    <th className="py-2 pr-2 text-center">PII</th>
                    <th className="py-2 pr-2 text-left">Mask Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {fieldEntries.map(([fname, fdata]) => (
                    <tr
                      key={fname}
                      className="border-b"
                      style={{ borderColor: 'var(--border)' }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-input)')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <td className="py-1.5 pr-2 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{fname}</td>
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
                          className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                          style={inputStyle}
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
                          className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none"
                          style={inputStyle}
                          placeholder="e.g. hash, redact"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-4 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>Add fields first to configure access</div>
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
    <div className="flex h-screen flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}

      {/* ── Header bar ─────────────────────────────────────────────── */}
      <header className="z-20 flex shrink-0 items-center justify-between border-b px-4 py-2.5" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-1 text-sm transition-colors"
            style={{ color: 'var(--accent)' }}
          >
            &larr; Back to Playground
          </button>
        </div>

        <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>NexaQL Admin</span>

        <button
          type="button"
          onClick={handleSave}
          disabled={!isDirty || saving}
          className={`rounded px-4 py-1.5 text-[12px] font-semibold transition-all ${
            isDirty
              ? 'bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577]'
              : 'border'
          }`}
          style={!isDirty ? { borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' } : undefined}
        >
          {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
        </button>
      </header>

      {/* ── Body: sidebar + content ────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Sidebar (250px) ──────────────────────────────────────── */}
        <div className="flex w-[250px] shrink-0 flex-col border-r" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
          {/* Sidebar header */}
          <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: 'var(--border)' }}>
            <span className="font-semibold text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>Schemas</span>
          </div>

          {/* Search */}
          <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: 'var(--border)' }}>
            <input
              type="text"
              placeholder="Search..."
              value={sidebarSearch}
              onChange={(e) => setSidebarSearch(e.target.value)}
              className="w-full rounded border px-2 py-1.5 text-xs focus:outline-none"
              style={inputStyle}
            />
          </div>

          {/* Roles + Policy Functions entries */}
          {!sidebarSearch && (
            <>
              <button
                type="button"
                onClick={() => setSelectedItem('__roles__')}
                className={`flex w-full items-center gap-2 border-b px-3 py-2.5 text-left transition-colors ${
                  selectedItem === '__roles__' ? 'border-l-2 border-l-green-500' : ''
                }`}
                style={{
                  borderBottomColor: 'var(--border)',
                  backgroundColor: selectedItem === '__roles__' ? 'var(--bg-elevated)' : 'transparent',
                }}
                onMouseEnter={(e) => { if (selectedItem !== '__roles__') e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'; }}
                onMouseLeave={(e) => { if (selectedItem !== '__roles__') e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <span className="font-semibold text-[12px]" style={{ color: 'var(--badge-green-text)' }}>Roles</span>
                <span className="rounded px-1 py-0.5 text-[9px] border" style={{ backgroundColor: 'var(--badge-green-bg)', borderColor: 'var(--badge-green-border)', color: 'var(--badge-green-text)' }}>
                  {Object.keys(ontology?.roles ?? {}).length} defined
                </span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectedItem('__policy_functions__');
                  setSelectedFunction(null);
                }}
                className={`flex w-full items-center gap-2 border-b px-3 py-2.5 text-left transition-colors ${
                  isPolicyFunctions ? 'border-l-2 border-l-amber-500' : ''
                }`}
                style={{
                  borderBottomColor: 'var(--border)',
                  backgroundColor: isPolicyFunctions ? 'var(--bg-elevated)' : 'transparent',
                }}
                onMouseEnter={(e) => { if (!isPolicyFunctions) e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'; }}
                onMouseLeave={(e) => { if (!isPolicyFunctions) e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <span className="font-semibold text-[12px]" style={{ color: 'var(--badge-amber-text)' }}>Policy Functions</span>
                <span className="rounded px-1 py-0.5 text-[9px] border" style={{ backgroundColor: 'var(--badge-amber-bg)', borderColor: 'var(--badge-amber-border)', color: 'var(--badge-amber-text)' }}>
                  ontology-level
                </span>
              </button>
              <div className="border-b" style={{ borderColor: 'var(--border)' }} />
            </>
          )}

          {/* Node list */}
          <div className="flex-1 overflow-y-auto">
            {filteredNodeNames.length === 0 && (
              <p className="px-3 py-3 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
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
                className={`flex w-full items-center justify-between border-b px-3 py-2.5 text-left transition-colors ${
                  selectedItem === name ? 'border-l-2 border-l-[#4f8ef7]' : ''
                }`}
                style={{
                  borderBottomColor: 'var(--border)',
                  backgroundColor: selectedItem === name ? 'var(--bg-elevated)' : 'transparent',
                }}
                onMouseEnter={(e) => { if (selectedItem !== name) e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'; }}
                onMouseLeave={(e) => { if (selectedItem !== name) e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <span className="truncate font-mono text-[12px]" style={{ color: 'var(--text-primary)' }}>{name}</span>
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>&rsaquo;</span>
              </button>
            ))}
          </div>

          {/* + New Schema */}
          <div className="shrink-0 border-t p-3" style={{ borderColor: 'var(--border)' }}>
            <button
              type="button"
              onClick={handleNewNode}
              className="flex w-full items-center justify-center gap-1.5 rounded border py-1.5 text-[11px]"
              style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}
            >
              + New Schema
            </button>
          </div>
        </div>

        {/* ── Main content area ────────────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
          {selectedItem === '__roles__' ? (
            /* Roles editor */
            <>
              <div className="shrink-0 border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
                <span className="font-semibold text-sm" style={{ color: 'var(--badge-green-text)' }}>Roles</span>
                <span className="ml-2 text-[10px]" style={{ color: 'var(--text-secondary)' }}>Define valid roles for access control policies</span>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                  Roles defined here are the only valid role names that can be used in <code style={{ color: 'var(--accent)' }}>visible_to</code>, <code style={{ color: 'var(--accent)' }}>row_policies</code>, and other access control settings. The source system (IdP/auth) maps users to these roles via the <code style={{ color: 'var(--accent)' }}>X-User-Context</code> header.
                </p>
                {Object.entries(ontology?.roles ?? {}).map(([roleName, roleDef]) => (
                  <div key={roleName} className="flex items-start gap-3 rounded border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
                    <div className="flex-1 space-y-2">
                      <input
                        defaultValue={roleName}
                        key={`rn-${roleName}`}
                        onBlur={(e) => {
                          const newName = e.target.value.trim();
                          if (newName && newName !== roleName) {
                            updateOntology((o) => {
                              if (!o.roles) return;
                              const def = o.roles[roleName] ?? { description: '' };
                              delete o.roles[roleName];
                              o.roles[newName] = def;
                            });
                          }
                        }}
                        className="rounded border px-2 py-1 font-mono text-sm font-semibold focus:outline-none"
                        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)', color: 'var(--accent)' }}
                        placeholder="role_name"
                      />
                      <input
                        defaultValue={roleDef.description}
                        key={`rd-${roleName}`}
                        onBlur={(e) =>
                          updateOntology((o) => {
                            if (o.roles?.[roleName]) o.roles[roleName].description = e.target.value;
                          })
                        }
                        className="w-full rounded border px-2 py-1 text-xs focus:outline-none"
                        style={inputStyle}
                        placeholder="Description"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => updateOntology((o) => { if (o.roles) delete o.roles[roleName]; })}
                      className="shrink-0 text-xs hover:text-red-400"
                      style={{ color: 'var(--text-secondary)' }}
                      title="Delete role"
                    >
                      ✕
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    updateOntology((o) => {
                      if (!o.roles) o.roles = {};
                      const name = `new_role_${Object.keys(o.roles).length + 1}`;
                      o.roles[name] = { description: '' };
                    })
                  }
                  className="rounded border px-3 py-1.5 text-[11px]"
                  style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}
                >
                  + Add Role
                </button>
              </div>
            </>
          ) : isPolicyFunctions ? (
            /* Policy functions view */
            <>
              <div className="shrink-0 border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
                <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Policy Functions</span>
                <span className="ml-2 text-[10px]" style={{ color: 'var(--text-secondary)' }}>(ontology-level)</span>
              </div>
              {renderPolicyFunctions()}
            </>
          ) : node && selectedItem ? (
            /* Node editor view */
            <>
              {/* Node header */}
              <div className="shrink-0 border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
                <div className="flex items-center gap-2 text-sm">
                  <span style={{ color: 'var(--text-muted)' }}>Editing:</span>
                  <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{selectedItem}</span>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex shrink-0 border-b" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
                {tabs.map((t) => (
                  <button
                    type="button"
                    key={t.key}
                    onClick={() => setActiveTab(t.key)}
                    className={`relative px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest transition-colors`}
                    style={{ color: activeTab === t.key ? 'var(--accent)' : 'var(--text-secondary)' }}
                  >
                    {t.label}
                    {activeTab === t.key && <span className="absolute right-0 bottom-0 left-0 h-[2px]" style={{ backgroundColor: 'var(--accent)' }} />}
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
                <div className="mb-3 text-3xl" style={{ color: 'var(--text-muted)' }}>&#x2699;</div>
                <p className="mb-1 text-sm" style={{ color: 'var(--text-secondary)' }}>NexaQL Admin</p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
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
