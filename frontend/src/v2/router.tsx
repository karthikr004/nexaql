import { Navigate, type RouteObject } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import HomeRedirect from './components/HomeRedirect';
import ChatPage from './pages/ChatPage';
import DomainsPage from './pages/DomainsPage';
import ConnectorsPage from './pages/ConnectorsPage';
import LoginPage from './pages/LoginPage';
import PlaygroundPage from './pages/PlaygroundPage';
import SetupPage from './pages/SetupPage';
import SettingsPage from './pages/SettingsPage';
import UsersPage from './pages/UsersPage';

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'domains', element: <DomainsPage /> },
      { path: 'connectors', element: <ConnectorsPage /> },
      { path: 'playground', element: <PlaygroundPage /> },
      { path: 'setup', element: <SetupPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'users', element: <UsersPage /> },
    ],
  },
  { path: '/v2', element: <Navigate to="/" replace /> },
  { path: '/v2/*', element: <V2Redirect /> },
];

function V2Redirect() {
  const path = window.location.pathname.replace(/^\/v2/, '') || '/';
  return <Navigate to={path} replace />;
}
