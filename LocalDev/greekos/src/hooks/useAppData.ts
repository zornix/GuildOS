import { useEffect, useState } from 'react';
import { INITIAL_ANNOUNCEMENTS, INITIAL_RULES } from '../data/mockData';
import { Announcement, ChapterRule, SecurityAssignment } from '../types';
import { api, ensureLogin } from '../api';
import {
  adaptAnnouncements,
  adaptEvents,
  adaptExcuses,
  adaptFines,
  adaptInitiatives,
  adaptMembers,
  adaptPayments,
  adaptRecruits,
  adaptSecurityAssignment,
  adaptTasks
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

  const events = useEvents({ members, syncApi, showToast, enqueueOutbox });
  const initiatives = useInitiatives({ members, syncApi, showToast });
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

  // ----------------------------------------------------
  // BACKEND LOAD (one try/catch: any failure falls back to the mock data)
  // ----------------------------------------------------
  useEffect(() => {
    (async () => {
      try {
        await ensureLogin();
        const [me, memberRows, standingRows] = await Promise.all([
          api.getMe(),
          api.getMembers(),
          api.getStandings()
        ]);
        const rosterRows = adaptMembers(memberRows, standingRows);

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

        // Security rosters are per event, so only upcoming events are worth a
        // request; a failing one just leaves that event's shift list empty.
        const adaptedEvents = adaptEvents(eventRows);
        const membersById = new Map(rosterRows.map(m => [m.id, m]));
        const today = new Date().toISOString().substring(0, 10);
        const securityByEvent = new Map<string, SecurityAssignment[]>();
        await Promise.all(
          adaptedEvents.filter(e => e.date >= today).map(async e => {
            try {
              const rows = await api.listSecurity(e.id);
              securityByEvent.set(e.id, rows.map(row => adaptSecurityAssignment(row, membersById)));
            } catch (err) {
              console.error(`Security load failed for event ${e.id}`, err);
            }
          })
        );

        setMembers(rosterRows);
        setCurrentMemberName(me.name);
        events.setEvents(adaptedEvents.map(e => ({
          ...e,
          securityAssignments: securityByEvent.get(e.id) || e.securityAssignments
        })));
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
      } catch (err) {
        console.error('Backend load failed', err);
        setBackendDown(true);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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
      case 'ANNOUNCEMENT':
        setAnnouncements(prev => [cmdResult.payload, ...prev]);
        enqueueOutbox({
          type: 'ANNOUNCEMENT_BLAST',
          recipient: 'All Brothers',
          message: `[GreekOS Announcement] ${cmdResult.payload.content}`,
          channel: 'SMS'
        });
        showToast(`Dispatched broadcast announcement.`);
        break;
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
    handleExecuteCommand
  };
}
