import { useEffect, useRef, useState } from 'react';
import { INITIAL_ANNOUNCEMENTS, INITIAL_RULES } from '../data/mockData';
import { Announcement, ChapterRule, Member } from '../types';
import { api, ensureLogin, TaskDto } from '../api';
import {
  adaptAnnouncements,
  adaptEvents,
  adaptExcuses,
  adaptFines,
  adaptInitiatives,
  adaptMembers,
  adaptPayments,
  adaptRecruits,
  adaptTasks,
  groupJobsByParent
} from '../adapters';
import { usePersistentState } from './usePersistentState';
import { useToast } from './useToast';
import { useBackend } from './useBackend';
import { useOutbox } from './useOutbox';
import { useRoster } from './useRoster';
import { useEvents } from './useEvents';
import { useInitiatives } from './useInitiatives';
import { useFinance } from './useFinance';
import { useAttendance } from './useAttendance';
import { useTasks } from './useTasks';
import { useRecruitment } from './useRecruitment';

/** Composes the domain hooks, runs the single initial backend load, and owns the
 *  few cross-domain bits (session identity, announcements, NL command execution). */
export function useAppData() {
  // Access level & impersonation state
  const [isOfficer, setIsOfficer] = useState<boolean>(true);
  const [currentMemberName, setCurrentMemberName] = useState<string>('Alexander Mercer');

  const [announcements, setAnnouncements] = useState<Announcement[]>(INITIAL_ANNOUNCEMENTS);

  // Demo-only tabs still live in localStorage.
  const [rules] = usePersistentState<ChapterRule[]>('g_rules', INITIAL_RULES);

  const { toastMessage, showToast } = useToast();
  const { loading, setLoading, backendDown, setBackendDown, syncApi } = useBackend(showToast);
  const outbox = useOutbox();
  const { enqueueOutbox } = outbox;

  const roster = useRoster(showToast);
  const { members, setMembers } = roster;

  // Jobs live on the same `tasks` table for both parents, so one refetch restamps
  // both boards. The ref breaks the cycle: the domain hooks call refetchJobs, but
  // it can only be built from the setters those same hooks return.
  const refetchJobsRef = useRef<() => Promise<void>>(async () => {});
  const refetchJobs = () => refetchJobsRef.current();

  const events = useEvents({ syncApi, showToast, enqueueOutbox, refetchJobs });
  const initiatives = useInitiatives({ members, syncApi, showToast, refetchJobs });
  const finance = useFinance({ members, setMembers, currentMemberName, isOfficer, syncApi, showToast, enqueueOutbox });
  const attendance = useAttendance({
    members,
    events: events.events,
    setEvents: events.setEvents,
    refetchEvents: events.refetchEvents,
    syncApi,
    showToast,
    enqueueOutbox
  });
  const tasks = useTasks({ members, syncApi, showToast });
  const recruitment = useRecruitment({ syncApi, showToast, enqueueOutbox });

  /** Stamp the job rows onto whichever event/initiative owns each one. */
  const applyJobs = (taskRows: TaskDto[], rosterRows: Member[]) => {
    const membersById = new Map(rosterRows.map(m => [m.id, m]));
    const { byEvent, byInitiative } = groupJobsByParent(taskRows, membersById);
    events.setEvents(evts => evts.map(e => ({ ...e, jobs: byEvent.get(e.id) ?? [] })));
    initiatives.setInitiatives(inits => inits.map(i => ({ ...i, jobs: byInitiative.get(i.id) ?? [] })));
  };
  refetchJobsRef.current = async () => applyJobs(await api.getTasks(), members);

  // ----------------------------------------------------
  // BACKEND LOAD (one try/catch: any failure falls back to the mock data)
  // ----------------------------------------------------
  useEffect(() => {
    (async () => {
      try {
        await ensureLogin();
        const [me, memberRows, standingRows, scoreRows] = await Promise.all([
          api.getMe(),
          api.getMembers(),
          api.getStandings(),
          // Officer-only endpoint: a member session 403s, which just means no
          // prior-shift counts rather than a failed load.
          api.getScores().catch(() => [])
        ]);
        const rosterRows = adaptMembers(memberRows, standingRows, scoreRows);

        const [eventRows, excuseRows, fineRows, treasury, taskRows, annRows, recruitRows, initRows] =
          await Promise.all([
            api.getEvents(),
            api.getExcuses(),
            api.getFines(),
            api.getTreasuryDashboard(),
            api.getTasks(),
            api.getAnnouncements(),
            api.getRecruits(),
            api.getInitiatives()
          ]);

        setMembers(rosterRows);
        setCurrentMemberName(me.name);
        events.setEvents(adaptEvents(eventRows));
        attendance.setExcuses(adaptExcuses(excuseRows, rosterRows));
        finance.setFines(adaptFines(fineRows, rosterRows));
        finance.setPayments(adaptPayments(treasury.recent_payments || [], rosterRows));
        // No chapter-wide ledger read exists yet (statements are per member),
        // so the immutable-ledger view starts empty rather than faked.
        finance.setLedger([]);
        tasks.setTasks(adaptTasks(taskRows, rosterRows));
        setAnnouncements(adaptAnnouncements(annRows, rosterRows));
        recruitment.setPnms(adaptRecruits(recruitRows));
        initiatives.setInitiatives(adaptInitiatives(initRows, rosterRows));
        // Queued after both setters above, so it restamps the freshly adapted rows.
        applyJobs(taskRows, rosterRows);
      } catch (err) {
        console.error('Backend load failed', err);
        setBackendDown(true);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // ----------------------------------------------------
  // ANNOUNCEMENTS
  // ----------------------------------------------------
  const refetchAnnouncements = async () =>
    setAnnouncements(adaptAnnouncements(await api.getAnnouncements(), members));

  /** Officer-only: drops a draft, retires a sent one from the calendar. */
  const handleDeleteAnnouncement = (announcementId: string) => {
    setAnnouncements(prev => prev.filter(a => a.id !== announcementId));
    syncApi(() => api.deleteAnnouncement(announcementId), refetchAnnouncements);
    showToast('Announcement removed from calendar.');
  };

  // ----------------------------------------------------
  // NATURAL LANGUAGE COMMAND EXECUTION
  // ----------------------------------------------------
  const handleExecuteCommand = (cmdResult: {
    type: 'FINE' | 'TASK' | 'EVENT' | 'BID' | 'ANNOUNCEMENT' | 'EXCUSE_APPROVE' | 'ATTENDANCE';
    payload: any;
    summary: string;
  }) => {
    switch (cmdResult.type) {
      case 'FINE':
        finance.handleIssueFine(cmdResult.payload);
        break;
      case 'TASK':
        tasks.handleAddTask(cmdResult.payload);
        break;
      case 'EVENT':
        events.handleAddEvent(cmdResult.payload);
        break;
      case 'BID':
        const targetPnm = recruitment.pnms.find(p => p.name.toLowerCase().includes(cmdResult.payload.pnmName.toLowerCase()));
        if (targetPnm) {
          recruitment.handleExtendBid(targetPnm.id);
        }
        break;
      case 'ANNOUNCEMENT': {
        // The backend keeps a calendar slot separate from the send time, so a
        // dispatched blast takes the date the command carried (today if none)
        // and lands on that calendar cell.
        const calendarDate = cmdResult.payload.date || new Date().toISOString().substring(0, 10);
        // The command payload carries no id; the refetch swaps in the real row.
        const localId = 'a_' + Math.random().toString(36).substring(2, 9);
        setAnnouncements(prev => [{ ...cmdResult.payload, id: localId, calendarDate }, ...prev]);
        syncApi(async () => {
          const created = await api.createAnnouncement({
            title: cmdResult.payload.title,
            body: cmdResult.payload.content,
            calendar_date: calendarDate
          });
          await api.sendAnnouncement(created.id);
        }, refetchAnnouncements);
        enqueueOutbox({
          type: 'ANNOUNCEMENT_BLAST',
          recipient: 'All Brothers',
          message: `[GreekOS Announcement] ${cmdResult.payload.content}`,
          channel: 'SMS'
        });
        showToast(`Dispatched broadcast announcement.`);
        break;
      }
      case 'EXCUSE_APPROVE':
        const targetExcuse = attendance.excuses.find(e => e.memberName.toLowerCase().includes(cmdResult.payload.memberName.toLowerCase()) && e.status === 'Pending');
        if (targetExcuse) {
          attendance.handleReviewExcuse(targetExcuse.id, 'Approved', currentMemberName);
        }
        break;
      default:
        break;
    }
  };

  return {
    isOfficer,
    setIsOfficer,
    currentMemberName,
    setCurrentMemberName,
    announcements,
    rules,
    loading,
    backendDown,
    toastMessage,
    showToast,
    outbox,
    roster,
    events,
    initiatives,
    finance,
    attendance,
    tasks,
    recruitment,
    handleDeleteAnnouncement,
    handleExecuteCommand
  };
}
