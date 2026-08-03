import { Outlet, Navigate, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import { useAuth } from '../contexts/AuthContext';
import '../styles/design-system.css';
import '../styles/layout.css';

const VIEW_TITLES: Record<string, string> = {
  '/chat': 'Chat',
  '/domains': 'Domains & schemas',
  '/connectors': 'Connectors',
  '/playground': 'Query playground',
  '/setup': 'Setup wizard',
  '/settings': 'Settings',
};

export default function AppShell() {
  const location = useLocation();
  const { user, loading, authMode } = useAuth();

  if (authMode === 'oauth' && !loading && !user) {
    return <Navigate to="/login" replace />;
  }

  let title = 'NexaQL';
  for (const [path, label] of Object.entries(VIEW_TITLES)) {
    if (location.pathname.startsWith(path)) {
      title = label;
      break;
    }
  }

  return (
    <div className="v2-shell">
      <Sidebar />
      <div className="v2-main">
        <TopBar title={title} />
        <div className="v2-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
