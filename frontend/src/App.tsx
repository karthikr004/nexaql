import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { ThemeProvider } from './ThemeContext';
import { DomainProvider } from './v2/contexts/DomainContext';
import { v2Routes } from './v2/router';
import Playground from './components/Playground';

function AppRoutes() {
  const location = useLocation();

  if (location.pathname.startsWith('/v2')) {
    return (
      <DomainProvider>
        <Routes>
          {v2Routes.map((route) => (
            <Route key={route.path} path={route.path} element={route.element}>
              {route.children?.map((child) => (
                <Route
                  key={child.path || 'index'}
                  index={child.index}
                  path={child.path}
                  element={child.element}
                />
              ))}
            </Route>
          ))}
        </Routes>
      </DomainProvider>
    );
  }

  return <Playground />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AppRoutes />
      </ThemeProvider>
    </BrowserRouter>
  );
}
