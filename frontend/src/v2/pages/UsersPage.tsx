import { useState, useCallback } from 'react';
import AuthSettings from '../components/AuthSettings';
import UserList from '../components/UserList';

interface Toast {
  message: string;
  type: 'success' | 'error' | 'info';
}

export default function UsersPage() {
  const [toast, setToast] = useState<Toast | null>(null);

  const showToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), 4000);
  }, []);

  return (
    <div style={{ padding: 32, maxWidth: 960, margin: '0 auto' }}>
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 20,
            right: 20,
            zIndex: 1000,
            padding: '10px 16px',
            borderRadius: 'var(--v2-radius-md)',
            fontSize: 13,
            fontWeight: 500,
            maxWidth: 400,
            boxShadow: 'var(--v2-shadow-md)',
            background: toast.type === 'success' ? 'var(--v2-teal-50)' : toast.type === 'error' ? 'var(--v2-red-50)' : 'var(--v2-bg-elevated)',
            color: toast.type === 'success' ? 'var(--v2-teal-700)' : toast.type === 'error' ? 'var(--v2-red-700)' : 'var(--v2-text-primary)',
            border: `1px solid ${toast.type === 'success' ? 'var(--v2-teal-500)' : toast.type === 'error' ? 'var(--v2-red-500)' : 'var(--v2-border)'}`,
          }}
        >
          {toast.message}
        </div>
      )}

      <div style={{ marginBottom: 32 }}>
        <h1 className="v2-heading-lg">Users &amp; Authentication</h1>
        <p className="v2-body-sm" style={{ marginTop: 4 }}>Manage auth mode, OAuth providers, and user access</p>
      </div>

      <AuthSettings showToast={showToast} />
      <UserList showToast={showToast} />
    </div>
  );
}
