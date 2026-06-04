import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { useTheme } from '../ThemeContext';
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
const AdminView = lazy(() => import('./AdminView'));

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
  const { theme, toggle } = useTheme();
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

  // Top-level view: playground or admin
  const [view, setView] = useState<'playground' | 'admin'>('playground');

  // Role switcher for access control testing
  const [activeRole, setActiveRole] = useState<string>('anonymous');

  const ROLE_CONFIGS: Record<string, { label: string; roles: string[]; user_id: string; attributes: Record<string, string> }> = {
    anonymous: { label: '👤 Anonymous', roles: [], user_id: 'anonymous', attributes: {} },
    analyst: { label: '🔍 Analyst (bob)', roles: ['analyst'], user_id: 'bob', attributes: {
      name: 'Bob Smith', email: 'bob@company.com', manager_id: 'mgr-east', region: 'US-EAST',
      department: 'Engineering', team_id: 'eng-platform', level: 'L4', job_role: 'Software Engineer'
    }},
    'manager-east': { label: '🔒 Manager (alice, US-EAST)', roles: ['manager'], user_id: 'alice', attributes: {
      name: 'Alice Johnson', email: 'alice@company.com', manager_id: 'mgr-east', region: 'US-EAST',
      department: 'Engineering', team_id: 'eng-platform', level: 'L6', job_role: 'Engineering Manager'
    }},
    'manager-west': { label: '🔒 Manager (carol, US-WEST)', roles: ['manager'], user_id: 'carol', attributes: {
      name: 'Carol Williams', email: 'carol@company.com', manager_id: 'mgr-west', region: 'US-WEST',
      department: 'Sales', team_id: 'sales-west', level: 'L6', job_role: 'Sales Manager'
    }},
    'manager-eu': { label: '🔒 Manager (emma, EU)', roles: ['manager'], user_id: 'emma', attributes: {
      name: 'Emma Davis', email: 'emma@company.com', manager_id: 'mgr-eu', region: 'EU',
      department: 'Operations', team_id: 'ops-eu', level: 'L6', job_role: 'Operations Manager'
    }},
    admin: { label: '⚡ Admin (full access)', roles: ['admin'], user_id: 'admin', attributes: {} },
  };

  const userContextHeaders = (): Record<string, string> => {
    const cfg = ROLE_CONFIGS[activeRole];
    if (!cfg) return {};
    return {
      'X-User-Context': JSON.stringify({
        user_id: cfg.user_id,
        roles: cfg.roles,
        ...cfg.attributes,
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
  const fetchOntology = useCallback(() => {
    fetch('/api/ontology')
      .then((r) => r.json())
      .then((data) => {
        if (data && Array.isArray(data.nodes)) setOntology(data);
        else console.error('Ontology load failed:', data?.error ?? data);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    fetchOntology();
  }, [fetchOntology]);

  const reloadOntology = useCallback(() => {
    fetchOntology();
  }, [fetchOntology]);

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
        <span className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--success)' }}>
          <span>&#x2713;</span> Valid
        </span>
      );
    return (
      <span className="flex items-center gap-1 text-[11px] text-red-400">
        <span>&#x2717;</span> {validation.errors[0]?.slice(0, 60)}
      </span>
    );
  };

  // ── Admin view ─────────────────────────────────────────────────────────────

  if (view === 'admin') {
    return (
      <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>Loading admin...</div>}>
        <AdminView onBack={() => setView('playground')} onOntologyChanged={reloadOntology} />
      </Suspense>
    );
  }

  // ── Playground view ────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="z-20 flex shrink-0 items-center justify-between border-b px-4 py-2.5" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{'⬡'}</span>
            <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>NexaQL</span>
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>/</span>
            <span className="text-sm" style={{ color: 'var(--accent)' }}>NexaQL Playground</span>
          </div>
          {ontology && (
            <span className="rounded-full border px-2 py-0.5 text-[10px]" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
              {ontology.domain} {'·'} {ontology.nodes.length} nodes
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Role switcher */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Role</span>
            <select
              value={activeRole}
              onChange={(e) => setActiveRole(e.target.value)}
              className="rounded border px-2 py-1 text-[11px] focus:outline-none"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
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
            className="rounded border px-3 py-1.5 font-medium text-[11px] transition-colors"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
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
                  ? 'cursor-not-allowed border text-slate-400'
                  : 'border border-transparent bg-[#4f8ef7] text-white shadow-blue-900/30 shadow-lg hover:bg-[#3b7de8]'
            }`}
            style={
              !isRunning && validLoaded && !validation.valid
                ? { borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }
                : undefined
            }
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
          {/* Theme toggle */}
          <button
            type="button"
            onClick={toggle}
            className="rounded border p-1.5 transition-colors"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
          {/* Admin gear icon */}
          <button
            type="button"
            onClick={() => setView('admin')}
            className="rounded border p-1.5 transition-colors"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
            title="Settings & Admin"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── Main area ───────────────────────────────────────────────── */}
      {/* Chat mode: full height. Query mode: share height with results panel */}
      <div
        className="flex overflow-hidden"
        style={centerView === 'query' ? { height: `${100 - resultsH}%` } : { flex: '1 1 0', minHeight: 0 }}
      >
        {/* Left panel */}
        <div
          style={{ width: `${leftWidth}%`, borderColor: 'var(--border)' }}
          className="flex shrink-0 flex-col overflow-hidden border-r"
        >
          {/* Left panel tab toggle */}
          <div className="flex shrink-0 border-b" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
            {(['schema', 'history'] as const).map((v) => (
              <button
                type="button"
                key={v}
                onClick={() => setLeftView(v)}
                className={`relative flex-1 py-1.5 font-semibold text-[10px] uppercase tracking-widest transition-colors`}
                style={{ color: leftView === v ? 'var(--accent)' : 'var(--text-secondary)' }}
              >
                {v === 'schema' ? (
                  'Schema'
                ) : (
                  <span className="flex items-center justify-center gap-1">
                    History
                    {history.length > 0 && (
                      <span className="rounded-full px-1 text-[9px]" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>{history.length}</span>
                    )}
                  </span>
                )}
                {leftView === v && <span className="absolute right-0 bottom-0 left-0 h-[2px]" style={{ backgroundColor: 'var(--accent)' }} />}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-hidden">
            {leftView === 'schema' ? (
              ontology ? (
                <SchemaExplorer nodes={ontology.nodes} onInsert={handleInsert} />
              ) : (
                <div className="flex h-full items-center justify-center text-xs" style={{ color: 'var(--text-secondary)' }}>Loading schema...</div>
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
          className="z-10 w-1 shrink-0 cursor-col-resize transition-colors hover:bg-[#4f8ef7]"
          style={{ backgroundColor: 'var(--border)' }}
          onMouseDown={(e) => startHDrag('left', e)}
        />

        {/* Center: Query Editor / Chat */}
        <div style={{ width: `${centerWidth}%` }} className="flex shrink-0 flex-col overflow-hidden">
          {/* Center tab bar */}
          <div className="flex shrink-0 border-b" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
            {(['query', 'chat'] as const).map((v) => (
              <button
                type="button"
                key={v}
                onClick={() => setCenterView(v)}
                className={`relative px-4 py-1.5 font-semibold text-[10px] uppercase tracking-widest transition-colors`}
                style={{ color: centerView === v ? 'var(--accent)' : 'var(--text-secondary)' }}
              >
                {v === 'query' ? 'Query Editor' : '✦ Agent Chat'}
                {centerView === v && <span className="absolute right-0 bottom-0 left-0 h-[2px]" style={{ backgroundColor: 'var(--accent)' }} />}
              </button>
            ))}
            {centerView === 'query' && (
              <span className="ml-auto self-center pr-3 font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>nexaql</span>
            )}
          </div>

          {/* Center content */}
          <div className="flex-1 overflow-hidden">
            {centerView === 'query' ? (
              <Suspense fallback={<div className="flex h-full items-center justify-center text-xs" style={{ color: 'var(--text-secondary)' }}>Loading editor...</div>}>
                <QueryEditor
                  value={query}
                  onChange={setQuery}
                  onRun={runQuery}
                  insertText={insertText}
                  onInsertConsumed={() => setInsertText(undefined)}
                  ontologyNodes={ontology?.nodes ?? []}
                  theme={theme}
                />
              </Suspense>
            ) : (
              <AgentChat onTurnComplete={setLastChatTurn} />
            )}
          </div>
        </div>

        {/* Right resizer */}
        <div
          className="z-10 w-1 shrink-0 cursor-col-resize transition-colors hover:bg-[#4f8ef7]"
          style={{ backgroundColor: 'var(--border)' }}
          onMouseDown={(e) => startHDrag('right', e)}
        />

        {/* Right: SQL Preview or Chat Query Panel */}
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

      {/* Vertical resizer + Results panel — only shown in query mode */}
      {centerView === 'query' && (
        <>
          <div
            className="z-10 h-1 shrink-0 cursor-row-resize transition-colors hover:bg-[#4f8ef7]"
            style={{ backgroundColor: 'var(--border)' }}
            onMouseDown={startVDrag}
          />
          <div style={{ height: `${resultsH}%`, borderColor: 'var(--border)' }} className="shrink-0 overflow-hidden border-t">
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
