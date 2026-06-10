/**
 * Shared UI primitives and style helpers for the Admin panel.
 * Keep this file small — only truly reusable pieces belong here.
 */
import { useEffect } from 'react';

// ── Style helpers ──────────────────────────────────────────────────────────

export const inputStyle: React.CSSProperties = {
  borderColor: 'var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-primary)',
};

export const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
};

// ── Toast ──────────────────────────────────────────────────────────────────

export interface ToastData {
  message: string;
  type: 'success' | 'error';
}

export function Toast({ message, type, onDismiss }: ToastData & { onDismiss: () => void }) {
  useEffect(() => {
    const duration = type === 'error' ? 8000 : 3500;
    const t = setTimeout(onDismiss, duration);
    return () => clearTimeout(t);
  }, [onDismiss, type]);

  return (
    <div
      className={`fixed top-4 right-4 z-50 max-w-lg rounded border px-4 py-3 text-sm shadow-lg ${
        type === 'success'
          ? 'border-[#3dd68c]/40 bg-[#1a2f25] text-[#3dd68c]'
          : 'border-red-500/40 bg-[#2f1a1a] text-red-400'
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="whitespace-pre-wrap text-[12px] leading-relaxed">{message}</div>
        <button type="button" onClick={onDismiss} className="shrink-0 text-[10px] opacity-60 hover:opacity-100">
          &#x2715;
        </button>
      </div>
    </div>
  );
}

// ── Section header ─────────────────────────────────────────────────────────

export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="shrink-0 border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
      <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{title}</span>
      {subtitle && <span className="ml-2 text-[10px]" style={{ color: 'var(--text-secondary)' }}>{subtitle}</span>}
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────

export function EmptyState({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="rounded border p-6 text-center" style={{ borderColor: 'var(--border)' }}>
      <div className="mb-2 text-2xl" style={{ color: 'var(--text-muted)' }}>{icon}</div>
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{text}</p>
    </div>
  );
}

// ── Sidebar button ─────────────────────────────────────────────────────────

interface SidebarBtnProps {
  label: string;
  icon?: string;
  active: boolean;
  accentColor?: string;
  badge?: string | number;
  onClick: () => void;
}

export function SidebarButton({ label, icon, active, accentColor, badge, onClick }: SidebarBtnProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 border-b px-3 py-2.5 text-left transition-colors ${
        active ? 'border-l-2' : ''
      }`}
      style={{
        borderBottomColor: 'var(--border)',
        borderLeftColor: active ? (accentColor ?? 'var(--accent)') : 'transparent',
        backgroundColor: active ? 'var(--bg-elevated)' : 'transparent',
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'; }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.backgroundColor = 'transparent'; }}
    >
      {icon && <span style={{ fontSize: '12px' }}>{icon}</span>}
      <span className="font-semibold text-[12px]" style={{ color: accentColor ?? 'var(--accent)' }}>{label}</span>
      {badge !== undefined && (
        <span
          className="rounded px-1 py-0.5 text-[9px] border"
          style={{ backgroundColor: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          {badge}
        </span>
      )}
    </button>
  );
}
