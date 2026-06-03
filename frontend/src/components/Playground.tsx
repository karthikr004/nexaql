import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import SchemaExplorer from './SchemaExplorer';
import HistoryPanel from './HistoryPanel';
import SQLPreview from './SQLPreview';
import ResultsPanel from './ResultsPanel';
import AgentChat from './AgentChat';
import ChatQueryPanel from './ChatQueryPanel';
import type {
  OntologySummary,
  ExecuteResult,
  ValidationState,
  ChatTurn,
  HistoryEntry,
} from '../types';

const QueryEditor = lazy(() => import('./QueryEditor'));

// ── Helpers ───────────────────────────────────────────────────────────────────

const HISTORY_KEY = 'nexaql-query-history';
const MAX_HISTORY = 50;

function parseQueryName(query: string): string {
  const m = query.match(/query\s+([A-Za-z_]\w*)/);
  return m?.[1] ?? '(unnamed)';
}

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries: HistoryEntry[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
  } catch {
    /* ignore */
  }
}

// ── Default query ─────────────────────────────────────────────────────────────

const DEFAULT_QUERY = `# Welcome to NexaQL Playground
# ─────────────────────────────────────────────
# NexaQL lets you query any structured data
# in a single graph-traversal query.
#
# Try: select an example above, or start typing below.
# ⌘↩ (Ctrl+Enter) to run  ·  click field names in the schema to insert

query RecentOrders {
  order(status: "DELIVERED") @orderby(ordered_at, DESC) @limit(10) {
    id
    ordered_at
    total_amount
    customer {
      name
      email
    }
    items {
      quantity
      unit_price
      product {
        name
      }
    }
  }
}`;

// ── Component ─────────────────────────────────────────────────────────────────

export default function Playground() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [insertText, setInsertText] = useState<string | undefined>(undefined);
  const [ontology, setOntology] = useState<OntologySummary | null>(null);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [validation, setValidation] = useState<ValidationState>({
    valid: false,
    errors: [],
    warnings: [],
    queryPreview: undefined,
    adapterType: undefined,
  });
  const [validLoaded, setValidLoaded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isIdle, setIsIdle] = useState(true);

  // Role switcher for access control testing
  const [activeRole, setActiveRole] = useState<string>('anonymous');

  const ROLE_CONFIGS: Record<string, { label: string; roles: string[]; attributes: Record<string, string> }> = {
    anonymous: { label: '👤 Anonymous', roles: [], attributes: {} },
    analyst: { label: '🔍 Analyst', roles: ['analyst'], attributes: {} },
    'manager-east': { label: '🔒 Manager (US-EAST)', roles: ['manager'], attributes: { region: 'US-EAST' } },
    'manager-west': { label: '🔒 Manager (US-WEST)', roles: ['manager'], attributes: { region: 'US-WEST' } },
    'manager-eu': { label: '🔒 Manager (EU)', roles: ['manager'], attributes: { region: 'EU' } },
    admin: { label: '⚡ Admin (full access)', roles: ['admin'], attributes: {} },
  };

  const userContextHeaders = (): Record<string, string> => {
    const cfg = ROLE_CONFIGS[activeRole];
    if (!cfg) return {};
    return {
      'X-User-Context': JSON.stringify({
        user_id: activeRole === 'anonymous' ? 'anonymous' : 'demo',
        roles: cfg.roles,
        attributes: cfg.attributes,
      }),
    };
  };

  // Left panel view toggle
  const [leftView, setLeftView] = useState<'schema' | 'history'>('schema');

  // Center panel view toggle: query editor or chat
  const [centerView, setCenterView] = useState<'query' | 'chat'>('query');

  // Last completed chat turn — drives the right panel in chat mode
  const [lastChatTurn, setLastChatTurn] = useState<ChatTurn | null>(null);

  // Query history (loaded from localStorage on mount)
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  useEffect(() => {
    setHistory(loadHistory());
  }, []);

  // Panel widths as %
  const [leftWidth, setLeftWidth] = useState(22);
  const [rightWidth, setRightWidth] = useState(28);
  const [resultsH, setResultsH] = useState(38);

  const dragRef = useRef<{ type: string; startX: number; startVal: number } | null>(null);

  // Load ontology
  useEffect(() => {
    fetch('/api/ontology')
      .then((r) => r.json())
      .then((data) => {
        if (data && Array.isArray(data.nodes)) setOntology(data);
        else console.error('Ontology load failed:', data?.error ?? data);
      })
      .catch(console.error);
  }, []);

  // Reset results when role changes (forces re-run with new enforcement)
  const prevRoleRef = useRef(activeRole);
  useEffect(() => {
    if (prevRoleRef.current !== activeRole) {
      prevRoleRef.current = activeRole;
      setResult(null);
      setValidLoaded(false);
      setIsIdle(true);
    }
  }, [activeRole]);

  // Debounced validation — 400ms for keystrokes, immediate for role changes
  // Uses a counter to discard stale responses from previous requests
  const validateSeqRef = useRef(0);
  useEffect(() => {
    const seq = ++validateSeqRef.current;
    const delay = prevRoleRef.current !== activeRole ? 0 : 400;
    const headers = userContextHeaders(); // capture at effect time
    const t = setTimeout(() => {
      if (!query.trim()) return;
      fetch('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ query }),
      })
        .then((r) => r.json())
        .then((v) => {
          // Only apply if this is still the latest request
          if (seq === validateSeqRef.current) {
            setValidation(v);
            setValidLoaded(true);
          }
        })
        .catch(() => {});
    }, delay);
    return () => clearTimeout(t);
  }, [query, activeRole]);

  // Add entry to history (dedupes by query text, most recent first)
  const addToHistory = useCallback((entry: HistoryEntry) => {
    setHistory((prev) => {
      const next = [entry, ...prev.filter((h) => h.query.trim() !== entry.query.trim())].slice(0, MAX_HISTORY);
      saveHistory(next);
      return next;
    });
  }, []);

  const runQuery = useCallback(async () => {
    if (!query.trim() || isRunning) return;
    setIsRunning(true);
    setIsIdle(false);
    const t0 = Date.now();
    try {
      const res = await fetch('/api/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...userContextHeaders() },
        body: JSON.stringify({ query }),
      });
      const data: ExecuteResult = await res.json();
      setResult(data);

      // Record in history
      addToHistory({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        query,
        queryName: parseQueryName(query),
        timestamp: Date.now(),
        rowCount: data.error ? undefined : (data.rowCount ?? 0),
        durationMs: Date.now() - t0,
        hadError: !!data.error,
      });
    } catch (e) {
      setResult({ error: String(e), rows: [], columns: [] });
      addToHistory({
        id: `${Date.now()}-err`,
        query,
        queryName: parseQueryName(query),
        timestamp: Date.now(),
        hadError: true,
      });
    } finally {
      setIsRunning(false);
    }
  }, [query, isRunning, activeRole, addToHistory]);

  const handleInsert = useCallback((text: string) => {
    setInsertText(text);
  }, []);

  const handleLoadHistory = useCallback((q: string) => {
    setQuery(q);
    setLeftView('schema');
  }, []);

  const handleDeleteHistory = useCallback((id: string) => {
    setHistory((prev) => {
      const next = prev.filter((h) => h.id !== id);
      saveHistory(next);
      return next;
    });
  }, []);

  const handleClearHistory = useCallback(() => {
    setHistory([]);
    saveHistory([]);
  }, []);

  // Horizontal resize
  const startHDrag = (type: 'left' | 'right', e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { type, startX: e.clientX, startVal: type === 'left' ? leftWidth : rightWidth };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = ((ev.clientX - dragRef.current.startX) / window.innerWidth) * 100;
      const drag = dragRef.current;
      if (drag.type === 'left') setLeftWidth(() => Math.min(35, Math.max(15, drag.startVal + delta)));
      else setRightWidth(() => Math.min(40, Math.max(18, drag.startVal - delta)));
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // Vertical resize
  const startVDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = resultsH;
    const onMove = (ev: MouseEvent) => {
      const delta = -((ev.clientY - startY) / window.innerHeight) * 100;
      setResultsH(Math.min(70, Math.max(15, startH + delta)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const centerWidth = 100 - leftWidth - rightWidth;

  const validationBadge = () => {
    if (!validLoaded) return null;
    if (validation.valid)
      return (
        <span className="flex items-center gap-1 text-[#3dd68c] text-[11px]">
          <span>&#x2713;</span> Valid
        </span>
      );
    return (
      <span className="flex items-center gap-1 text-[11px] text-red-400">
        <span>&#x2717;</span> {validation.errors[0]?.slice(0, 60)}
      </span>
    );
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#0f1117]">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="z-20 flex shrink-0 items-center justify-between border-[#252d3d] border-b bg-[#0f1117] px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{'⬡'}</span>
            <span className="font-semibold text-slate-200 text-sm">NexaQL</span>
            <span className="text-slate-600 text-sm">/</span>
            <span className="text-[#4f8ef7] text-sm">NexaQL Playground</span>
          </div>
          {ontology && (
            <span className="rounded-full border border-[#252d3d] bg-[#1e2535] px-2 py-0.5 text-[10px] text-slate-400">
              {ontology.domain} {'·'} {ontology.nodes.length} nodes
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Role switcher */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-500 uppercase tracking-widest">Role</span>
            <select
              value={activeRole}
              onChange={(e) => setActiveRole(e.target.value)}
              className="rounded border border-[#252d3d] bg-[#1e2535] px-2 py-1 text-[11px] text-slate-300 focus:border-[#4f8ef7] focus:outline-none"
            >
              {Object.entries(ROLE_CONFIGS).map(([key, cfg]) => (
                <option key={key} value={key}>
                  {cfg.label}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-48">{validationBadge()}</div>
          <button
            type="button"
            onClick={() =>
              fetch('/api/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...userContextHeaders() },
                body: JSON.stringify({ query }),
              })
                .then((r) => r.json())
                .then((v) => {
                  setValidation(v);
                  setValidLoaded(true);
                })
            }
            className="rounded border border-[#252d3d] bg-[#1e2535] px-3 py-1.5 font-medium text-[11px] text-slate-300 transition-colors hover:border-[#4f8ef7] hover:text-[#4f8ef7]"
          >
            Validate
          </button>
          <button
            type="button"
            onClick={runQuery}
            disabled={isRunning || (validLoaded && !validation.valid)}
            className={`flex items-center gap-1.5 rounded px-4 py-1.5 font-semibold text-[12px] transition-all ${
              isRunning
                ? 'running-border cursor-wait border border-[#4f8ef7] bg-[#1e3a5f] text-[#4f8ef7]'
                : validLoaded && !validation.valid
                  ? 'cursor-not-allowed border border-[#252d3d] bg-[#1e2535] text-slate-600'
                  : 'border border-transparent bg-[#4f8ef7] text-white shadow-blue-900/30 shadow-lg hover:bg-[#3b7de8]'
            }`}
          >
            {isRunning ? (
              <>
                <div className="h-3 w-3 animate-spin rounded-full border-2 border-[#4f8ef7] border-t-transparent" />
                Running...
              </>
            ) : (
              <>
                {'▶'} Run<span className="ml-1 text-[10px] opacity-60">{'⌘↩'}</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* ── Main area ───────────────────────────────────────────────── */}
      {/* Chat mode: full height. Query mode: share height with results panel */}
      <div
        className="flex overflow-hidden"
        style={centerView === 'chat' ? { flex: '1 1 0', minHeight: 0 } : { height: `${100 - resultsH}%` }}
      >
        {/* Left panel */}
        <div
          style={{ width: `${leftWidth}%` }}
          className="flex shrink-0 flex-col overflow-hidden border-[#252d3d] border-r"
        >
          {/* Left panel tab toggle */}
          <div className="flex shrink-0 border-[#252d3d] border-b bg-[#0f1117]">
            {(['schema', 'history'] as const).map((view) => (
              <button
                type="button"
                key={view}
                onClick={() => setLeftView(view)}
                className={`relative flex-1 py-1.5 font-semibold text-[10px] uppercase tracking-widest transition-colors ${
                  leftView === view ? 'text-[#4f8ef7]' : 'text-slate-600 hover:text-slate-400'
                }`}
              >
                {view === 'schema' ? (
                  'Schema'
                ) : (
                  <span className="flex items-center justify-center gap-1">
                    History
                    {history.length > 0 && (
                      <span className="rounded-full bg-[#1e2535] px-1 text-[9px] text-slate-500">{history.length}</span>
                    )}
                  </span>
                )}
                {leftView === view && <span className="absolute right-0 bottom-0 left-0 h-[2px] bg-[#4f8ef7]" />}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-hidden">
            {leftView === 'schema' ? (
              ontology ? (
                <SchemaExplorer nodes={ontology.nodes} onInsert={handleInsert} />
              ) : (
                <div className="flex h-full items-center justify-center text-slate-600 text-xs">Loading schema...</div>
              )
            ) : (
              <HistoryPanel
                entries={history}
                onLoad={handleLoadHistory}
                onDelete={handleDeleteHistory}
                onClear={handleClearHistory}
              />
            )}
          </div>
        </div>

        {/* Left resizer */}
        <div
          className="z-10 w-1 shrink-0 cursor-col-resize bg-[#252d3d] transition-colors hover:bg-[#4f8ef7]"
          onMouseDown={(e) => startHDrag('left', e)}
        />

        {/* Center: Query Editor / Chat */}
        <div style={{ width: `${centerWidth}%` }} className="flex shrink-0 flex-col overflow-hidden">
          {/* Center tab bar */}
          <div className="flex shrink-0 border-[#252d3d] border-b bg-[#0f1117]">
            {(['query', 'chat'] as const).map((view) => (
              <button
                type="button"
                key={view}
                onClick={() => setCenterView(view)}
                className={`relative px-4 py-1.5 font-semibold text-[10px] uppercase tracking-widest transition-colors ${
                  centerView === view ? 'text-[#4f8ef7]' : 'text-slate-600 hover:text-slate-400'
                }`}
              >
                {view === 'query' ? 'Query Editor' : '✦ Agent Chat'}
                {centerView === view && <span className="absolute right-0 bottom-0 left-0 h-[2px] bg-[#4f8ef7]" />}
              </button>
            ))}
            {centerView === 'query' && (
              <span className="ml-auto self-center pr-3 font-mono text-[10px] text-slate-600">nexaql</span>
            )}
          </div>

          {/* Center content */}
          <div className="flex-1 overflow-hidden">
            {centerView === 'query' ? (
              <Suspense fallback={<div className="flex h-full items-center justify-center text-slate-600 text-xs">Loading editor...</div>}>
                <QueryEditor
                  value={query}
                  onChange={setQuery}
                  onRun={runQuery}
                  insertText={insertText}
                  onInsertConsumed={() => setInsertText(undefined)}
                  ontologyNodes={ontology?.nodes ?? []}
                />
              </Suspense>
            ) : (
              <AgentChat onTurnComplete={setLastChatTurn} />
            )}
          </div>
        </div>

        {/* Right resizer */}
        <div
          className="z-10 w-1 shrink-0 cursor-col-resize bg-[#252d3d] transition-colors hover:bg-[#4f8ef7]"
          onMouseDown={(e) => startHDrag('right', e)}
        />

        {/* Right: SQL Preview (query mode) or Chat Query Panel (chat mode) */}
        <div style={{ width: `${rightWidth}%` }} className="shrink-0 overflow-hidden">
          {centerView === 'chat' ? (
            <ChatQueryPanel
              nexaqlQuery={lastChatTurn?.nexaqlQuery ?? null}
              queryPreview={lastChatTurn?.queryPreview ?? null}
              adapterType={lastChatTurn?.adapterType ?? null}
            />
          ) : (
            <SQLPreview
              queryPreview={result?.queryPreview ?? validation.queryPreview ?? null}
              adapterType={result?.adapterType ?? validation.adapterType ?? null}
              isLoading={isRunning}
            />
          )}
        </div>
      </div>

      {/* Vertical resizer + Results panel — hidden in chat mode */}
      {centerView === 'query' && (
        <>
          <div
            className="z-10 h-1 shrink-0 cursor-row-resize bg-[#252d3d] transition-colors hover:bg-[#4f8ef7]"
            onMouseDown={startVDrag}
          />
          <div style={{ height: `${resultsH}%` }} className="shrink-0 overflow-hidden border-[#252d3d] border-t">
            <ResultsPanel
              rows={result?.rows ?? []}
              columns={result?.columns ?? []}
              rowCount={result?.rowCount ?? 0}
              durationMs={result?.durationMs ?? 0}
              error={result?.error ?? null}
              warnings={result?.warnings ?? validation.warnings}
              isLoading={isRunning}
              isIdle={isIdle}
              shape={result?.shape}
            />
          </div>
        </>
      )}
    </div>
  );
}
