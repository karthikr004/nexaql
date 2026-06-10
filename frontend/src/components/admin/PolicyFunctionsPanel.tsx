/**
 * Policy Functions editor — ontology-level access functions
 * that can be referenced by row policies.
 */
import { useState } from 'react';
import { SectionHeader, inputStyle, labelStyle } from './shared';
import type { OntologyData, AccessFunctionData } from '../../types';

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeEmptyAccessFunction(): AccessFunctionData {
  return { description: '', sql: '', requires: [] };
}

// ── Props ────────────────────────────────────────────────────────────────────

interface Props {
  ontology: OntologyData;
  onUpdate: (updater: (draft: OntologyData) => void) => void;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function PolicyFunctionsPanel({ ontology, onUpdate }: Props) {
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);

  const accessFunctions = ontology?.access_functions ?? {};
  const fnEntries = Object.entries(accessFunctions);
  const selectedFnData = selectedFunction ? accessFunctions[selectedFunction] : null;

  return (
    <>
      <SectionHeader title="Policy Functions" subtitle="(ontology-level)" />
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
                const name = `fn_${Object.keys(accessFunctions).length + 1}`;
                onUpdate((o) => {
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
                      onUpdate((o) => {
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
                      onUpdate((o) => {
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
                      onUpdate((o) => {
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
                      onUpdate((o) => {
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
                      onUpdate((o) => {
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
    </>
  );
}
