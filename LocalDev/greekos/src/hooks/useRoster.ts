import { useState } from 'react';
import { api, RosterImportResult } from '../api';
import { Member } from '../types';
import { ShowToast } from './useToast';

/** The roster. Members are read-only against the backend today: they join by
 *  invite (POST /api/auth/invite + setup code) and standing is derived server
 *  side, so both mutations here are local. */
export function useRoster(showToast: ShowToast) {
  const [members, setMembers] = useState<Member[]>([]);

  const handleAddMember = (
    newMem: Omit<Member, 'id' | 'points' | 'attendanceRate' | 'duesBalance' | 'duesBalanceCents' | 'securityHoursServed'>
  ) => {
    const mem: Member = {
      ...newMem,
      id: 'm_' + Math.random().toString(36).substring(2, 9),
      duesBalanceCents: 95000,
      duesBalance: 950,
      attendanceRate: 100,
      securityHoursServed: 0
    };
    setMembers(prev => [mem, ...prev]);
    showToast(`Added ${mem.name} to active roster.`);
  };

  const handleUpdateStanding = (memberId: string, standing: Member['standing']) => {
    setMembers(prev => prev.map(m => m.id === memberId ? { ...m, standing } : m));
    showToast(`Updated brother academic/disciplinary standing.`);
  };

  /** CSV roster import (officer only). Throws RosterRejectedError with the
   *  offending rows when the file is rejected — nothing was imported. */
  const handleImportRoster = async (chapterId: string, file: File): Promise<RosterImportResult> => {
    const result = await api.importRoster(chapterId, file);
    showToast(
      `Invited ${result.created_count} member${result.created_count === 1 ? '' : 's'}` +
      (result.skipped_count ? `, skipped ${result.skipped_count} already on the roster.` : '.')
    );
    return result;
  };

  return { members, setMembers, handleAddMember, handleUpdateStanding, handleImportRoster };
}
