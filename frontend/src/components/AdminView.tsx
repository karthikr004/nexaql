/**
 * AdminView — thin orchestrator that composes small admin panel components.
 *
 * Layout: header + sidebar (200px) + main content area.
 * Sidebar items: Connectors, Domains, API Keys.
 * Domain drill-down: Domains → Domain detail (schemas + roles + access) → Schema detail (nodes).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  ConnectorsPanel,
  DomainsPanel,
  ApiKeysPanel,
  Toast,
  SidebarButton,
  type ToastData,
} from './admin';
import type { ConnectorInfo } from './admin/ConnectorsPanel';

// ── Props ────────────────────────────────────────────────────────────────────

interface AdminViewProps {
  onBack: () => void;
  onOntologyChanged?: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// ── URL ↔ State helpers ─────────────────────────────────────────────────────

type SidebarItem = '__connectors__' | '__domains__' | '__api_keys__' | '__roles__' | '__policy_functions__' | string;

/** Map from URL path segment to sidebar item key */
const PATH_TO_SIDEBAR: Record<string, SidebarItem> = {
  connectors: '__connectors__',
  domains: '__domains__',
  'api-keys': '__api_keys__',
  roles: '__roles__',
  'policy-functions': '__policy_functions__',
};
const SIDEBAR_TO_PATH: Record<string, string> = Object.fromEntries(
  Object.entries(PATH_TO_SIDEBAR).map(([p, s]) => [s, p]),
);

interface AdminRoute {
  sidebar: SidebarItem | null;
  domain?: string;
  schema?: string;
  node?: string;
}

function parseAdminPath(pathname: string): AdminRoute {
  const parts = pathname.replace(/^\/admin\/?/, '').split('/').filter(Boolean);
  if (parts.length === 0) return { sidebar: '__domains__' };

  const seg0 = parts[0] as string;
  const seg1 = parts[1] as string | undefined;
  const seg2 = parts[2] as string | undefined;
  const seg3 = parts[3] as string | undefined;

  // /admin/connectors, /admin/api-keys, /admin/roles, /admin/policy-functions
  const mapped = PATH_TO_SIDEBAR[seg0];
  if (mapped && mapped !== '__domains__') return { sidebar: mapped };
  // /admin/domains
  if (seg0 === 'domains') {
    if (!seg1) return { sidebar: '__domains__' };
    const domain = decodeURIComponent(seg1);
    // /admin/domains/:domain/schemas/:schema
    if (seg2 === 'schemas' && seg3) {
      return { sidebar: '__domains__', domain, schema: decodeURIComponent(seg3) };
    }
    return { sidebar: '__domains__', domain };
  }
  // /admin/nodes/:node
  if (seg0 === 'nodes' && seg1) {
    const node = decodeURIComponent(seg1);
    return { sidebar: node, node };
  }
  return { sidebar: '__domains__' };
}

function buildAdminPath(item: SidebarItem | null, domain?: string | null, schema?: string | null): string {
  if (!item) return '/admin';
  // Special sidebar items
  const seg = SIDEBAR_TO_PATH[item];
  if (seg && item !== '__domains__') return `/admin/${seg}`;
  // Domains navigation
  if (item === '__domains__') {
    if (domain && schema) return `/admin/domains/${encodeURIComponent(domain)}/schemas/${encodeURIComponent(schema)}`;
    if (domain) return `/admin/domains/${encodeURIComponent(domain)}`;
    return '/admin/domains';
  }
  // Node item — it's a node name string
  return `/admin/nodes/${encodeURIComponent(item)}`;
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function AdminView({ onBack, onOntologyChanged }: AdminViewProps) {
  // ── URL-derived initial state ───────────────────────────────────────────
  const initialRoute = useRef(parseAdminPath(window.location.pathname));

  // ── Core state ──────────────────────────────────────────────────────────
  const [toast, setToast] = useState<ToastData | null>(null);

  // ── Sidebar state ───────────────────────────────────────────────────────
  const [selectedItem, setSelectedItem] = useState<SidebarItem | null>(initialRoute.current.sidebar);

  // ── Connectors (lifted for sidebar badge count) ─────────────────────────
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [connectorsLoading, setConnectorsLoading] = useState(false);

  const fetchConnectors = useCallback(async () => {
    setConnectorsLoading(true);
    try {
      const res = await fetch('/api/connectors');
      if (res.ok) setConnectors((await res.json()).connectors ?? []);
    } catch { /* ignore */ } finally { setConnectorsLoading(false); }
  }, []);

  useEffect(() => { fetchConnectors(); }, [fetchConnectors]);

  // ── URL navigation helper ──────────────────────────────────────────────
  const pushingRef = useRef(false);  // prevent popstate echo
  const navigateAdmin = useCallback((item: SidebarItem | null, domain?: string | null, schema?: string | null) => {
    setSelectedItem(item);
    const path = buildAdminPath(item, domain, schema);
    if (window.location.pathname !== path) {
      pushingRef.current = true;
      window.history.pushState(null, '', path);
      // Reset flag after microtask
      queueMicrotask(() => { pushingRef.current = false; });
    }
  }, []);

  // Listen for browser back/forward
  useEffect(() => {
    const onPopState = () => {
      if (pushingRef.current) return;
      const route = parseAdminPath(window.location.pathname);
      setSelectedItem(route.sidebar);
      // Domain/schema routing is handled by DomainsPanel via the URL
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  // ── Helpers ─────────────────────────────────────────────────────────────
  const showToast = useCallback((t: ToastData) => setToast(t), []);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}

      {/* Header */}
      <header className="z-20 flex shrink-0 items-center justify-between border-b px-4 py-2.5" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}>
        <button type="button" onClick={onBack} className="flex items-center gap-1 text-sm transition-colors" style={{ color: 'var(--accent)' }}>&larr; Back to Playground</button>
        <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>NexaQL Admin</span>
        <div />
      </header>

      {/* Body: sidebar + content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar — Connectors, Domains, API Keys only */}
        <div className="flex w-[200px] shrink-0 flex-col border-r" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
          <SidebarButton label="Connectors" icon="&#x1F50C;" active={selectedItem === '__connectors__'} accentColor="var(--accent)" badge={connectors.length}
            onClick={() => { navigateAdmin('__connectors__'); fetchConnectors(); }} />
          <SidebarButton label="Domains" icon="&#x1F310;" active={selectedItem === '__domains__'} accentColor="var(--badge-green-text)"
            onClick={() => { navigateAdmin('__domains__'); }} />
          <SidebarButton label="API Keys" icon="&#x1F511;" active={selectedItem === '__api_keys__'} accentColor="var(--badge-amber-text)"
            onClick={() => navigateAdmin('__api_keys__')} />
        </div>

        {/* Main content area */}
        <div className="flex flex-1 flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
          {selectedItem === '__connectors__' ? (
            <ConnectorsPanel connectors={connectors} loading={connectorsLoading} onRefresh={fetchConnectors} onToast={showToast} />
          ) : selectedItem === '__domains__' ? (
            <DomainsPanel
              onToast={showToast}
              onOntologyChanged={onOntologyChanged}
              onNavigate={(domain, schema) => navigateAdmin('__domains__', domain, schema)}
              initialDomain={initialRoute.current.domain}
              initialSchema={initialRoute.current.schema}
            />
          ) : selectedItem === '__api_keys__' ? (
            <ApiKeysPanel onToast={showToast} />
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center">
                <div className="mb-3 text-3xl" style={{ color: 'var(--text-muted)' }}>&#x2699;</div>
                <p className="mb-1 text-sm" style={{ color: 'var(--text-secondary)' }}>NexaQL Admin</p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Select an item from the sidebar.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

