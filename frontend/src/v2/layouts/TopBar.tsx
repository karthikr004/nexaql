import { useState, useRef, useEffect } from 'react';
import { useTheme } from '../../ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import { useDomain } from '../contexts/DomainContext';
import UserMenu from '../components/UserMenu';

interface TopBarProps {
  title: string;
}

export default function TopBar({ title }: TopBarProps) {
  const { theme, toggle } = useTheme();
  const { user, authMode } = useAuth();
  const { domains, activeDomain, switchDomain } = useDomain();
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    }
    if (showMenu) {
      document.addEventListener('mousedown', handleClick);
    }
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showMenu]);

  return (
    <header className="v2-topbar">
      <h1 className="v2-topbar-title">{title}</h1>

      <div className="v2-topbar-spacer" />

      {domains.length > 0 && (
        <div className="v2-domain-selector" ref={menuRef}>
          <button
            className="v2-domain-trigger"
            onClick={() => setShowMenu(!showMenu)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--v2-accent)' }}>
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5V19A9 3 0 0 0 21 19V5" />
              <path d="M3 12A9 3 0 0 0 21 12" />
            </svg>
            <span>{activeDomain || 'Select domain'}</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--v2-text-tertiary)' }}>
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {showMenu && (
            <div className="v2-domain-menu">
              {domains.map((d) => (
                <button
                  key={d.name}
                  className={`v2-domain-option ${d.name === activeDomain ? 'active' : ''}`}
                  onClick={() => { switchDomain(d.name); setShowMenu(false); }}
                >
                  <span className="v2-domain-option-name">{d.name}</span>
                  {d.name === activeDomain && (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--v2-accent)' }}>
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {user && <UserMenu user={user} authMode={authMode} />}

      <button
        className="v2-icon-btn"
        onClick={toggle}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      >
        {theme === 'dark' ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2" /><path d="M12 20v2" /><path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" /><path d="M2 12h2" /><path d="M20 12h2" /><path d="m6.34 17.66-1.41 1.41" /><path d="m19.07 4.93-1.41 1.41" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
          </svg>
        )}
      </button>
    </header>
  );
}
