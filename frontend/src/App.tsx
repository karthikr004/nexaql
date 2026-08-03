import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './ThemeContext';
import { AuthProvider } from './v2/contexts/AuthContext';
import { DomainProvider } from './v2/contexts/DomainContext';
import { routes } from './v2/router';

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <DomainProvider>
            <Routes>
              {routes.map((route) => (
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
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
