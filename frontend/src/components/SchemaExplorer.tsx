import { useState } from 'react';
import type { NodeInfo } from '../types';

interface Props {
  nodes: NodeInfo[];
  onInsert: (text: string) => void;
}

const TYPE_VAR: Record<string, string> = {
  string: 'var(--type-string)',
  integer: 'var(--type-integer)',
  numeric: 'var(--type-numeric)',
  boolean: 'var(--type-boolean)',
  date: 'var(--type-date)',
  enum: 'var(--type-enum)',
};

function Badge({ text, type }: { text: string; type: string }) {
  return (
    <span
      className="rounded px-1.5 py-0.5 font-mono text-[10px] border"
      style={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border)', color: TYPE_VAR[type] ?? 'var(--text-secondary)' }}
    >
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
      <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[11px] leading-snug" style={{ color: 'var(--text-secondary)' }}>{node.description}</p>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{node.table}</span>
              {node.visibleTo && (
                <span
                  className="rounded px-1.5 py-0.5 text-[9px] border cursor-pointer"
                  style={{ backgroundColor: 'var(--badge-red-bg)', borderColor: 'var(--badge-red-border)', color: 'var(--badge-red-text)' }}
                  title={`Node restricted to: ${node.visibleTo.join(', ')}`}
                  onClick={() => setTab('access')}
                >
                  🔒 {node.visibleTo.join(', ')}
                </span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={insertNodeTemplate}
              className="rounded border px-1.5 py-0.5 text-[10px] transition-colors"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
              title="Insert query template"
            >
              ↗ Insert
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 gap-3 border-b px-3" style={{ borderColor: 'var(--border)' }}>
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
                tab === t ? 'border-[#4f8ef7]' : 'border-transparent'
              }`}
              style={{ color: tab === t ? 'var(--accent)' : 'var(--text-muted)' }}
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
                className="group flex w-full items-center justify-between px-3 py-1.5 text-left"
                style={{ ['--tw-bg-opacity' as string]: 1 }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-elevated)')}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                onClick={() => onInsert(f.name)}
                title={`${f.description} — click to insert`}
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={`truncate font-mono text-[11px]`}
                    style={{ color: f.filterable ? 'var(--success)' : 'var(--text-primary)' }}
                  >
                    {f.name}
                  </span>
                  {f.filterable && <span className="shrink-0 text-[9px]" style={{ color: 'var(--text-secondary)' }}>⚡</span>}
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
                  <Badge text={f.type} type={f.type} />
                  <span className="text-[9px] opacity-0 transition-opacity group-hover:opacity-100" style={{ color: 'var(--text-muted)' }}>
                    ↗
                  </span>
                </div>
              </button>
            );
          })}

        {/* ── Edges ────────────────────────────────────────────────── */}
        {tab === 'edges' &&
          (node.edges.length === 0 ? (
            <p className="px-3 py-3 text-[11px]" style={{ color: 'var(--text-secondary)' }}>No edges defined</p>
          ) : (
            node.edges.map((e) => {
              const targetNode = allNodes.find((n) => n.name === e.target);
              return (
                <div
                  key={e.name}
                  className="group flex items-center gap-1 px-3 py-1.5"
                  onMouseEnter={(ev) => (ev.currentTarget.style.backgroundColor = 'var(--bg-elevated)')}
                  onMouseLeave={(ev) => (ev.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    onClick={() => onNavigate({ nodeType: e.target, label: e.name })}
                    title={e.description}
                  >
                    <div className="min-w-0">
                      <span className="font-mono text-[11px] " style={{ color: 'var(--field-edge)' }}>{e.name}</span>
                      <span className="ml-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>→ {e.target}</span>
                    </div>
                    {targetNode && (
                      <span className="shrink-0 text-[9px]" style={{ color: 'var(--text-secondary)' }}>{targetNode.fields.length}f</span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => onInsert(`${e.name} {\n    \n  }`)}
                    className="shrink-0 rounded border border-transparent px-1.5 py-0.5 text-[10px] opacity-0 transition-colors group-hover:opacity-100"
                    style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
                    title="Insert edge into query"
                  >
                    ↗
                  </button>
                  <span className="shrink-0 text-[10px]" style={{ color: 'var(--text-secondary)' }}>›</span>
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
                  className="flex w-full items-center justify-between px-3 py-1.5 text-left"
                  onMouseEnter={(ev) => (ev.currentTarget.style.backgroundColor = 'var(--bg-elevated)')}
                  onMouseLeave={(ev) => (ev.currentTarget.style.backgroundColor = 'transparent')}
                  onClick={() => onInsert(`${f.name}: `)}
                  title={f.description}
                >
                  <span className="font-mono text-[11px] " style={{ color: 'var(--field-filter)' }}>{f.name}</span>
                  <Badge text={f.type} type={f.type} />
                </button>
              ))}
            {node.specialFilters.map((sf) => (
              <button
                type="button"
                key={sf.name}
                className="flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left"
                onMouseEnter={(ev) => (ev.currentTarget.style.backgroundColor = 'var(--bg-elevated)')}
                onMouseLeave={(ev) => (ev.currentTarget.style.backgroundColor = 'transparent')}
                onClick={() => onInsert(sf.type === 'integer' ? `${sf.name}: 30` : `${sf.name}: true`)}
                title={sf.description}
              >
                <span className="font-mono text-[11px] " style={{ color: 'var(--field-special)' }}>
                  {sf.type === 'integer' ? `${sf.name}: 30` : `${sf.name}: true`}
                </span>
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{sf.description}</span>
              </button>
            ))}
            {node.fields.filter((f) => f.filterable).length === 0 && node.specialFilters.length === 0 && (
              <p className="px-3 py-3 text-[11px]" style={{ color: 'var(--text-secondary)' }}>No filters defined</p>
            )}
          </>
        )}

        {/* ── Access ───────────────────────────────────────────────── */}
        {tab === 'access' && (
          <div className="space-y-2.5 px-3 py-2">
            {/* Node-level policy */}
            <div className="rounded border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
              <p className="mb-2 font-semibold text-[11px] uppercase tracking-widest" style={{ color: 'var(--text-primary)' }}>Node Access</p>
              {node.visibleTo ? (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] ">🔒 Restricted</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    Visible to: <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{node.visibleTo.join(', ')}</span>
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-[11px]" style={{ color: 'var(--success)' }}>✓ Open</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>All roles can query this node</span>
                </div>
              )}
            </div>

            {/* Field-level policies */}
            <div className="rounded border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
              <p className="mb-2 font-semibold text-[11px] uppercase tracking-widest" style={{ color: 'var(--text-primary)' }}>Field Access</p>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead>
                    <tr className="border-b text-left" style={{ borderColor: 'var(--border)' }}>
                      <th className="py-1.5 pr-3 font-medium" style={{ color: 'var(--text-muted)' }}>Field</th>
                      <th className="py-1.5 pr-3 font-medium" style={{ color: 'var(--text-muted)' }}>Access</th>
                      <th className="py-1.5 pr-3 font-medium" style={{ color: 'var(--text-muted)' }}>PII</th>
                      <th className="py-1.5 font-medium" style={{ color: 'var(--text-muted)' }}>Masking</th>
                    </tr>
                  </thead>
                  <tbody>
                    {node.fields.map((f) => (
                      <tr key={f.name} className="border-b" style={{ borderColor: 'var(--bg-elevated)' }}>
                        <td className="py-1.5 pr-3">
                          <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{f.name}</span>
                        </td>
                        <td className="py-1.5 pr-3">
                          {f.visibleTo ? (
                            <span className="">🔒 {f.visibleTo.join(', ')}</span>
                          ) : (
                            <span style={{ color: 'var(--text-secondary)' }}>all</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3">
                          {f.pii ? (
                            <span
                              className="rounded px-1 py-0.5 text-[10px] border"
                              style={{ backgroundColor: 'var(--badge-pii-bg)', borderColor: 'var(--badge-pii-border)', color: 'var(--badge-pii-text)' }}
                            >
                              PII
                            </span>
                          ) : (
                            <span style={{ color: 'var(--text-secondary)' }}>—</span>
                          )}
                        </td>
                        <td className="py-1.5">
                          {f.maskWith ? (
                            <span className="font-mono text-[10px] text-[#a78bfa]">{f.maskWith}</span>
                          ) : (
                            <span style={{ color: 'var(--text-secondary)' }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Info note */}
            <p className="text-[10px] italic" style={{ color: 'var(--text-secondary)' }}>
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
      {filtered.length === 0 && <p className="px-3 py-3 text-[11px]" style={{ color: 'var(--text-secondary)' }}>No nodes match "{search}"</p>}
      {filtered.map((node) => (
        <button
          type="button"
          key={node.name}
          className="group flex w-full items-center justify-between border-b px-3 py-2.5 text-left"
          style={{ borderColor: 'var(--bg-input)' }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-elevated)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          onClick={() => onNavigate({ nodeType: node.name, label: node.name })}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono font-semibold text-[12px]" style={{ color: 'var(--accent)' }}>{node.name}</span>
              <span className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                {node.fieldCount}f · {node.edges.length}e
              </span>
              {node.visibleTo && (
                <span
                  className="rounded px-1 py-0.5 text-[9px] border"
                  style={{ backgroundColor: 'var(--badge-red-bg)', borderColor: 'var(--badge-red-border)', color: 'var(--badge-red-text)' }}
                >
                  🔒 {node.visibleTo.join(', ')}
                </span>
              )}
            </div>
            <p className="mt-0.5 truncate text-[10px]" style={{ color: 'var(--text-muted)' }}>{node.description}</p>
          </div>
          <div className="ml-2 flex shrink-0 items-center gap-1.5">
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>&#8250;</span>
          </div>
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
    <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="shrink-0 border-b px-3 pt-3 pb-2" style={{ borderColor: 'var(--border)' }}>
        <span className="font-semibold text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>Schema Explorer</span>

        {/* Breadcrumb */}
        <div className="mt-2 flex min-h-[18px] flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={() => goToIndex(-1)}
            className={`text-[11px] transition-colors ${
              navPath.length === 0 ? 'cursor-default' : 'hover:underline'
            }`}
            style={{ color: navPath.length === 0 ? 'var(--text-primary)' : 'var(--accent)' }}
          >
            Nodes
          </button>
          {navPath.map((entry, i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>/</span>
              <button
                type="button"
                onClick={() => goToIndex(i)}
                className={`max-w-[100px] truncate text-[11px] transition-colors ${
                  i === navPath.length - 1 ? 'cursor-default' : 'hover:underline'
                }`}
                style={{ color: i === navPath.length - 1 ? 'var(--text-primary)' : 'var(--accent)' }}
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
          <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: 'var(--border)' }}>
            <input
              type="text"
              placeholder="Search nodes…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded border px-2 py-1.5 text-xs focus:outline-none"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-input)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <div className="flex shrink-0 flex-wrap gap-3 border-b px-3 py-1.5" style={{ borderColor: 'var(--border)' }}>
            <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>Click node to explore</span>
            <span className="text-[9px]" style={{ color: 'var(--success)' }}>⚡ filterable</span>
            <span className="text-[9px]" style={{ color: 'var(--field-edge)' }}>→ edge</span>
            <span className="text-[9px]" style={{ color: 'var(--badge-red-text)' }}>🔒 restricted</span>
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
