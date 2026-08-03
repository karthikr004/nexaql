import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

const SYSTEM_ROLES = [
  { value: 'admin', label: 'Admin', description: 'Full access' },
  { value: 'analyst', label: 'Analyst', description: 'Query & view' },
  { value: 'viewer', label: 'Viewer', description: 'Read-only' },
] as const;

interface RoleEditorProps {
  userId: number;
  currentRoles: string[];
  onSave: (userId: number, roles: string[]) => Promise<void>;
  disabled?: boolean;
}

export default function RoleEditor({ userId, currentRoles, onSave, disabled }: RoleEditorProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(currentRoles[0] ?? '');
  const [saving, setSaving] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setSelected(currentRoles[0] ?? '');

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
  }, [open, currentRoles]);

  const getDropdownStyle = useCallback((): React.CSSProperties => {
    if (!triggerRef.current) return { position: 'fixed', top: 0, left: 0 };
    const rect = triggerRef.current.getBoundingClientRect();
    const dropdownHeight = 180;
    const spaceBelow = window.innerHeight - rect.bottom;
    const top = spaceBelow < dropdownHeight
      ? rect.top - dropdownHeight
      : rect.bottom + 4;

    return { position: 'fixed', top, left: rect.left };
  }, []);

  const handleSave = async () => {
    if (selected === (currentRoles[0] ?? '')) return;
    setSaving(true);
    try {
      await onSave(userId, selected ? [selected] : []);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  const currentRole = currentRoles[0] ?? '';
  const changed = selected !== currentRole;

  return (
    <>
      <div
        ref={triggerRef}
        className="v2-role-trigger"
        onClick={() => !disabled && setOpen(!open)}
        title={disabled ? 'Last admin — cannot change role' : 'Click to change role'}
        style={disabled ? { cursor: 'default', opacity: 0.7 } : undefined}
      >
        {currentRole ? (
          <span className={`v2-role-badge ${currentRole === 'admin' ? 'v2-role-admin' : ''}`}>
            {currentRole}
          </span>
        ) : (
          <span className="v2-role-none">no role</span>
        )}
        {!disabled && (
          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="var(--v2-text-tertiary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          >
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        )}
      </div>

      {open && createPortal(
        <div ref={dropdownRef} className="v2-role-dropdown" style={getDropdownStyle()}>
          <div className="v2-role-dropdown-header">Select role</div>
          {SYSTEM_ROLES.map((role) => (
            <label key={role.value} className="v2-role-option">
              <input
                type="radio"
                name={`role-${userId}`}
                checked={selected === role.value}
                onChange={() => setSelected(role.value)}
                className="v2-role-radio"
              />
              <span className="v2-role-option-label">{role.label}</span>
              <span className="v2-role-option-desc">{role.description}</span>
            </label>
          ))}
          <div className="v2-role-dropdown-footer">
            <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={() => setOpen(false)}>
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
        document.querySelector('.v2-shell') ?? document.body,
      )}
    </>
  );
}
