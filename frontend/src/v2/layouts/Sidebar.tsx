import { useLocation, useNavigate } from 'react-router-dom';
import { useDomain } from '../contexts/DomainContext';

interface NavItem {
  icon: string;
  label: string;
  path: string;
  badge?: boolean;
}

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { domains } = useDomain();

  const showWizardBadge = domains.length === 0;

  const navItems: NavItem[] = [
    { icon: 'chat', label: 'Chat', path: '/v2/chat' },
    { icon: 'database', label: 'Domains', path: '/v2/domains' },
    { icon: 'plug', label: 'Connectors', path: '/v2/connectors' },
    { icon: 'code', label: 'Playground', path: '/v2/playground' },
    { icon: 'wand', label: 'Setup', path: '/v2/setup', badge: showWizardBadge },
  ];

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <aside className="v2-sidebar">
      <div className="v2-sidebar-logo" onClick={() => navigate('/v2/chat')} title="NexaQL">
        <span>N</span>
      </div>

      <nav className="v2-sidebar-nav">
        {navItems.map((item) => (
          <button
            key={item.path}
            className={`v2-sidebar-item ${isActive(item.path) ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
            title={item.label}
          >
            <SidebarIcon name={item.icon} />
            {item.badge && <span className="v2-sidebar-badge" />}
          </button>
        ))}
      </nav>

      <div className="v2-sidebar-spacer" />

      <button
        className={`v2-sidebar-item ${isActive('/v2/settings') ? 'active' : ''}`}
        onClick={() => navigate('/v2/settings')}
        title="Settings"
      >
        <SidebarIcon name="settings" />
      </button>
    </aside>
  );
}

function SidebarIcon({ name }: { name: string }) {
  const icons: Record<string, JSX.Element> = {
    chat: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
    database: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5V19A9 3 0 0 0 21 19V5" />
        <path d="M3 12A9 3 0 0 0 21 12" />
      </svg>
    ),
    plug: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22v-5" /><path d="M9 8V2" /><path d="M15 8V2" />
        <path d="M18 8v5a6 6 0 0 1-12 0V8z" />
      </svg>
    ),
    code: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" />
      </svg>
    ),
    wand: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="m15 4-1 1 5 5 1-1a2.83 2.83 0 1 0-4-4l-1 1Z" />
        <path d="m13 6-8.5 8.5a2.12 2.12 0 1 0 3 3L16 9" />
        <path d="m2 2 20 20" />
      </svg>
    ),
    settings: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
  };

  return icons[name] || null;
}
