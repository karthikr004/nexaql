import { useEffect } from 'react';

export interface ToastData {
  message: string;
  type: 'success' | 'error';
}

interface ToastProps extends ToastData {
  onDismiss: () => void;
}

export default function Toast({ message, type, onDismiss }: ToastProps) {
  useEffect(() => {
    const duration = type === 'error' ? 8000 : 3500;
    const t = setTimeout(onDismiss, duration);
    return () => clearTimeout(t);
  }, [onDismiss, type]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 16,
        right: 16,
        zIndex: 50,
        maxWidth: 400,
        padding: '10px 16px',
        borderRadius: 'var(--v2-radius-md)',
        border: '1px solid',
        borderColor: type === 'success' ? 'var(--v2-teal-500)' : 'var(--v2-red-500)',
        background: type === 'success' ? 'var(--v2-teal-50)' : 'var(--v2-red-50)',
        color: type === 'success' ? 'var(--v2-teal-700)' : 'var(--v2-red-700)',
        fontSize: 13,
        fontFamily: 'var(--v2-font-sans)',
        boxShadow: 'var(--v2-shadow-md)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span style={{ flex: 1, whiteSpace: 'pre-wrap' }}>{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: 14,
          opacity: 0.6,
          color: 'inherit',
        }}
      >
        &#x2715;
      </button>
    </div>
  );
}
