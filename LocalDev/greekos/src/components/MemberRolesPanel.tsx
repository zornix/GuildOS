import { useEffect, useState } from 'react';
import { api, RoleDto } from '../api';
import Modal from './ui/Modal';

/** The assigned-role keys after switching one role on or off. */
export function toggleRoleKeys(keys: string[], key: string, on: boolean): string[] {
  const without = keys.filter(k => k !== key);
  return on ? [...without, key] : without;
}

interface Props {
  memberId: string;
  memberName: string;
  onClose: () => void;
}

/** Officer-only (`roles:assign`) role toggles for one member. Writes hit
 *  POST/DELETE /api/rbac/members/{id}/roles and roll back on failure. */
export default function MemberRolesPanel({ memberId, memberName, onClose }: Props) {
  const [catalog, setCatalog] = useState<RoleDto[] | null>(null);
  const [assigned, setAssigned] = useState<string[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([api.getRoleCatalog(), api.getMemberRoles(memberId)])
      .then(([roles, mine]) => {
        if (!live) return;
        setCatalog(roles);
        setAssigned(mine.map(r => r.role_key));
      })
      .catch(err => live && setError(err instanceof Error ? err.message : String(err)));
    return () => { live = false; };
  }, [memberId]);

  const toggle = async (key: string, on: boolean) => {
    const previous = assigned;
    setAssigned(toggleRoleKeys(previous, key, on));
    setPending(key);
    setError(null);
    try {
      if (on) await api.assignMemberRole(memberId, key);
      else await api.revokeMemberRole(memberId, key);
    } catch (err) {
      setAssigned(previous);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(null);
    }
  };

  return (
    <Modal title={`Roles — ${memberName}`} onClose={onClose}>
      {error && (
        <p role="alert" className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg p-2 mb-3">
          {error}
        </p>
      )}

      {catalog === null && !error && <p className="text-xs text-slate-500">Loading roles…</p>}

      <div className="space-y-1 max-h-[60vh] overflow-y-auto">
        {(catalog || []).map(role => {
          const on = assigned.includes(role.key);
          return (
            <label
              key={role.key}
              className="flex items-center gap-3 p-2 min-h-11 rounded-lg hover:bg-slate-50 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={on}
                disabled={pending !== null}
                onChange={e => toggle(role.key, e.target.checked)}
                className="w-4 h-4 accent-navy cursor-pointer"
              />
              <span className="text-sm font-semibold text-slate-800">{role.label}</span>
              <span className="text-xs text-slate-400 font-mono ml-auto">{role.key}</span>
            </label>
          );
        })}
      </div>

      {catalog !== null && catalog.length === 0 && (
        <p className="text-xs text-slate-500">No roles in the catalog yet.</p>
      )}
    </Modal>
  );
}
