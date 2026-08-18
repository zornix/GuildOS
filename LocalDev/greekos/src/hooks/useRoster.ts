import { useState } from 'react';
import { INITIAL_MEMBERS } from '../data/mockData';
import { Member } from '../types';
import { ShowToast } from './useToast';

/** The roster. Members are read-only against the backend today: they join by
 *  invite (POST /api/auth/invite + setup code) and standing is derived server
 *  side, so both mutations here are local. */
export function useRoster(showToast: ShowToast) {
  const [members, setMembers] = useState<Member[]>(INITIAL_MEMBERS);

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

  return { members, setMembers, handleAddMember, handleUpdateStanding };
}
