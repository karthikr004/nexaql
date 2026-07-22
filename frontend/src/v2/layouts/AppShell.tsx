import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import '../styles/design-system.css';
import '../styles/layout.css';

const VIEW_TITLES: Record<string, string> = {
  '/v2/chat': 'Chat',
  '/v2/domains': 'Domains & schemas',
  '/v2/connectors': 'Connectors',
  '/v2/playground': 'Query playground',
  '/v2/setup': 'Setup wizard',
  '/v2/settings': 'Settings',
};

export default function AppShell() {
  const location = useLocation();

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
