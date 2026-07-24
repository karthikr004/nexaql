import { type RouteObject } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import HomeRedirect from './components/HomeRedirect';
import ChatPage from './pages/ChatPage';
import DomainsPage from './pages/DomainsPage';
import ConnectorsPage from './pages/ConnectorsPage';
import PlaygroundPage from './pages/PlaygroundPage';
import SetupPage from './pages/SetupPage';
import SettingsPage from './pages/SettingsPage';

export const v2Routes: RouteObject[] = [
  {
    path: '/v2',
    element: <AppShell />,
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'domains', element: <DomainsPage /> },
      { path: 'connectors', element: <ConnectorsPage /> },
      { path: 'playground', element: <PlaygroundPage /> },
      { path: 'setup', element: <SetupPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];
