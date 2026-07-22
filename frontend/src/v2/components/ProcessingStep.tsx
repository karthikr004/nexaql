import { useState } from 'react';

interface Props {
  label: string;
  icon: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string;
  badgeVariant?: 'purple' | 'teal' | 'amber' | 'gray';
}

export default function ProcessingStep({ label, icon, children, defaultOpen = false, badge, badgeVariant = 'gray' }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      style={{
        border: '1px solid var(--v2-border-light)',
        borderRadius: 'var(--v2-radius-md)',
        overflow: 'hidden',
        background: 'var(--v2-bg-surface)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          width: '100%',
          padding: '8px 12px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontFamily: 'var(--v2-font-sans)',
          fontSize: 12,
          fontWeight: 500,
          color: 'var(--v2-text-secondary)',
          transition: 'color var(--v2-transition-fast)',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--v2-text-primary)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--v2-text-secondary)'; }}
      >
        <span style={{ fontSize: 13, width: 18, textAlign: 'center', flexShrink: 0 }}>{icon}</span>
        <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>
        {badge && (
          <span className={`v2-badge v2-badge-${badgeVariant}`} style={{ fontSize: 10 }}>{badge}</span>
        )}
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform var(--v2-transition-fast)',
            flexShrink: 0,
          }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div
          style={{
            padding: '0 12px 10px',
            borderTop: '1px solid var(--v2-border-light)',
          }}
        >
          <div style={{ paddingTop: 10 }}>
            {children}
          </div>
        </div>
      )}
    </div>
  );
}
