import { useState, useRef, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import type { AuthUser, AuthMode } from '../types/auth';

interface UserMenuProps {
  user: AuthUser;
  authMode: AuthMode;
}

function getInitials(name: string | null, email: string): string {
  if (name) {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    const first = parts[0] ?? '';
    const last = parts.length >= 2 ? (parts[parts.length - 1] ?? '') : '';
    if (last) return (first.charAt(0) + last.charAt(0)).toUpperCase();
    if (first) return first.charAt(0).toUpperCase();
  }
  return email.charAt(0).toUpperCase();
}

export default function UserMenu({ user, authMode }: UserMenuProps) {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  if (authMode === 'dev') {
    return (
      <span className="v2-user-dev-badge">DEV</span>
    );
  }

  const initials = getInitials(user.name, user.email);

  return (
    <div className="v2-user-menu" ref={ref}>
      <button
        className="v2-user-avatar-btn"
        onClick={() => setOpen(!open)}
        title={user.name ?? user.email}
      >
        {user.avatarUrl ? (
          <img
            src={user.avatarUrl}
            alt=""
            className="v2-user-avatar-img"
          />
        ) : (
          <span className="v2-user-avatar-initials">{initials}</span>
        )}
      </button>

      {open && (
        <div className="v2-user-dropdown">
          <div className="v2-user-dropdown-header">
            <div className="v2-user-dropdown-name">{user.name ?? 'User'}</div>
            <div className="v2-user-dropdown-email">{user.email}</div>
            {user.roles.length > 0 && (
              <div className="v2-user-dropdown-roles">
                {user.roles.map((role) => (
                  <span key={role} className="v2-user-role-badge">{role}</span>
                ))}
              </div>
            )}
          </div>
          <div className="v2-user-dropdown-divider" />
          <button
            className="v2-user-dropdown-item"
            onClick={() => { setOpen(false); logout(); }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
