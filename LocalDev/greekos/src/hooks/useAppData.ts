import { useEffect, useRef, useState } from 'react';
import { INITIAL_ANNOUNCEMENTS, INITIAL_RULES } from '../data/mockData';
import { Announcement, ChapterEvent, ChapterRule, Member, SecurityAssignment } from '../types';
import { api, ensureLogin, optionalOfficerCall, EventDto, TaskDto } from '../api';
import { isoDay } from '../formatters';
import { MemberBalance, adaptMemberBalance } from '../lib/balance';
import { isOfficerView } from '../lib/session';
import {
  adaptAnnouncements,
  adaptEventDetail,
  adaptEvents,
  adaptExcuses,
  adaptFines,
  adaptInitiatives,
  adaptMembers,
  adaptPayments,
  adaptRecruits,
  adaptSecurityAssignment,
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
import { useContribution } from './useContribution';

/** Composes the domain hooks, runs the single initial backend load, and owns the
 *  few cross-domain bits (session identity, announcements, NL command execution). */
export function useAppData() {
  // The real session (from /me + /rbac/me/permissions) …
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [sessionName, setSessionName] = useState<string>('');
  const [myBalance, setMyBalance] = useState<MemberBalance | null>(null);
  const sessionIsOfficer = isOfficerView(permissions);
  // … and the *view*, which the Demo "view as" switcher may override. Starts
  // as officer so the backend-down mock data still shows the full prototype.
  const [isOfficer, setIsOfficer] = useState<boolean>(true);
  const [currentMemberName, setCurrentMemberName] = useState<string>('Alexander Mercer');

  const [announcements, setAnnouncements] = useState<Announcement[]>(INITIAL_ANNOUNCEMENTS);

  // Demo-only tabs still live in localStorage.
  const [rules] = usePersistentState<ChapterRule[]>('g_rules', INITIAL_RULES);

  const { toastMessage, showToast, dismissToast } = useToast();
  const { loading, setLoading, backendDown, setBackendDown, syncApi } = useBackend(showToast);
  const outbox = useOutbox();
  const { enqueueOutbox } = outbox;

  const roster = useRoster(showToast);
  const { members, setMembers } = roster;

  // Jobs live on the same `tasks` table for both parents, so one refetch restamps
  // all three boards. The ref breaks the cycle: the domain hooks call refetchJobs, but
  // it can only be built from the setters those same hooks return.
  const refetchJobsRef = useRef<() => Promise<void>>(async () => {});
  const refetchJobs = () => refetchJobsRef.current();

  const events = useEvents({ members, syncApi, showToast, enqueueOutbox, refetchJobs });
  const initiatives = useInitiatives({ members, syncApi, showToast, refetchJobs });
  const finance = useFinance({ members, setMembers, currentMemberName, isOfficer, syncApi, showToast, enqueueOutbox });
  const attendance = useAttendance({
    members,
    setEvents: events.setEvents,
    refetchEvents: events.refetchEvents,
    syncApi,
    showToast,
    enqueueOutbox
  });
  const tasks = useTasks({
    syncApi,
    showToast,
    refetchJobs
  });
  const recruitment = useRecruitment({ syncApi, showToast, enqueueOutbox });
  const contribution = useContribution(currentMemberName, events.events, initiatives.initiatives);

  /** Stamp the job rows onto whichever event/initiative owns each one. The chip
   *  counts live on the event rows, so restamp those in the same update when
   *  fresh ones are supplied (rows are patched, never re-adapted, to keep the
   *  per-event security shifts already in state). */
  const applyJobs = (
    taskRows: TaskDto[], rosterRows: Member[], eventRows?: EventDto[],
    titles = {
      events: new Map<string, string>((eventRows ?? events.events).map(e => [e.id, e.title])),
      initiatives: new Map<string, string>(initiatives.initiatives.map(i => [i.id, i.title]))
    }
  ) => {
    tasks.setTasks(adaptTasks(taskRows, rosterRows, titles));
    const membersById = new Map(rosterRows.map(m => [m.id, m]));
    const { byEvent, byInitiative } = groupJobsByParent(taskRows, membersById);
    const countsById = new Map((eventRows ?? []).map(row => [row.id, row]));
    events.setEvents(evts => evts.map(e => {
      const row = countsById.get(e.id);
      return {
        ...e,
        jobs: byEvent.get(e.id) ?? [],
        ...(row ? { jobCount: row.job_count || 0, openJobCount: row.open_job_count || 0 } : {})
      };
    }));
    initiatives.setInitiatives(inits => inits.map(i => ({ ...i, jobs: byInitiative.get(i.id) ?? [] })));
  };
  // Jobs and the open-job chips come from different endpoints, so both are read
  // here. refetchEvents already calls this, hence no call back into it.
  refetchJobsRef.current = async () => {
    const [taskRows, eventRows] = await Promise.all([api.getTasks(), api.getEvents()]);
    applyJobs(taskRows, members, eventRows);
  };

  // ----------------------------------------------------
  // BACKEND LOAD (one try/catch: any failure falls back to the mock data)
  // ----------------------------------------------------
  useEffect(() => {
    (async () => {
      try {
        await ensureLogin();
        const [me, perms, memberRows, standingRows, scoreRows] = await Promise.all([
          api.getMe(),
          api.getMyPermissions(),
          api.getMembers(),
          // Officer-gated: a member session 403s, which just means an empty
          // standing/score section rather than a failed load.
          optionalOfficerCall(api.getStandings(), []),
          optionalOfficerCall(api.getScores(), [])
        ]);
        const permissionSet = new Set(perms.permissions);
        const rosterRows = adaptMembers(memberRows, standingRows, scoreRows);

        const [eventRows, excuseRows, fineRows, treasury, taskRows, annRows, recruitRows, initRows, myBalanceRow] =
          await Promise.all([
            api.getEvents(),
            api.getExcuses(),
            api.getFines(),
            optionalOfficerCall(api.getTreasuryDashboard(), null),
            api.getTasks(),
            api.getAnnouncements(),
            optionalOfficerCall(api.getRecruits(), []),
            api.getInitiatives(),
            api.getMemberTreasuryDashboard(me.id).then(adaptMemberBalance).catch(err => {
              console.error('Member balance load failed', err);
              return null;
            })
          ]);

        // Security rosters, organizer/supervisor names and the door code are
        // all per event, so only upcoming events get the extra requests; a
        // failing one just leaves that event's row with the list data.
        const adaptedEvents = adaptEvents(eventRows);
        const membersById = new Map(rosterRows.map(m => [m.id, m]));
        const today = isoDay();
        const securityByEvent = new Map<string, SecurityAssignment[]>();
        const detailByEvent = new Map<string, Partial<ChapterEvent>>();
        await Promise.all(
          adaptedEvents.filter(e => e.date >= today).map(async e => {
            try {
              const [rows, detail, link] = await Promise.all([
                api.listSecurity(e.id),
                api.getEvent(e.id),
                api.getCheckInLink(e.id)
              ]);
              securityByEvent.set(e.id, rows.map(row => adaptSecurityAssignment(row, membersById)));
              detailByEvent.set(e.id, {
                ...adaptEventDetail(detail, rosterRows),
                checkInToken: link.short_code,
                checkInLinkActive: !!link.short_code
              });
            } catch (err) {
              console.error(`Upcoming-event load failed for event ${e.id}`, err);
            }
          })
        );

        setMembers(rosterRows);
        setPermissions(permissionSet);
        setSessionName(me.name);
        setMyBalance(myBalanceRow);
        setCurrentMemberName(me.name);
        setIsOfficer(isOfficerView(permissionSet));
        events.setEvents(adaptedEvents.map(e => ({
          ...e,
          ...(detailByEvent.get(e.id) || {}),
          securityAssignments: securityByEvent.get(e.id) || e.securityAssignments
        })));
        attendance.setExcuses(adaptExcuses(excuseRows, rosterRows));
        finance.setFines(adaptFines(fineRows, rosterRows));
        finance.setPayments(adaptPayments(treasury?.recent_payments || [], rosterRows));
        // No chapter-wide ledger read exists yet (statements are per member),
        // so the chapter-ledger view starts empty rather than faked.
        finance.setLedger([]);
        setAnnouncements(adaptAnnouncements(annRows, rosterRows));
        recruitment.setPnms(adaptRecruits(recruitRows));
        initiatives.setInitiatives(adaptInitiatives(initRows, rosterRows));
        // Queued after both setters above, so it restamps the freshly adapted rows.
        applyJobs(taskRows, rosterRows, eventRows, {
          events: new Map(adaptedEvents.map(e => [e.id, e.title])),
          initiatives: new Map(initRows.map(i => [i.id, i.title]))
        });
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
    permissions,
    sessionIsOfficer,
    sessionName,
    contribution,
    myBalance,
    setIsOfficer,
    currentMemberName,
    setCurrentMemberName,
    announcements,
    rules,
    loading,
    backendDown,
    toastMessage,
    showToast,
    dismissToast,
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
