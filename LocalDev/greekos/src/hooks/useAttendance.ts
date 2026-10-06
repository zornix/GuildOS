import { useState, type Dispatch, type SetStateAction } from 'react';
import { ChapterEvent, Excuse, Member } from '../types';
import { serverMessage } from '../lib/sync';
import { api } from '../api';
import { adaptExcuses } from '../adapters';
import { ShowToast } from './useToast';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  setEvents: Dispatch<SetStateAction<ChapterEvent[]>>;
  refetchEvents: () => Promise<void>;
  syncApi: SyncApi;
  showToast: ShowToast;
}

/** Roll call, door-code check-in and absence excuses. Attendance is recorded onto
 *  the event rows, so this hook writes into the events state too. */
export function useAttendance({ members, setEvents, refetchEvents, syncApi, showToast }: Deps) {
  const [excuses, setExcuses] = useState<Excuse[]>([]);

  const refetchExcuses = async () => setExcuses(adaptExcuses(await api.getExcuses(), members));

  const handleRecordAttendance = (eventId: string, records: { memberId: string; status: 'Present' | 'Absent' | 'Excused' | 'Late' }[]) => {
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, attendanceTaken: true, checkedInCount: records.filter(r => r.status === 'Present').length } : e));
    syncApi(async () => {
      // Every member is attempted — one refusal must not drop the rest of the roster.
      // 'Late' still counts as showing up — the API has no late state.
      const results = await Promise.allSettled(records.map(r =>
        api.markAttendance(eventId, r.memberId, r.status === 'Absent' ? 'absent' : r.status === 'Excused' ? 'excused' : 'present')
      ));
      const failed = records.filter((_, i) => results[i].status === 'rejected');
      if (failed.length) {
        const names = failed.map(r => members.find(m => m.id === r.memberId)?.name ?? r.memberId);
        const listed = names.slice(0, 5).join(', ') + (names.length > 5 ? ` and ${names.length - 5} more` : '');
        throw new Error(`${failed.length} of ${records.length} not recorded — re-enter ${listed}.`);
      }
    }, refetchEvents, {
      onSuccess: () => showToast(`Recorded roll call attendance.`),
      onError: err => showToast(`Roll call incomplete: ${(err as Error).message}`)
    });
  };

  const handleSubmitExcuse = (excuseData: Omit<Excuse, 'id' | 'status' | 'submittedDate'>) => {
    const newExcuse: Excuse = {
      ...excuseData,
      id: 'ex_' + Math.random().toString(36).substring(2, 9),
      status: 'Pending',
      submittedAt: new Date().toISOString().replace('T', ' ').substring(0, 16)
    };
    setExcuses(prev => [newExcuse, ...prev]);
    syncApi(() => api.submitExcuse(newExcuse.eventId, newExcuse.reason), refetchExcuses, 'Excuse request submitted for executive review.');
  };

  const handleReviewExcuse = (excuseId: string, status: 'Approved' | 'Rejected', reviewedBy: string) => {
    setExcuses(prev => prev.map(e => e.id === excuseId ? { ...e, status, decidedBy: reviewedBy } : e));
    syncApi(
      () => api.reviewExcuse(excuseId, status === 'Approved' ? 'approved' : 'denied'),
      refetchExcuses,
      `Excuse marked ${status}.`
    );
  };

  /** Door-code check-in. The code identifies the event and the backend checks in
   *  the signed-in member, so neither is passed from the UI. */
  const handleSelfCheckIn = async (code: string): Promise<{ ok: boolean; message: string }> => {
    try {
      const res = await api.checkInWithCode(code.trim());
      await refetchEvents().catch(err => console.error('Refresh after check-in failed', err));
      return { ok: true, message: `Checked in to ${res.event_title}.` };
    } catch (err) {
      const msg = (err as Error).message;
      if (msg.includes('(410)')) return { ok: false, message: 'That door code has expired or is not valid.' };
      if (msg.includes('(409)')) return { ok: false, message: 'You are already checked in for this event.' };
      return { ok: false, message: serverMessage(err, 'Check-in failed. Ask an officer for the current door code.') };
    }
  };

  return {
    excuses,
    setExcuses,
    handleRecordAttendance,
    handleSubmitExcuse,
    handleReviewExcuse,
    handleSelfCheckIn
  };
}
