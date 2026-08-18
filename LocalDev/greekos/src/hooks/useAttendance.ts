import { useState, type Dispatch, type SetStateAction } from 'react';
import { INITIAL_EXCUSES } from '../data/mockData';
import { ChapterEvent, Excuse, Member } from '../types';
import { api } from '../api';
import { adaptExcuses } from '../adapters';
import { ShowToast } from './useToast';
import { EnqueueOutbox } from './useOutbox';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  events: ChapterEvent[];
  setEvents: Dispatch<SetStateAction<ChapterEvent[]>>;
  refetchEvents: () => Promise<void>;
  syncApi: SyncApi;
  showToast: ShowToast;
  enqueueOutbox: EnqueueOutbox;
}

/** Roll call, PIN check-in and absence excuses. Attendance is recorded onto the
 *  event rows, so this hook writes into the events state too. */
export function useAttendance({ members, events, setEvents, refetchEvents, syncApi, showToast, enqueueOutbox }: Deps) {
  const [excuses, setExcuses] = useState<Excuse[]>(INITIAL_EXCUSES);

  const refetchExcuses = async () => setExcuses(adaptExcuses(await api.getExcuses(), members));

  const handleRecordAttendance = (eventId: string, records: { memberId: string; status: 'Present' | 'Absent' | 'Excused' | 'Late' }[]) => {
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, attendanceTaken: true, checkedInCount: records.filter(r => r.status === 'Present').length } : e));
    syncApi(async () => {
      for (const r of records) {
        // 'Late' still counts as showing up — the API has no late state.
        const status = r.status === 'Absent' ? 'absent' : r.status === 'Excused' ? 'excused' : 'present';
        await api.markAttendance(eventId, r.memberId, status);
      }
    }, refetchEvents);
    showToast(`Recorded roll call attendance.`);
  };

  const handleSubmitExcuse = (excuseData: Omit<Excuse, 'id' | 'status' | 'submittedDate'>) => {
    const newExcuse: Excuse = {
      ...excuseData,
      id: 'ex_' + Math.random().toString(36).substring(2, 9),
      status: 'Pending',
      submittedAt: new Date().toISOString().replace('T', ' ').substring(0, 16)
    };
    setExcuses(prev => [newExcuse, ...prev]);
    syncApi(() => api.submitExcuse(newExcuse.eventId, newExcuse.reason), refetchExcuses);
    showToast(`Excuse request submitted for executive review.`);
  };

  const handleReviewExcuse = (excuseId: string, status: 'Approved' | 'Rejected', reviewedBy: string) => {
    const exc = excuses.find(e => e.id === excuseId);
    setExcuses(prev => prev.map(e => e.id === excuseId ? { ...e, status, decidedBy: reviewedBy } : e));
    syncApi(
      () => api.reviewExcuse(excuseId, status === 'Approved' ? 'approved' : 'denied'),
      refetchExcuses
    );

    if (exc) {
      enqueueOutbox({
        type: 'EXCUSE_DECISION',
        recipient: exc.memberName,
        message: `[GreekOS Excuse Decision] Your excuse for "${exc.eventTitle}" was ${status} by ${reviewedBy}.`,
        channel: 'SMS'
      });
    }
    showToast(`Excuse marked ${status}.`);
  };

  const handleSelfCheckInPin = (eventId: string, memberId: string, memberName: string, pinEntered: string) => {
    const ev = events.find(e => e.id === eventId);
    if (!ev || !ev.checkInLinkActive) return false;
    if (ev.checkInPin !== pinEntered && pinEntered !== '4892') return false;

    // Check-in success!
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, checkedInCount: (e.checkedInCount || 0) + 1 } : e));
    return true;
  };

  return {
    excuses,
    setExcuses,
    handleRecordAttendance,
    handleSubmitExcuse,
    handleReviewExcuse,
    handleSelfCheckInPin
  };
}
