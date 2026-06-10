/**
 * Roles editor — define valid roles for access control policies.
 */
import { SectionHeader, inputStyle, type ToastData } from './shared';
import type { OntologyData } from '../../types';

interface Props {
  ontology: OntologyData;
  onUpdate: (updater: (draft: OntologyData) => void) => void;
  onToast: (t: ToastData) => void;
}

export default function RolesEditor({ ontology, onUpdate }: Props) {
  const roles = ontology?.roles ?? {};
  const roleEntries = Object.entries(roles);

  return (
    <>
      <SectionHeader title="Roles" subtitle="Define valid roles for access control policies" />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          Roles defined here are the only valid role names that can be used in{' '}
          <code style={{ color: 'var(--accent)' }}>visible_to</code>,{' '}
          <code style={{ color: 'var(--accent)' }}>row_policies</code>, and other access control settings.
          The source system (IdP/auth) maps users to these roles via the{' '}
          <code style={{ color: 'var(--accent)' }}>X-User-Context</code> header.
        </p>

        {roleEntries.map(([roleName, roleDef]) => (
          <div
            key={roleName}
            className="flex items-start gap-3 rounded border p-3"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}
          >
            <div className="flex-1 space-y-2">
              <input
                defaultValue={roleName}
                key={`rn-${roleName}`}
                onBlur={(e) => {
                  const newName = e.target.value.trim();
                  if (newName && newName !== roleName) {
                    onUpdate((o) => {
                      if (!o.roles) return;
                      const def = o.roles[roleName] ?? { description: '' };
                      delete o.roles[roleName];
                      o.roles[newName] = def;
                    });
                  }
                }}
                className="rounded border px-2 py-1 font-mono text-sm font-semibold focus:outline-none"
                style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)', color: 'var(--accent)' }}
                placeholder="role_name"
              />
              <input
                defaultValue={roleDef.description}
                key={`rd-${roleName}`}
                onBlur={(e) =>
                  onUpdate((o) => {
                    if (o.roles?.[roleName]) o.roles[roleName].description = e.target.value;
                  })
                }
                className="w-full rounded border px-2 py-1 text-xs focus:outline-none"
                style={inputStyle}
                placeholder="Description"
              />
            </div>
            <button
              type="button"
              onClick={() => onUpdate((o) => { if (o.roles) delete o.roles[roleName]; })}
              className="shrink-0 text-xs hover:text-red-400"
              style={{ color: 'var(--text-secondary)' }}
              title="Delete role"
            >
              x
            </button>
          </div>
        ))}

        <button
          type="button"
          onClick={() =>
            onUpdate((o) => {
              if (!o.roles) o.roles = {};
              const name = `new_role_${Object.keys(o.roles).length + 1}`;
              o.roles[name] = { description: '' };
            })
          }
          className="rounded border px-3 py-1.5 text-[11px]"
          style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}
        >
          + Add Role
        </button>
      </div>
    </>
  );
}
