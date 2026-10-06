import { useEffect, useRef, useState } from 'react';
import { Announcement, Member } from '../types';
import { api, AuthRequiredError, ensureLogin, logout, optionalOfficerCall, EventDto, TaskDto } from '../api';
import { loadStartupEvents, loadJobRefresh } from '../lib/app-data';
import { EMPTY_CONTRIBUTION } from '../lib/contribution';
import {
  adaptAnnouncements,
  adaptContribution,
  adaptExcuses,
  adaptFines,
  adaptInitiatives,
  adaptMembers,
  adaptPayments,
  adaptRecruits,
  adaptTasks,
  groupJobsByParent
} from '../adapters';
import { useToast } from './useToast';
import { useBackend } from './useBackend';
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
  const [chapterId, setChapterId] = useState<string>('');
  const [chapterName, setChapterName] = useState<string>('');
  const [currentMemberId, setCurrentMemberId] = useState<string>('');
  const [currentMemberName, setCurrentMemberName] = useState<string>('');

  const [announcements, setAnnouncements] = useState<Announcement[]>([]);

  const { toastMessage, showToast, dismissToast } = useToast();
  const { loading, setLoading, backendDown, setBackendDown, syncApi } = useBackend(showToast);

  const roster = useRoster(showToast);
  const { members, setMembers } = roster;

  // Jobs live on the same `tasks` table for both parents, so one refetch restamps
  // all three boards. The ref breaks the cycle: the domain hooks call refetchJobs, but
  // it can only be built from the setters those same hooks return.
  const refetchJobsRef = useRef<(eventId?: string) => Promise<void>>(async () => {});
  const refetchJobs = (eventId?: string) => refetchJobsRef.current(eventId);

  const events = useEvents({ members, syncApi, showToast, refetchJobs });
  const initiatives = useInitiatives({ members, syncApi, refetchJobs });
  const finance = useFinance({ members, setMembers, currentMemberId, backendDown, setBackendDown, showToast });
  const attendance = useAttendance({
    members,
    setEvents: events.setEvents,
    refetchEvents: events.refetchEvents,
    syncApi,
    showToast
  });
  const tasks = useTasks({ syncApi, refetchJobs });
  const recruitment = useRecruitment({ syncApi });
  const contribution = useContribution();

  /** Stamp the job rows onto whichever event/initiative owns each one. The chip
   *  counts live on the event rows, so restamp those in the same update when
   *  fresh ones are supplied (rows are patched, never re-adapted, to keep the
   *  per-event security shifts already in state). */
  const applyJobs = (
    taskRows: TaskDto[], rosterRows: Member[], eventRows?: EventDto[],
    titles = {
      events: new Map<string, string>([...events.events, ...(eventRows ?? [])].map(e => [e.id, e.title])),
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
  // A job change touches the job boards and, for an event's job, that one
  // event's open-job chips, so only those are read (not the whole event list).
  // refetchEvents already calls this, hence no call back into it.
  refetchJobsRef.current = async (eventId?: string) => {
    const { taskRows, detail } = await loadJobRefresh(api, eventId);
    if (taskRows) applyJobs(taskRows, members, detail && [detail]);
    else if (detail) events.setEvents(evts => evts.map(e => e.id === detail.id ? {
      ...e, jobCount: detail.job_count || 0, openJobCount: detail.open_job_count || 0
    } : e));
  };

  /** Re-reads the caller's own permission keys. Role edits on yourself change
   *  what the nav may show, so the roster calls this instead of waiting for a
   *  reload. */
  const refreshOwnPermissions = async (memberId: string) => {
    if (memberId !== currentMemberId) return;
    try {
      const perms = await api.getMyPermissions();
      const permissionSet = new Set(perms.permissions);
      setPermissions(permissionSet);
    } catch (err) {
      console.error('Permission refresh failed', err);
    }
  };

  // ----------------------------------------------------
  // BACKEND LOAD (one try/catch; failure leaves empty state + backendDown)
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

        const [eventRows, excuseRows, fineRows, treasury, taskRows, annRows, recruitRows, initRows, contributionRow, myTreasuryRow] =
          await Promise.all([
            api.getEvents(),
            api.getExcuses(),
            api.getFines(),
            optionalOfficerCall(api.getTreasuryDashboard(), null),
            api.getTasks(),
            api.getAnnouncements(),
            optionalOfficerCall(api.getRecruits(), []),
            api.getInitiatives(),
            // Lifetime contribution counts. A failure here empties the "My
            // record" panel rather than failing the whole load.
            api.getMyContribution().then(adaptContribution).catch(err => {
              console.error('Contribution load failed', err);
              return EMPTY_CONTRIBUTION;
            }),
            api.getMemberTreasuryDashboard(me.id).catch(err => {
              console.error('Member treasury load failed', err);
              return null;
            })
          ]);

        // Security rosters, organizer/supervisor names and the door code for
        // every upcoming event arrive in one request. If it fails, the list
        // still renders from GET /api/events and the officer is told why the
        // detail fields are blank (no per-event fallback: that is 3N requests).
        const { events: adaptedEvents, notice, error } = await loadStartupEvents(eventRows, rosterRows, api);
        if (notice) {
          console.error('Upcoming event details load failed', error);
          showToast(notice);
        }

        setMembers(rosterRows);
        setPermissions(permissionSet);
        setSessionName(me.name);
        setChapterId(me.chapter_id);
        setChapterName(me.chapter_name || '');
        finance.setMyTreasury(myTreasuryRow);
        contribution.setRecord(contributionRow);
        setCurrentMemberId(me.id);
        setCurrentMemberName(me.name);
        events.setEvents(adaptedEvents);
        attendance.setExcuses(adaptExcuses(excuseRows, rosterRows));
        finance.setFines(adaptFines(fineRows, rosterRows));
        finance.setPayments(adaptPayments(treasury?.recent_payments || [], rosterRows));
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
        if (err instanceof AuthRequiredError) logout();
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
    syncApi(() => api.deleteAnnouncement(announcementId), refetchAnnouncements, 'Announcement removed from calendar.');
  };

  // ----------------------------------------------------
  // COMMAND CONSOLE EXECUTION
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
        }, refetchAnnouncements, 'Dispatched broadcast announcement.');
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
    permissions,
    sessionName,
    chapterId,
    chapterName,
    contribution: contribution.record,
    myBalance: finance.myBalance,
    currentMemberId,
    currentMemberName,
    announcements,
    loading,
    backendDown,
    toastMessage,
    showToast,
    dismissToast,
    roster,
    events,
    initiatives,
    finance,
    attendance,
    tasks,
    recruitment,
    refreshOwnPermissions,
    handleDeleteAnnouncement,
    handleExecuteCommand
  };
}
