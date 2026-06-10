/**
 * Node editor — tabbed editor for a single ontology node.
 * Tabs: General, Fields, Edges, Filters, Access.
 */
import { useState } from 'react';
import { inputStyle, labelStyle } from './shared';
import type {
  OntologyData,
  NodeData,
  FieldData,
  EdgeData,
  JoinStepData,
  SpecialFilterData,
  RowPolicyData,
  AccessFunctionData,
} from '../../types';

// ── Constants ────────────────────────────────────────────────────────────────

type EditorTab = 'general' | 'fields' | 'edges' | 'filters' | 'access';

const FIELD_TYPES = ['string', 'integer', 'numeric', 'boolean', 'date', 'enum'];
const JOIN_TYPES = ['JOIN', 'LEFT', 'LEFT JOIN'];

const TABS: { key: EditorTab; label: string }[] = [
  { key: 'general', label: 'General' },
  { key: 'fields', label: 'Fields' },
  { key: 'edges', label: 'Edges' },
  { key: 'filters', label: 'Filters' },
  { key: 'access', label: 'Access' },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function get<V>(rec: Record<string, V>, key: string): V {
  const v = rec[key];
  if (v === undefined) throw new Error(`Missing key: ${key}`);
  return v;
}

function makeEmptyField(): FieldData { return { type: 'string', description: '', filterable: false }; }
function makeEmptyEdge(): EdgeData { return { node: '', description: '', join_steps: [] }; }
function makeEmptyJoinStep(): JoinStepData { return { table: '', alias_key: '', condition: '' }; }
function makeEmptyFilter(): SpecialFilterData { return { description: '', sql: '' }; }
function makeEmptyRowPolicy(): RowPolicyData { return { condition: '', roles: [], mode: 'function' }; }

// ── Props ────────────────────────────────────────────────────────────────────

interface Props {
  nodeName: string;
  node: NodeData;
  nodeNames: string[];
  roleNames: string[];
  accessFunctions: Record<string, AccessFunctionData>;
  onUpdateNode: (updater: (draft: NodeData) => void) => void;
  onUpdateOntology: (updater: (draft: OntologyData) => void) => void;
}

// ── Tab renderers ────────────────────────────────────────────────────────────

function GeneralTab({ node, onUpdate }: { node: NodeData; onUpdate: (u: (n: NodeData) => void) => void }) {
  return (
    <div className="space-y-4 p-4">
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Table</label>
        <input value={node.table ?? ''} onChange={(e) => onUpdate((n) => { n.table = e.target.value; })} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
      </div>
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Primary Key</label>
        <input value={node.primary_key} onChange={(e) => onUpdate((n) => { n.primary_key = e.target.value; })} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
      </div>
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Description</label>
        <textarea rows={3} value={node.description} onChange={(e) => onUpdate((n) => { n.description = e.target.value; })} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none resize-none" style={inputStyle} />
      </div>
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Datasource (optional)</label>
        <input value={node.datasource ?? ''} onChange={(e) => onUpdate((n) => { n.datasource = e.target.value || undefined; })} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
      </div>
    </div>
  );
}

function FieldsTab({ node, onUpdate }: { node: NodeData; onUpdate: (u: (n: NodeData) => void) => void }) {
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
              <tr key={fname} className="border-b" style={{ borderColor: 'var(--border)' }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-input)')}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}>
                <td className="py-1.5 pr-2">
                  <input value={fname} onChange={(e) => { const nn = e.target.value; if (nn === fname) return; onUpdate((n) => { const v = get(n.fields, fname); delete n.fields[fname]; n.fields[nn] = v; }); }}
                    className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none" style={inputStyle} />
                </td>
                <td className="py-1.5 pr-2">
                  <select value={fdata.type} onChange={(e) => onUpdate((n) => { get(n.fields, fname).type = e.target.value; })}
                    className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle}>
                    {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td className="py-1.5 pr-2">
                  <input value={fdata.description} onChange={(e) => onUpdate((n) => { get(n.fields, fname).description = e.target.value; })}
                    className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle} />
                </td>
                <td className="py-1.5 pr-2 text-center">
                  <input type="checkbox" checked={fdata.filterable ?? false} onChange={(e) => onUpdate((n) => { get(n.fields, fname).filterable = e.target.checked; })} className="accent-[#4f8ef7]" />
                </td>
                <td className="py-1.5 text-center">
                  <button type="button" onClick={() => onUpdate((n) => { delete n.fields[fname]; })} className="hover:text-red-400" style={{ color: 'var(--text-secondary)' }} title="Delete field">x</button>
                </td>
              </tr>
            ))}
            {fieldEntries.length === 0 && (
              <tr><td colSpan={5} className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No fields defined</td></tr>
            )}
          </tbody>
        </table>
        {/* Enum values */}
        {fieldEntries.filter(([, fd]) => fd.type === 'enum').map(([fname, fdata]) => (
          <div key={`enum-${fname}`} className="mt-2 rounded border p-2" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
            <label className="text-[10px] uppercase tracking-widest" style={labelStyle}>
              Enum values for <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{fname}</span>
            </label>
            <input value={(fdata.values ?? []).join(', ')} onChange={(e) => onUpdate((n) => { get(n.fields, fname).values = e.target.value.split(',').map((v) => v.trim()).filter(Boolean); })}
              placeholder="value1, value2, ..." className="mt-1 w-full rounded border px-2 py-1 font-mono text-xs focus:outline-none" style={inputStyle} />
          </div>
        ))}
      </div>
      <button type="button" onClick={() => { const name = `field_${Object.keys(node.fields).length + 1}`; onUpdate((n) => { n.fields[name] = makeEmptyField(); }); }}
        className="mt-3 rounded border px-3 py-1.5 text-[11px] transition-colors" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>+ Add Field</button>
    </div>
  );
}

function EdgesTab({ node, nodeNames, onUpdate }: { node: NodeData; nodeNames: string[]; onUpdate: (u: (n: NodeData) => void) => void }) {
  const edges = node.edges ?? {};
  const edgeEntries = Object.entries(edges);
  return (
    <div className="space-y-3 p-4">
      {edgeEntries.map(([ename, edata]) => (
        <div key={ename} className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
          <div className="mb-2 flex items-center justify-between">
            <input value={ename} onChange={(e) => { const nn = e.target.value; if (nn === ename) return; onUpdate((n) => { const ed = n.edges ?? {}; const v = get(ed, ename); delete ed[ename]; ed[nn] = v; n.edges = ed; }); }}
              className="rounded border px-2 py-1 font-mono text-xs focus:outline-none" style={inputStyle} placeholder="Edge name" />
            <button type="button" onClick={() => onUpdate((n) => { if (n.edges) delete n.edges[ename]; })} className="hover:text-red-400" style={{ color: 'var(--text-secondary)' }} title="Delete edge">x</button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Target Node</label>
              <select value={edata.node} onChange={(e) => onUpdate((n) => { const ed = n.edges?.[ename]; if (ed) ed.node = e.target.value; })}
                className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle}>
                <option value="">-- select --</option>
                {nodeNames.map((nn) => <option key={nn} value={nn}>{nn}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Description</label>
              <input value={edata.description} onChange={(e) => onUpdate((n) => { const ed = n.edges?.[ename]; if (ed) ed.description = e.target.value; })}
                className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle} />
            </div>
            <div>
              <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Join Type</label>
              <select value={edata.join_type ?? 'JOIN'} onChange={(e) => onUpdate((n) => { const ed = n.edges?.[ename]; if (ed) ed.join_type = e.target.value; })}
                className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle}>
                {JOIN_TYPES.map((jt) => <option key={jt} value={jt}>{jt}</option>)}
              </select>
            </div>
          </div>
          {/* Join Steps */}
          <div className="mt-2">
            <label className="mb-1 block text-[9px] uppercase tracking-widest" style={labelStyle}>Join Steps</label>
            {edata.join_steps.map((step, si) => (
              <div key={si} className="mb-1 grid grid-cols-[1fr_1fr_2fr_auto] gap-1.5">
                <input value={step.table} onChange={(e) => onUpdate((n) => { const s = n.edges?.[ename]?.join_steps[si]; if (s) s.table = e.target.value; })}
                  placeholder="table" className="rounded border px-1.5 py-1 font-mono text-[10px] focus:outline-none" style={inputStyle} />
                <input value={step.alias_key} onChange={(e) => onUpdate((n) => { const s = n.edges?.[ename]?.join_steps[si]; if (s) s.alias_key = e.target.value; })}
                  placeholder="alias_key" className="rounded border px-1.5 py-1 font-mono text-[10px] focus:outline-none" style={inputStyle} />
                <input value={step.condition} onChange={(e) => onUpdate((n) => { const s = n.edges?.[ename]?.join_steps[si]; if (s) s.condition = e.target.value; })}
                  placeholder="condition" className="rounded border px-1.5 py-1 font-mono text-[10px] focus:outline-none" style={inputStyle} />
                <button type="button" onClick={() => onUpdate((n) => { n.edges?.[ename]?.join_steps.splice(si, 1); })} className="hover:text-red-400" style={{ color: 'var(--text-secondary)' }}>x</button>
              </div>
            ))}
            <button type="button" onClick={() => onUpdate((n) => { const ed = n.edges?.[ename]; if (ed) ed.join_steps.push(makeEmptyJoinStep()); })}
              className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>+ Add Join Step</button>
          </div>
        </div>
      ))}
      {edgeEntries.length === 0 && <div className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No edges defined</div>}
      <button type="button" onClick={() => { const name = `edge_${Object.keys(edges).length + 1}`; onUpdate((n) => { if (!n.edges) n.edges = {}; n.edges[name] = makeEmptyEdge(); }); }}
        className="rounded border px-3 py-1.5 text-[11px] transition-colors" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>+ Add Edge</button>
    </div>
  );
}

function FiltersTab({ node, onUpdate }: { node: NodeData; onUpdate: (u: (n: NodeData) => void) => void }) {
  const filters = node.special_filters ?? {};
  const filterEntries = Object.entries(filters);
  return (
    <div className="space-y-3 p-4">
      {filterEntries.map(([fname, fdata]) => (
        <div key={fname} className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
          <div className="mb-2 flex items-center justify-between">
            <input value={fname} onChange={(e) => { const nn = e.target.value; if (nn === fname) return; onUpdate((n) => { const sf = n.special_filters ?? {}; const v = get(sf, fname); delete sf[fname]; sf[nn] = v; n.special_filters = sf; }); }}
              className="rounded border px-2 py-1 font-mono text-xs focus:outline-none" style={inputStyle} placeholder="Filter name" />
            <button type="button" onClick={() => onUpdate((n) => { if (n.special_filters) delete n.special_filters[fname]; })} className="hover:text-red-400" style={{ color: 'var(--text-secondary)' }}>x</button>
          </div>
          <div className="space-y-2">
            <div>
              <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Description</label>
              <input value={fdata.description} onChange={(e) => onUpdate((n) => { const sf = n.special_filters?.[fname]; if (sf) sf.description = e.target.value; })}
                className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle} />
            </div>
            <div>
              <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>SQL Expression</label>
              <input value={fdata.sql} onChange={(e) => onUpdate((n) => { const sf = n.special_filters?.[fname]; if (sf) sf.sql = e.target.value; })}
                className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none" style={inputStyle} />
            </div>
            <div>
              <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Type (optional)</label>
              <select value={fdata.type ?? ''} onChange={(e) => onUpdate((n) => { const sf = n.special_filters?.[fname]; if (sf) sf.type = e.target.value || undefined; })}
                className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle}>
                <option value="">none</option>
                <option value="integer">integer</option>
              </select>
            </div>
          </div>
        </div>
      ))}
      {filterEntries.length === 0 && <div className="py-6 text-center text-xs" style={{ color: 'var(--text-secondary)' }}>No special filters defined</div>}
      <button type="button" onClick={() => { const name = `filter_${Object.keys(filters).length + 1}`; onUpdate((n) => { if (!n.special_filters) n.special_filters = {}; n.special_filters[name] = makeEmptyFilter(); }); }}
        className="rounded border px-3 py-1.5 text-[11px] transition-colors" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>+ Add Filter</button>
    </div>
  );
}

function AccessTab({
  nodeName,
  node,
  roleNames,
  accessFunctions,
  onUpdate,
}: {
  nodeName: string;
  node: NodeData;
  roleNames: string[];
  accessFunctions: Record<string, AccessFunctionData>;
  onUpdate: (u: (n: NodeData) => void) => void;
}) {
  const [policyTestResults, setPolicyTestResults] = useState<Record<string, { valid: boolean; message: string } | null>>({});
  const [policyTesting, setPolicyTesting] = useState<Record<string, boolean>>({});

  const accessFunctionNames = Object.keys(accessFunctions);
  const policies = node.row_policies ?? [];
  const fieldEntries = Object.entries(node.fields);

  const resolvePolicyCondition = (pol: RowPolicyData): string => {
    if (pol.mode === 'function' && pol.function_name) {
      const fn = accessFunctions[pol.function_name];
      if (fn && pol.function_field) return fn.sql.replace(/\{field\}/g, pol.function_field);
      return fn?.sql ?? pol.condition;
    }
    return pol.condition;
  };

  const handleTestPolicy = async (pi: number, condition: string, fieldName?: string) => {
    const key = `${nodeName}-${pi}`;
    setPolicyTesting((prev) => ({ ...prev, [key]: true }));
    setPolicyTestResults((prev) => ({ ...prev, [key]: null }));

    if (fieldName && node) {
      const nodeFields = Object.keys(node.fields);
      if (!nodeFields.includes(fieldName)) {
        setPolicyTestResults((prev) => ({ ...prev, [key]: { valid: false, message: `Field '${fieldName}' does not exist on node '${nodeName}'. Available fields: ${nodeFields.join(', ')}` } }));
        setPolicyTesting((prev) => ({ ...prev, [key]: false }));
        return;
      }
    }

    try {
      const res = await fetch('/api/admin/validate-policy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ condition, node_name: nodeName, sample_user: { user_id: 'test-user-1', roles: ['manager'], attributes: { region: 'US-EAST', manager_id: 'mgr-1', team_id: 'engineering' } } }),
      });
      const body = await res.json().catch(() => ({}));
      setPolicyTestResults((prev) => ({ ...prev, [key]: res.ok ? { valid: true, message: body.resolved_sql ?? 'Policy is valid' } : { valid: false, message: body.error ?? `HTTP ${res.status}` } }));
    } catch (err) {
      setPolicyTestResults((prev) => ({ ...prev, [key]: { valid: false, message: String(err) } }));
    } finally {
      setPolicyTesting((prev) => ({ ...prev, [key]: false }));
    }
  };

  return (
    <div className="space-y-5 p-4">
      {/* Node-level visible_to */}
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Node visible_to (comma-separated roles)</label>
        <input
          defaultValue={(node.visible_to ?? []).join(', ')}
          key={`vt-${nodeName}`}
          onBlur={(e) => onUpdate((n) => { const val = e.target.value.split(',').map((v) => v.trim()).filter(Boolean); n.visible_to = val.length ? val : undefined; })}
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
          const testKey = `${nodeName}-${pi}`;
          const testResult = policyTestResults[testKey] ?? null;
          const isTesting = policyTesting[testKey] ?? false;
          return (
            <div key={pi} className="mb-2 rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
              <div className="mb-2 flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Policy {pi + 1}</span>
                  <PolicyModeToggle mode={mode} onChange={(m) => onUpdate((n) => { const p = n.row_policies?.[pi]; if (p) p.mode = m; })} />
                </div>
                <button type="button" onClick={() => onUpdate((n) => { if (n.row_policies) n.row_policies.splice(pi, 1); })} className="hover:text-red-400" style={{ color: 'var(--text-secondary)' }}>x</button>
              </div>
              <div className="space-y-2">
                {mode === 'function' ? (
                  <FunctionPolicyInputs pol={pol} pi={pi} node={node} accessFunctions={accessFunctions} accessFunctionNames={accessFunctionNames} onUpdate={onUpdate} />
                ) : (
                  <RawPolicyInput pol={pol} pi={pi} onUpdate={onUpdate} />
                )}
                <RolePicker label="Applies to Roles" selected={pol.roles} roleNames={roleNames} onChange={(roles) => onUpdate((n) => { const p = n.row_policies?.[pi]; if (p) p.roles = roles; })} color="blue" />
                <RolePicker label="Except Roles" selected={pol.except_roles ?? []} roleNames={roleNames} onChange={(roles) => onUpdate((n) => { const p = n.row_policies?.[pi]; if (p) p.except_roles = roles; })} color="red" />
                {/* Test */}
                <div className="flex items-center gap-2">
                  <button type="button" disabled={isTesting || !pol.condition} onClick={() => handleTestPolicy(pi, resolvePolicyCondition(pol), pol.mode === 'function' ? pol.function_field : undefined)}
                    className="rounded border px-3 py-1 text-[10px] font-semibold disabled:opacity-40" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                    {isTesting ? 'Testing...' : 'Test Policy'}
                  </button>
                  {testResult && (
                    <div className={`flex-1 rounded border px-2 py-1 font-mono text-[10px] ${testResult.valid ? 'border-[#3dd68c]/40 bg-[#1a2f25]/50 text-[#3dd68c]' : 'border-red-500/40 bg-[#2f1a1a]/50 text-red-400'}`}>
                      {testResult.valid ? 'Valid' : 'Error'}: {testResult.message}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        <button type="button" onClick={() => onUpdate((n) => { if (!n.row_policies) n.row_policies = []; n.row_policies.push(makeEmptyRowPolicy()); })}
          className="rounded border px-3 py-1.5 text-[11px] transition-colors" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>+ Add Row Policy</button>
      </div>

      {/* Per-field access */}
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
                  <tr key={fname} className="border-b" style={{ borderColor: 'var(--border)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-input)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}>
                    <td className="py-1.5 pr-2 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{fname}</td>
                    <td className="py-1.5 pr-2">
                      <input value={(fdata.visible_to ?? []).join(', ')} onChange={(e) => onUpdate((n) => { const f = n.fields[fname]; if (f) { const v = e.target.value.split(',').map((x) => x.trim()).filter(Boolean); f.visible_to = v.length ? v : undefined; } })}
                        className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle} placeholder="all" />
                    </td>
                    <td className="py-1.5 pr-2 text-center">
                      <input type="checkbox" checked={fdata.pii ?? false} onChange={(e) => onUpdate((n) => { const f = n.fields[fname]; if (f) f.pii = e.target.checked || undefined; })} className="accent-[#4f8ef7]" />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input value={fdata.mask_with ?? ''} onChange={(e) => onUpdate((n) => { const f = n.fields[fname]; if (f) f.mask_with = e.target.value || undefined; })}
                        className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle} placeholder="e.g. hash, redact" />
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
}

// ── Small reusable pieces for the Access tab ─────────────────────────────────

function PolicyModeToggle({ mode, onChange }: { mode: string; onChange: (m: 'function' | 'raw') => void }) {
  return (
    <div className="inline-flex rounded-full border p-0.5" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-input)' }}>
      {(['function', 'raw'] as const).map((m) => (
        <button key={m} type="button" onClick={() => onChange(m)}
          className={`rounded-full px-2 py-0.5 text-[9px] font-semibold transition-colors ${mode === m ? 'bg-[#4f8ef7] text-white' : ''}`}
          style={mode !== m ? { color: 'var(--text-muted)' } : undefined}>
          {m === 'function' ? 'Function' : 'Raw SQL'}
        </button>
      ))}
    </div>
  );
}

function FunctionPolicyInputs({
  pol, pi, node, accessFunctions, accessFunctionNames, onUpdate,
}: {
  pol: RowPolicyData; pi: number; node: NodeData;
  accessFunctions: Record<string, AccessFunctionData>;
  accessFunctionNames: string[];
  onUpdate: (u: (n: NodeData) => void) => void;
}) {
  const selFn = pol.function_name ? accessFunctions[pol.function_name] : undefined;
  return (
    <>
      <div>
        <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Policy Function</label>
        <select value={pol.function_name ?? ''} onChange={(e) => onUpdate((n) => { const p = n.row_policies?.[pi]; if (p) { p.function_name = e.target.value || undefined; const fn = accessFunctions[e.target.value]; if (fn && p.function_field) p.condition = fn.sql.replace(/\{field\}/g, p.function_field); else if (fn) p.condition = fn.sql; } })}
          className="w-full rounded border px-1.5 py-1 text-xs focus:outline-none" style={inputStyle}>
          <option value="">-- select function --</option>
          {accessFunctionNames.map((fn) => <option key={fn} value={fn}>{fn}</option>)}
        </select>
      </div>
      <div>
        <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Field (column the function applies to)</label>
        <select value={pol.function_field ?? ''} onChange={(e) => onUpdate((n) => { const p = n.row_policies?.[pi]; if (p) { p.function_field = e.target.value || undefined; if (p.function_name) { const fn = accessFunctions[p.function_name]; if (fn) p.condition = fn.sql.replace(/\{field\}/g, e.target.value); } } })}
          className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none" style={inputStyle}>
          <option value="">-- select column --</option>
          {Object.keys(node.fields).map((fname) => <option key={fname} value={fname}>{fname}</option>)}
        </select>
      </div>
      {selFn && (
        <div className="rounded border p-2" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
          <div className="mb-1 text-[9px]" style={{ color: 'var(--text-muted)' }}>{selFn.description}</div>
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{selFn.sql}</div>
          {(selFn.requires ?? []).length > 0 && (
            <div className="mt-1 text-[9px]" style={{ color: 'var(--text-secondary)' }}>
              Requires: {selFn.requires!.map((r) => <span key={r} className="mr-1 inline-block rounded px-1 py-0.5 font-mono text-[9px]" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>{r}</span>)}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function RawPolicyInput({ pol, pi, onUpdate }: { pol: RowPolicyData; pi: number; onUpdate: (u: (n: NodeData) => void) => void }) {
  return (
    <>
      <div>
        <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>Condition</label>
        <input value={pol.condition} onChange={(e) => onUpdate((n) => { const p = n.row_policies?.[pi]; if (p) p.condition = e.target.value; })}
          className="w-full rounded border px-1.5 py-1 font-mono text-xs focus:outline-none" style={inputStyle} />
      </div>
      <div className="flex items-center gap-1.5 rounded border border-yellow-700/30 bg-yellow-900/10 px-2 py-1">
        <span className="text-[10px] text-yellow-600">Raw SQL -- use policy functions for better validation</span>
      </div>
    </>
  );
}

function RolePicker({ label, selected, roleNames, onChange, color }: { label: string; selected: string[]; roleNames: string[]; onChange: (roles: string[]) => void; color: 'blue' | 'red' }) {
  return (
    <div>
      <label className="mb-0.5 block text-[9px] uppercase tracking-widest" style={labelStyle}>{label}</label>
      <div className="flex flex-wrap gap-1.5 rounded border px-2 py-1.5 min-h-[32px]" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-input)' }}>
        {roleNames.length === 0 ? (
          <span className="text-[10px] italic" style={{ color: 'var(--text-secondary)' }}>No roles defined</span>
        ) : roleNames.map((rn) => {
          const active = selected.includes(rn);
          const activeClass = color === 'blue' ? 'bg-[#4f8ef7]/20 border-[#4f8ef7] text-[#4f8ef7]' : 'bg-red-500/20 border-red-500 text-red-400';
          return (
            <button key={rn} type="button"
              onClick={() => onChange(active ? selected.filter((r) => r !== rn) : [...selected, rn])}
              className={`rounded px-2 py-0.5 text-[10px] font-medium border transition-colors ${active ? activeClass : ''}`}
              style={!active ? { backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-muted)' } : undefined}>
              {rn}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Main NodeEditor ──────────────────────────────────────────────────────────

export default function NodeEditor({ nodeName, node, nodeNames, roleNames, accessFunctions, onUpdateNode, onUpdateOntology: _onUpdateOntology }: Props) {
  void _onUpdateOntology; // reserved for future use (e.g. renaming nodes)
  const [activeTab, setActiveTab] = useState<EditorTab>('general');

  return (
    <>
      {/* Node header */}
      <div className="shrink-0 border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2 text-sm">
          <span style={{ color: 'var(--text-muted)' }}>Editing:</span>
          <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{nodeName}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 border-b" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
        {TABS.map((t) => (
          <button
            type="button"
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className="relative px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest transition-colors"
            style={{ color: activeTab === t.key ? 'var(--accent)' : 'var(--text-secondary)' }}
          >
            {t.label}
            {activeTab === t.key && <span className="absolute right-0 bottom-0 left-0 h-[2px]" style={{ backgroundColor: 'var(--accent)' }} />}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'general' && <GeneralTab node={node} onUpdate={onUpdateNode} />}
        {activeTab === 'fields' && <FieldsTab node={node} onUpdate={onUpdateNode} />}
        {activeTab === 'edges' && <EdgesTab node={node} nodeNames={nodeNames} onUpdate={onUpdateNode} />}
        {activeTab === 'filters' && <FiltersTab node={node} onUpdate={onUpdateNode} />}
        {activeTab === 'access' && <AccessTab nodeName={nodeName} node={node} roleNames={roleNames} accessFunctions={accessFunctions} onUpdate={onUpdateNode} />}
      </div>
    </>
  );
}
