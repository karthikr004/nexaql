import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

const SYSTEM_ROLES = ['admin', 'analyst', 'viewer'] as const;

const ROLE_DESCRIPTIONS: Record<string, string> = {
  admin: 'Full access',
  analyst: 'Query & view',
  viewer: 'Read-only',
};

interface RoleEditorProps {
  userId: number;
  currentRoles: string[];
  onSave: (userId: number, roles: string[]) => Promise<void>;
}

interface DropdownPos {
  top: number;
  left: number;
}

export default function RoleEditor({ userId, currentRoles, onSave }: RoleEditorProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(currentRoles);
  const [saving, setSaving] = useState(false);
  const [pos, setPos] = useState<DropdownPos>({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const dropdownHeight = 210;

    if (spaceBelow < dropdownHeight) {
      setPos({ top: rect.top - dropdownHeight, left: rect.left });
    } else {
      setPos({ top: rect.bottom + 4, left: rect.left });
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setSelected(currentRoles);
    updatePosition();

    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (
        triggerRef.current && !triggerRef.current.contains(target) &&
        dropdownRef.current && !dropdownRef.current.contains(target)
      ) {
        setOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open, currentRoles, updatePosition]);

  const toggle = (role: string) => {
    setSelected((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    );
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(userId, selected);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  const changed = JSON.stringify([...selected].sort()) !== JSON.stringify([...currentRoles].sort());

  return (
    <>
      <div
        ref={triggerRef}
        style={{ display: 'flex', gap: 4, flexWrap: 'wrap', cursor: 'pointer', alignItems: 'center' }}
        onClick={() => setOpen(!open)}
        title="Click to edit roles"
      >
        {currentRoles.length > 0 ? (
          currentRoles.map((r) => (
            <span key={r} className={`v2-role-badge ${r === 'admin' ? 'v2-role-admin' : ''}`}>
              {r}
            </span>
          ))
        ) : (
          <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', fontStyle: 'italic' }}>
            no roles
          </span>
        )}
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="var(--v2-text-tertiary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ flexShrink: 0 }}
        >
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
      </div>

      {open && createPortal(
        <div
          ref={dropdownRef}
          className="v2-role-dropdown"
          style={{ position: 'fixed', top: pos.top, left: pos.left }}
        >
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--v2-border)' }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--v2-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Assign roles
            </span>
          </div>
          {SYSTEM_ROLES.map((role) => (
            <label key={role} className="v2-role-option">
              <input
                type="checkbox"
                checked={selected.includes(role)}
                onChange={() => toggle(role)}
                className="v2-role-checkbox"
              />
              <span style={{ fontSize: 13, fontWeight: 500 }}>{role}</span>
              <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginLeft: 'auto' }}>
                {ROLE_DESCRIPTIONS[role]}
              </span>
            </label>
          ))}
          <div style={{ padding: '8px 12px', borderTop: '1px solid var(--v2-border)', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button
              type="button"
              className="v2-btn v2-btn-ghost v2-btn-sm"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="v2-btn v2-btn-primary v2-btn-sm"
              onClick={handleSave}
              disabled={!changed || saving}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
