import { useState, useCallback, useEffect } from 'react';

interface User {
  id: number;
  email: string;
  name: string | null;
  avatar_url: string | null;
  oauth_provider: string;
  roles: string[];
  is_active: boolean;
  last_login_at: string | null;
}

interface Toast {
  message: string;
  type: 'success' | 'error' | 'info';
}

interface UserListProps {
  showToast: (t: Toast) => void;
}

export default function UserList({ showToast }: UserListProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/users', { credentials: 'include' });
      if (res.ok) {
        setUsers(await res.json());
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleToggleActive = useCallback(async (user: User) => {
    try {
      const res = await fetch(`/api/admin/users/${user.id}/active`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !user.is_active }),
        credentials: 'include',
      });
      if (res.ok) {
        showToast({ message: `${user.email} ${user.is_active ? 'deactivated' : 'activated'}`, type: 'success' });
        fetchUsers();
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    }
  }, [fetchUsers, showToast]);

  if (loading) {
    return (
      <div style={{ marginBottom: 32 }}>
        <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Users</h2>
        <div className="v2-card" style={{ padding: 24, textAlign: 'center' }}>
          <p className="v2-body-sm">Loading...</p>
        </div>
      </div>
    );
  }

  if (users.length === 0) {
    return (
      <div style={{ marginBottom: 32 }}>
        <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>Users</h2>
        <div className="v2-card" style={{ textAlign: 'center', padding: '40px 24px' }}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <p className="v2-heading-sm" style={{ marginBottom: 4 }}>No users yet</p>
          <p className="v2-body-sm">Users appear here after they sign in via OAuth</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 32 }}>
      <h2 className="v2-heading-md" style={{ marginBottom: 16 }}>
        Users <span style={{ fontWeight: 400, fontSize: 13, color: 'var(--v2-text-tertiary)' }}>({users.length})</span>
      </h2>
      <div className="v2-card">
        <table className="v2-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Provider</th>
              <th>Roles</th>
              <th>Last Login</th>
              <th style={{ textAlign: 'right' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {u.avatar_url ? (
                      <img
                        src={u.avatar_url}
                        alt=""
                        style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }}
                      />
                    ) : (
                      <div style={{
                        width: 28, height: 28, borderRadius: '50%',
                        background: 'var(--v2-purple-100)', color: 'var(--v2-purple-700)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 600,
                      }}>
                        {(u.name ?? u.email).charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{u.name ?? 'Unknown'}</div>
                      <div style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>{u.email}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <span className="v2-badge v2-badge-teal">{u.oauth_provider}</span>
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {u.roles.length > 0 ? u.roles.map((r) => (
                      <span
                        key={r}
                        style={{
                          padding: '1px 6px', fontSize: 11, fontWeight: 500,
                          borderRadius: 'var(--v2-radius-full)',
                          background: r === 'admin' ? 'var(--v2-purple-50)' : 'var(--v2-bg-surface)',
                          color: r === 'admin' ? 'var(--v2-purple-700)' : 'var(--v2-text-secondary)',
                        }}
                      >
                        {r}
                      </span>
                    )) : (
                      <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>none</span>
                    )}
                  </div>
                </td>
                <td>
                  <span style={{ fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'Never'}
                  </span>
                </td>
                <td>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      className="v2-btn v2-btn-ghost v2-btn-sm"
                      onClick={() => handleToggleActive(u)}
                      style={{ color: u.is_active ? 'var(--v2-red-500)' : 'var(--v2-teal-600)', fontSize: 12 }}
                    >
                      {u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
