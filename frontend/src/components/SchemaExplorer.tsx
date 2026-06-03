import { useState } from 'react';
import type { NodeInfo } from '../types';

interface Props {
  nodes: NodeInfo[];
  onInsert: (text: string) => void;
}

const TYPE_COLOR: Record<string, string> = {
  string: 'text-orange-400',
  integer: 'text-cyan-400',
  numeric: 'text-cyan-400',
  boolean: 'text-purple-400',
  date: 'text-yellow-400',
  enum: 'text-green-400',
};

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span className={`rounded bg-[#1e2535] px-1.5 py-0.5 font-mono text-[10px] ${color} border border-[#252d3d]`}>
      {text}
    </span>
  );
}

// ── Navigation types ──────────────────────────────────────────────────────────

interface NavEntry {
  nodeType: string;
  label: string;
}

type DetailTab = 'fields' | 'edges' | 'filters' | 'access';

// ── Node detail view ──────────────────────────────────────────────────────────

function NodeDetail({
  node,
  allNodes,
  onInsert,
  onNavigate,
  initialTab,
}: {
  node: NodeInfo;
  allNodes: NodeInfo[];
  onInsert: (text: string) => void;
  onNavigate: (entry: NavEntry) => void;
  initialTab?: DetailTab;
}) {
  const [tab, setTab] = useState<DetailTab>(initialTab ?? 'fields');

  // Count fields with access restrictions
  const accessCount = (node.visibleTo ? 1 : 0) + node.fields.filter((f) => f.visibleTo || f.pii).length;

  const insertNodeTemplate = () => {
    const fields = node.fields
      .slice(0, 5)
      .map((f) => `    ${f.name}`)
      .join('\n');
    onInsert(`query {\n  ${node.name} {\n${fields}\n  }\n}`);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Node summary */}
      <div className="shrink-0 border-[#252d3d] border-b px-3 py-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[11px] text-slate-400 leading-snug">{node.description}</p>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="font-mono text-[10px] text-slate-600">{node.table}</span>
              {node.visibleTo && (
                <span
                  className="rounded bg-[#1a0f0f] px-1.5 py-0.5 text-[9px] text-red-400 border border-red-900/40 cursor-pointer"
                  title={`Node restricted to: ${node.visibleTo.join(', ')}`}
                  onClick={() => setTab('access')}
                >
                  🔒 {node.visibleTo.join(', ')}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={insertNodeTemplate}
            className="shrink-0 rounded border border-[#252d3d] bg-[#1e2535] px-1.5 py-0.5 text-[10px] text-slate-400 transition-colors hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
            title="Insert query template"
          >
            ↗ Insert
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 gap-3 border-[#252d3d] border-b px-3">
        {(['fields', 'edges', 'filters', 'access'] as const).map((t) => {
          const count =
            t === 'fields'
              ? node.fields.length
              : t === 'edges'
                ? node.edges.length
                : t === 'filters'
                  ? node.specialFilters.length
                  : accessCount;
          return (
            <button
              type="button"
              key={t}
              className={`border-b-2 py-1.5 text-[11px] capitalize transition-colors ${
                tab === t ? 'border-[#4f8ef7] text-[#4f8ef7]' : 'border-transparent text-slate-500 hover:text-slate-300'
              }`}
              onClick={() => setTab(t)}
            >
              {t === 'access' ? '🔒 Access' : t}&nbsp;
              {count > 0 && <span className="text-[10px] opacity-60">{count}</span>}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto py-1">
        {/* ── Fields ───────────────────────────────────────────────── */}
        {tab === 'fields' &&
          node.fields.map((f) => {
            const hasRestriction = f.visibleTo || f.pii;
            return (
              <button
                type="button"
                key={f.name}
                className="group flex w-full items-center justify-between px-3 py-1.5 text-left hover:bg-[#1e2535]"
                onClick={() => onInsert(f.name)}
                title={`${f.description} — click to insert`}
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={`truncate font-mono text-[11px] ${f.filterable ? 'text-[#3dd68c]' : 'text-slate-300'}`}
                  >
                    {f.name}
                  </span>
                  {f.filterable && <span className="shrink-0 text-[9px] text-slate-600">⚡</span>}
                  {hasRestriction && (
                    <span
                      className="shrink-0 text-[9px] cursor-pointer"
                      title={
                        f.visibleTo
                          ? `Restricted to: ${f.visibleTo.join(', ')}${f.pii ? ' · PII' : ''}`
                          : 'PII field'
                      }
                      onClick={(e) => {
                        e.stopPropagation();
                        setTab('access');
                      }}
                    >
                      🔒
                    </span>
                  )}
                </div>
                <div className="ml-2 flex shrink-0 items-center gap-1.5">
                  <Badge text={f.type} color={TYPE_COLOR[f.type] ?? 'text-slate-400'} />
                  <span className="text-[9px] text-slate-700 opacity-0 transition-opacity group-hover:opacity-100">
                    ↗
                  </span>
                </div>
              </button>
            );
          })}

        {/* ── Edges ────────────────────────────────────────────────── */}
        {tab === 'edges' &&
          (node.edges.length === 0 ? (
            <p className="px-3 py-3 text-[11px] text-slate-600">No edges defined</p>
          ) : (
            node.edges.map((e) => {
              const targetNode = allNodes.find((n) => n.name === e.target);
              return (
                <div key={e.name} className="group flex items-center gap-1 px-3 py-1.5 hover:bg-[#1e2535]">
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    onClick={() => onNavigate({ nodeType: e.target, label: e.name })}
                    title={e.description}
                  >
                    <div className="min-w-0">
                      <span className="font-mono text-[11px] text-orange-400">{e.name}</span>
                      <span className="ml-1.5 text-[10px] text-slate-500">→ {e.target}</span>
                    </div>
                    {targetNode && (
                      <span className="shrink-0 text-[9px] text-slate-600">{targetNode.fields.length}f</span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => onInsert(`${e.name} {\n    \n  }`)}
                    className="shrink-0 rounded border border-transparent bg-[#0f1117] px-1.5 py-0.5 text-[10px] text-slate-600 opacity-0 transition-colors hover:border-[#4f8ef7] hover:text-[#4f8ef7] group-hover:opacity-100"
                    title="Insert edge into query"
                  >
                    ↗
                  </button>
                  <span className="shrink-0 text-[10px] text-slate-600">›</span>
                </div>
              );
            })
          ))}

        {/* ── Filters ──────────────────────────────────────────────── */}
        {tab === 'filters' && (
          <>
            {node.fields
              .filter((f) => f.filterable)
              .map((f) => (
                <button
                  type="button"
                  key={f.name}
                  className="flex w-full items-center justify-between px-3 py-1.5 text-left hover:bg-[#1e2535]"
                  onClick={() => onInsert(`${f.name}: `)}
                  title={f.description}
                >
                  <span className="font-mono text-[11px] text-yellow-400">{f.name}</span>
                  <Badge text={f.type} color={TYPE_COLOR[f.type] ?? 'text-slate-400'} />
                </button>
              ))}
            {node.specialFilters.map((sf) => (
              <button
                type="button"
                key={sf.name}
                className="flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left hover:bg-[#1e2535]"
                onClick={() => onInsert(sf.type === 'integer' ? `${sf.name}: 30` : `${sf.name}: true`)}
                title={sf.description}
              >
                <span className="font-mono text-[11px] text-pink-400">
                  {sf.type === 'integer' ? `${sf.name}: 30` : `${sf.name}: true`}
                </span>
                <span className="text-[10px] text-slate-500">{sf.description}</span>
              </button>
            ))}
            {node.fields.filter((f) => f.filterable).length === 0 && node.specialFilters.length === 0 && (
              <p className="px-3 py-3 text-[11px] text-slate-600">No filters defined</p>
            )}
          </>
        )}

        {/* ── Access ───────────────────────────────────────────────── */}
        {tab === 'access' && (
          <div className="space-y-2.5 px-3 py-2">
            {/* Node-level policy */}
            <div className="rounded border border-[#252d3d] bg-[#131920] p-3">
              <p className="mb-2 font-semibold text-[11px] text-slate-300 uppercase tracking-widest">Node Access</p>
              {node.visibleTo ? (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-red-400">🔒 Restricted</span>
                  <span className="text-[11px] text-slate-400">
                    Visible to: <span className="font-mono text-slate-200">{node.visibleTo.join(', ')}</span>
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-[#3dd68c]">✓ Open</span>
                  <span className="text-[11px] text-slate-400">All roles can query this node</span>
                </div>
              )}
            </div>

            {/* Field-level policies */}
            <div className="rounded border border-[#252d3d] bg-[#131920] p-3">
              <p className="mb-2 font-semibold text-[11px] text-slate-300 uppercase tracking-widest">Field Access</p>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead>
                    <tr className="border-[#252d3d] border-b text-left">
                      <th className="py-1.5 pr-3 font-medium text-slate-500">Field</th>
                      <th className="py-1.5 pr-3 font-medium text-slate-500">Access</th>
                      <th className="py-1.5 pr-3 font-medium text-slate-500">PII</th>
                      <th className="py-1.5 font-medium text-slate-500">Masking</th>
                    </tr>
                  </thead>
                  <tbody>
                    {node.fields.map((f) => (
                      <tr key={f.name} className="border-[#1e2535] border-b">
                        <td className="py-1.5 pr-3">
                          <span className="font-mono text-slate-300">{f.name}</span>
                        </td>
                        <td className="py-1.5 pr-3">
                          {f.visibleTo ? (
                            <span className="text-red-400">🔒 {f.visibleTo.join(', ')}</span>
                          ) : (
                            <span className="text-slate-600">all</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3">
                          {f.pii ? (
                            <span className="rounded bg-yellow-950/20 px-1 py-0.5 text-[10px] text-yellow-400 border border-yellow-900/30">
                              PII
                            </span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="py-1.5">
                          {f.maskWith ? (
                            <span className="font-mono text-[10px] text-[#a78bfa]">{f.maskWith}</span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Info note */}
            <p className="text-[10px] text-slate-600 italic">
              Access policies are defined in the ontology YAML. Use the Role switcher in the header to test different
              access levels.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Root node list ────────────────────────────────────────────────────────────

function NodeList({
  nodes,
  search,
  onNavigate,
}: {
  nodes: NodeInfo[];
  search: string;
  onNavigate: (entry: NavEntry) => void;
}) {
  const filtered = nodes.filter(
    (n) =>
      !search || n.name.includes(search.toLowerCase()) || n.description.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex-1 overflow-y-auto py-1">
      {filtered.length === 0 && <p className="px-3 py-3 text-[11px] text-slate-600">No nodes match "{search}"</p>}
      {filtered.map((node) => (
        <button
          type="button"
          key={node.name}
          className="group flex w-full items-center justify-between border-[#161b27] border-b px-3 py-2.5 text-left hover:bg-[#1e2535]"
          onClick={() => onNavigate({ nodeType: node.name, label: node.name })}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono font-semibold text-[#4f8ef7] text-[12px]">{node.name}</span>
              <span className="text-[10px] text-slate-600">
                {node.fieldCount}f · {node.edges.length}e
              </span>
              {node.visibleTo && (
                <span className="rounded bg-[#1a0f0f] px-1 py-0.5 text-[9px] text-red-400 border border-red-900/40">
                  🔒 {node.visibleTo.join(', ')}
                </span>
              )}
            </div>
            <p className="mt-0.5 truncate text-[10px] text-slate-500">{node.description}</p>
          </div>
          <span className="ml-2 shrink-0 text-slate-600 text-sm group-hover:text-slate-400">›</span>
        </button>
      ))}
    </div>
  );
}

// ── Main explorer ─────────────────────────────────────────────────────────────

export default function SchemaExplorer({ nodes = [], onInsert }: Props) {
  const [navPath, setNavPath] = useState<NavEntry[]>([]);
  const [search, setSearch] = useState('');

  const currentEntry = navPath.length > 0 ? navPath[navPath.length - 1] : null;
  const currentNode = currentEntry ? (nodes.find((n) => n.name === currentEntry.nodeType) ?? null) : null;

  const navigate = (entry: NavEntry) => {
    setNavPath((prev) => [...prev, entry]);
    setSearch('');
  };

  const goToIndex = (index: number) => {
    setNavPath((prev) => (index < 0 ? [] : prev.slice(0, index + 1)));
  };

  return (
    <div className="flex h-full flex-col bg-[#0f1117]">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="shrink-0 border-[#252d3d] border-b px-3 pt-3 pb-2">
        <span className="font-semibold text-[10px] text-slate-400 uppercase tracking-widest">Schema Explorer</span>

        {/* Breadcrumb */}
        <div className="mt-2 flex min-h-[18px] flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={() => goToIndex(-1)}
            className={`text-[11px] transition-colors ${
              navPath.length === 0 ? 'cursor-default text-slate-300' : 'text-[#4f8ef7] hover:underline'
            }`}
          >
            Nodes
          </button>
          {navPath.map((entry, i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="text-[11px] text-slate-600">/</span>
              <button
                type="button"
                onClick={() => goToIndex(i)}
                className={`max-w-[100px] truncate text-[11px] transition-colors ${
                  i === navPath.length - 1 ? 'cursor-default text-slate-300' : 'text-[#4f8ef7] hover:underline'
                }`}
                title={entry.label}
              >
                {entry.label}
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* ── Legend (root only) ───────────────────────────────────── */}
      {!currentNode && (
        <>
          <div className="shrink-0 border-[#252d3d] border-b px-3 py-2">
            <input
              type="text"
              placeholder="Search nodes…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded border border-[#252d3d] bg-[#161b27] px-2 py-1.5 text-slate-300 text-xs placeholder-slate-600 focus:border-[#4f8ef7] focus:outline-none"
            />
          </div>
          <div className="flex shrink-0 flex-wrap gap-3 border-[#252d3d] border-b px-3 py-1.5">
            <span className="text-[9px] text-slate-500">Click node to explore</span>
            <span className="text-[#3dd68c] text-[9px]">⚡ filterable</span>
            <span className="text-[9px] text-orange-400">→ edge</span>
            <span className="text-[9px] text-red-400">🔒 restricted</span>
          </div>
        </>
      )}

      {/* ── Content ──────────────────────────────────────────────── */}
      {currentNode ? (
        <NodeDetail node={currentNode} allNodes={nodes} onInsert={onInsert} onNavigate={navigate} />
      ) : (
        <NodeList nodes={nodes} search={search} onNavigate={navigate} />
      )}
    </div>
  );
}
