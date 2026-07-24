import type { ReactNode } from 'react';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

export default function Drawer({ open, onClose, title, children }: DrawerProps) {
  if (!open) return null;

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.2)', zIndex: 40,
        }}
      />
      <div style={{
        position: 'fixed', top: 0, left: 56, bottom: 0, width: 340,
        background: 'var(--v2-bg-surface)', borderRight: '1px solid var(--v2-border)',
        zIndex: 50, display: 'flex', flexDirection: 'column',
        boxShadow: '4px 0 24px rgba(0,0,0,0.12)',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--v2-text-primary)' }}>{title}</span>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--v2-text-tertiary)', padding: '2px', display: 'flex' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {children}
        </div>
      </div>
    </>
  );
}
