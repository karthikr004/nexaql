import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { useDomain } from '../contexts/DomainContext';
import { useTheme } from '../../ThemeContext';
import type {
  OntologySummary,
  ExecuteResult,
  ValidationState,
  HistoryEntry,
} from '../../types';
import Drawer from '../components/Drawer';
import SchemaExplorer from '../components/SchemaExplorer';
import HistoryPanel from '../components/HistoryPanel';
import ResultsPanel from '../components/ResultsPanel';
import SQLPreview from '../components/SQLPreview';

const V2QueryEditor = lazy(() => import('../components/V2QueryEditor'));

const HISTORY_KEY = 'nexaql-v2-query-history';
const MAX_HISTORY = 50;

const WELCOME_QUERY = `# Welcome to NexaQL Playground
# Write NexaQL queries and execute them against your data.
#
# Try: select an example above, or start typing below.
# Cmd+Enter to run  ·  click field names to insert
`;

const ROLE_CONFIGS: Record<string, { label: string; roles: string[]; user_id: string; attributes: Record<string, string> }> = {
  anonymous: { label: 'Anonymous', roles: [], user_id: 'anonymous', attributes: {} },
  analyst: { label: 'Analyst (bob)', roles: ['analyst'], user_id: 'bob', attributes: {
    name: 'Bob Smith', email: 'bob@company.com', manager_id: 'mgr-east', region: 'US-EAST',
    department: 'Engineering', team_id: 'eng-platform', level: 'L4', job_role: 'Software Engineer',
  }},
  manager: { label: 'Manager (alice)', roles: ['manager'], user_id: 'alice', attributes: {
    name: 'Alice Johnson', email: 'alice@company.com', manager_id: 'mgr-east', region: 'US-EAST',
    department: 'Engineering', team_id: 'eng-platform', level: 'L6', job_role: 'Engineering Manager',
  }},
  admin: { label: 'Admin (full)', roles: ['admin'], user_id: 'admin', attributes: {} },
};

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

function saveHistory(entries: HistoryEntry[]): void {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
  } catch { /* ignore */ }
}

export default function PlaygroundPage() {
  const { activeDomain } = useDomain();
  const { theme } = useTheme();
  const [query, setQuery] = useState(WELCOME_QUERY);
  const initialQuerySet = useRef(false);
  const [insertText, setInsertText] = useState<string | undefined>(undefined);
  const [ontology, setOntology] = useState<OntologySummary | null>(null);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [validation, setValidation] = useState<ValidationState>({ valid: false, errors: [], warnings: [] });
  const [validLoaded, setValidLoaded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isIdle, setIsIdle] = useState(true);
  const [activeRole, setActiveRole] = useState('anonymous');
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const [drawerOpen, setDrawerOpen] = useState<'schema' | 'history' | null>(null);
  const [showSQL, setShowSQL] = useState(false);
  const [editorWidth, setEditorWidth] = useState(50);
  const dragRef = useRef<{ startX: number; startVal: number } | null>(null);

  useEffect(() => { setHistory(loadHistory()); }, []);

  const fetchOntology = useCallback(() => {
    fetch('/api/ontology', { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        if (data && Array.isArray(data.nodes)) setOntology(data);
      })
      .catch(() => {});
  }, []);

  useEffect(() => { fetchOntology(); }, [fetchOntology]);

  useEffect(() => {
    const first = ontology?.examples?.[0];
    if (first && !initialQuerySet.current) {
      initialQuerySet.current = true;
      setQuery(first.query);
    }
  }, [ontology]);

  const userContextHeaders = useCallback((): Record<string, string> => {
    const cfg = ROLE_CONFIGS[activeRole];
    if (!cfg) return {};
    return {
      'X-User-Context': JSON.stringify({
        user_id: cfg.user_id,
        roles: cfg.roles,
        ...cfg.attributes,
      }),
    };
  }, [activeRole]);

  const prevRoleRef = useRef(activeRole);
  useEffect(() => {
    if (prevRoleRef.current !== activeRole) {
      prevRoleRef.current = activeRole;
      setResult(null);
      setValidLoaded(false);
      setIsIdle(true);
    }
  }, [activeRole]);

  const validateSeqRef = useRef(0);
  useEffect(() => {
    const seq = ++validateSeqRef.current;
    const t = setTimeout(() => {
      if (!query.trim()) return;
      fetch('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...userContextHeaders() },
        body: JSON.stringify({ query }),
        credentials: 'include',
      })
        .then((r) => r.json())
        .then((v) => {
          if (seq === validateSeqRef.current) {
            setValidation(v);
            setValidLoaded(true);
          }
        })
        .catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [query, activeRole, userContextHeaders]);

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
        credentials: 'include',
      });
      const data: ExecuteResult = await res.json();
      setResult(data);
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
  }, [query, isRunning, userContextHeaders, addToHistory]);

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startVal: editorWidth };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const containerEl = document.getElementById('pg-split-container');
      if (!containerEl) return;
      const rect = containerEl.getBoundingClientRect();
      const delta = ((ev.clientX - dragRef.current.startX) / rect.width) * 100;
      setEditorWidth(Math.min(70, Math.max(30, dragRef.current.startVal + delta)));
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const examples = ontology?.examples ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, height: '100%', background: 'var(--v2-bg-app)', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', borderBottom: '1px solid var(--v2-border)',
        background: 'var(--v2-bg-surface)', flexShrink: 0, gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="v2-heading-sm">Playground</span>
          {activeDomain && <span className="v2-badge v2-badge-purple">{activeDomain}</span>}
          <div style={{ width: 1, height: 20, background: 'var(--v2-border)', margin: '0 2px' }} />

          <ToolbarToggle
            active={drawerOpen === 'schema'}
            onClick={() => setDrawerOpen(drawerOpen === 'schema' ? null : 'schema')}
            icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" /></svg>}
            label="Schema"
          />

          <ToolbarToggle
            active={drawerOpen === 'history'}
            onClick={() => setDrawerOpen(drawerOpen === 'history' ? null : 'history')}
            icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>}
            label="History"
            badge={history.length > 0 ? history.length : undefined}
          />

          <ToolbarToggle
            active={showSQL}
            onClick={() => setShowSQL((v) => !v)}
            icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></svg>}
            label="SQL"
          />

          {validLoaded && (
            validation.valid
              ? <span style={{ fontSize: 11, color: 'var(--v2-teal-500)', display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  Valid
                </span>
              : <span style={{ fontSize: 11, color: 'var(--v2-red-500)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginLeft: 4 }}>
                  {validation.errors[0]?.slice(0, 50)}
                </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>Role:</span>
            <select
              value={activeRole}
              onChange={(e) => setActiveRole(e.target.value)}
              style={{
                appearance: 'none', background: 'var(--v2-bg-input)', border: '1px solid var(--v2-border)',
                borderRadius: 'var(--v2-radius-sm)', padding: '4px 24px 4px 8px', fontSize: 12,
                color: 'var(--v2-text-primary)', cursor: 'pointer', outline: 'none',
                backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%236B7280' stroke-width='2'%3e%3cpolyline points='6 9 12 15 18 9'/%3e%3c/svg%3e")`,
                backgroundRepeat: 'no-repeat', backgroundPosition: 'right 6px center',
              }}
            >
              {Object.entries(ROLE_CONFIGS).map(([key, cfg]) => (
                <option key={key} value={key}>{cfg.label}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={runQuery}
            disabled={isRunning || !query.trim()}
            className="v2-btn v2-btn-primary v2-btn-sm"
            style={{ gap: 4, opacity: isRunning || !query.trim() ? 0.5 : 1 }}
          >
            {isRunning ? (
              <div style={{
                width: 12, height: 12, borderRadius: '50%',
                border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white',
                animation: 'v2-spin 0.8s linear infinite',
              }} />
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3" /></svg>
            )}
            {isRunning ? 'Running...' : 'Run'}
          </button>
        </div>
      </div>

      {/* Examples bar */}
      {examples.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 16px', borderBottom: '1px solid var(--v2-border)',
          background: 'var(--v2-bg-app)', flexShrink: 0, overflowX: 'auto',
        }}>
          <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', flexShrink: 0, fontWeight: 500 }}>Examples</span>
          {examples.map((ex, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setQuery(ex.query)}
              style={{
                background: 'var(--v2-bg-surface)',
                border: '1px solid var(--v2-border)',
                borderRadius: 'var(--v2-radius-sm)',
                padding: '4px 10px', fontSize: 12, fontWeight: 500,
                color: 'var(--v2-text-secondary)', cursor: 'pointer',
                whiteSpace: 'nowrap', transition: 'all 0.15s ease', flexShrink: 0,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--v2-accent)';
                e.currentTarget.style.color = 'var(--v2-accent)';
                e.currentTarget.style.background = 'var(--v2-accent-subtle)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--v2-border)';
                e.currentTarget.style.color = 'var(--v2-text-secondary)';
                e.currentTarget.style.background = 'var(--v2-bg-surface)';
              }}
            >
              {ex.name}
            </button>
          ))}
        </div>
      )}

      {/* Two-pane split: Editor | Results */}
      <div id="pg-split-container" style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ width: `${editorWidth}%`, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <Suspense fallback={
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                Loading editor...
              </div>
            }>
              <V2QueryEditor
                value={query}
                onChange={setQuery}
                onRun={runQuery}
                insertText={insertText}
                onInsertConsumed={() => setInsertText(undefined)}
                ontologyNodes={ontology?.nodes ?? []}
                theme={theme}
              />
            </Suspense>
          </div>

          {showSQL && (
            <SQLPreview
              queryPreview={validation.queryPreview ?? result?.queryPreview ?? null}
              adapterType={validation.adapterType ?? result?.adapterType ?? null}
              isLoading={isRunning}
              onClose={() => setShowSQL(false)}
            />
          )}

          <div
            style={{ position: 'absolute', top: 0, right: -2, bottom: 0, width: 4, cursor: 'col-resize', zIndex: 10 }}
            onMouseDown={startDrag}
          />
        </div>

        <div style={{ width: `${100 - editorWidth}%`, minWidth: 0, overflow: 'hidden' }}>
          <ResultsPanel result={result} isRunning={isRunning} isIdle={isIdle} />
        </div>
      </div>

      {/* Drawers */}
      <Drawer open={drawerOpen === 'schema'} onClose={() => setDrawerOpen(null)} title="Schema Explorer">
        {ontology ? (
          <SchemaExplorer nodes={ontology.nodes} onInsert={(text) => { setInsertText(text); setDrawerOpen(null); }} />
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
            Loading schema...
          </div>
        )}
      </Drawer>

      <Drawer open={drawerOpen === 'history'} onClose={() => setDrawerOpen(null)} title="Query History">
        <HistoryPanel
          history={history}
          onLoad={(q) => { setQuery(q); setDrawerOpen(null); }}
          onDelete={(id) => {
            setHistory((prev) => {
              const next = prev.filter((h) => h.id !== id);
              saveHistory(next);
              return next;
            });
          }}
          onClear={() => { setHistory([]); saveHistory([]); }}
        />
      </Drawer>
    </div>
  );
}

interface ToolbarToggleProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: number;
}

function ToolbarToggle({ active, onClick, icon, label, badge }: ToolbarToggleProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: active ? 'var(--v2-accent-subtle)' : 'none',
        border: '1px solid transparent',
        borderColor: active ? 'var(--v2-accent)' : 'transparent',
        borderRadius: 'var(--v2-radius-sm)',
        cursor: 'pointer', padding: '4px 8px', display: 'flex', alignItems: 'center', gap: 4,
        color: active ? 'var(--v2-accent)' : 'var(--v2-text-secondary)',
        fontSize: 12, fontWeight: 500,
      }}
    >
      {icon}
      {label}
      {badge !== undefined && (
        <span style={{
          background: 'var(--v2-accent)', color: 'white', borderRadius: 999,
          fontSize: 9, fontWeight: 600, padding: '1px 5px', minWidth: 16, textAlign: 'center',
        }}>
          {badge}
        </span>
      )}
    </button>
  );
}
