import { useState } from 'react';
import { INITIAL_EVENTS } from '../data/mockData';
import { ChapterEvent, EventJob, Member, SecurityAssignment } from '../types';
import { api } from '../api';
import { adaptEvents, adaptSecurityAssignment, toEventBody } from '../adapters';
import { ShowToast } from './useToast';
import { EnqueueOutbox } from './useOutbox';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  syncApi: SyncApi;
  showToast: ShowToast;
  enqueueOutbox: EnqueueOutbox;
}

/** Chapter events plus their claimable jobs and security shifts. */
export function useEvents({ members, syncApi, showToast, enqueueOutbox }: Deps) {
  const [events, setEvents] = useState<ChapterEvent[]>(INITIAL_EVENTS);

  const refetchEvents = async () => setEvents(adaptEvents(await api.getEvents()));

  /** Reload one event's security roster from the backend. */
  const refetchSecurity = async (eventId: string) => {
    const membersById = new Map(members.map(m => [m.id, m]));
    const rows = await api.listSecurity(eventId);
    const securityAssignments = rows.map(row => adaptSecurityAssignment(row, membersById));
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, securityAssignments } : e));
  };

  /** The swap id lives on the assignment row, so read it fresh before acting. */
  const pendingSwapId = async (eventId: string, assignmentId: string) => {
    const rows = await api.listSecurity(eventId);
    const swap = rows.find(r => r.task_id === assignmentId)?.pending_swap;
    if (!swap || swap.status !== 'pending') throw new Error('That swap request is no longer pending');
    return swap.id;
  };

  /** Swap mutations share one 409 the UI can put in plain words. */
  const syncSwap = (eventId: string, call: () => Promise<unknown>) =>
    syncApi(async () => {
      try {
        await call();
      } catch (err) {
        // syncApi only refetches on success, so reconcile the optimistic row here.
        await refetchSecurity(eventId).catch(() => { /* leave the optimistic row */ });
        const message = (err as Error).message;
        if (message.includes('swap_wrong_state')) {
          throw new Error('That swap request is no longer pending');
        }
        throw err;
      }
    }, () => refetchSecurity(eventId));

  const handleAddEvent = (newEvent: Omit<ChapterEvent, 'id' | 'attendanceTaken' | 'checkedInCount'>) => {
    const ev: ChapterEvent = {
      ...newEvent,
      id: 'e_' + Math.random().toString(36).substring(2, 9),
      attendanceTaken: false,
      checkedInCount: 0,
      checkInPin: Math.floor(1000 + Math.random() * 9000).toString(),
      checkInLinkActive: true,
      securityAssignments: []
    };
    setEvents(prev => [ev, ...prev]);
    syncApi(() => api.createEvent(toEventBody(ev)), refetchEvents);
    showToast(`Created chapter event "${ev.title}"`);
  };

  const handleUpdateEvent = (updated: ChapterEvent) => {
    setEvents(prev => prev.map(e => e.id === updated.id ? updated : e));
    syncApi(() => api.updateEvent(updated.id, toEventBody(updated)), refetchEvents);
  };

  const handleVolunteerOrganizer = (eventId: string, memberName: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        const currentOrgs = e.organizers || [];
        if (!currentOrgs.includes(memberName)) {
          return { ...e, organizers: [...currentOrgs, memberName] };
        }
      }
      return e;
    }));
    showToast(`Volunteered as Organizer for event!`);
  };

  const handleClaimJob = (eventId: string, jobId: string, memberId: string, memberName: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return {
          ...e,
          jobs: e.jobs.map(j => {
            if (j.id === jobId) {
              const alreadyClaimed = j.claimants.some(c => c.memberId === memberId);
              if (!alreadyClaimed && j.claimants.length < j.peopleNeeded) {
                return {
                  ...j,
                  claimants: [...j.claimants, { memberId, memberName, claimedAt: new Date().toISOString() }],
                  status: 'In Progress'
                };
              }
            }
            return j;
          })
        };
      }
      return e;
    }));
    showToast(`Claimed job successfully!`);
  };

  const handleUnclaimJob = (eventId: string, jobId: string, memberId: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return {
          ...e,
          jobs: e.jobs.map(j => {
            if (j.id === jobId) {
              const updatedClaimants = j.claimants.filter(c => c.memberId !== memberId);
              return {
                ...j,
                claimants: updatedClaimants,
                status: updatedClaimants.length === 0 ? 'To Do' : j.status
              };
            }
            return j;
          })
        };
      }
      return e;
    }));
    showToast(`Unclaimed job.`);
  };

  const handleReportJobDone = (eventId: string, jobId: string, memberName: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return {
          ...e,
          jobs: e.jobs.map(j => {
            if (j.id === jobId) {
              return {
                ...j,
                status: 'Done Reported',
                reportedBy: memberName,
                reportedAt: new Date().toISOString()
              };
            }
            return j;
          })
        };
      }
      return e;
    }));
    showToast(`Reported job complete! Awaiting supervisor sign-off.`);
  };

  const handleApproveJob = (eventId: string, jobId: string, officerName: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return {
          ...e,
          jobs: e.jobs.map(j => {
            if (j.id === jobId) {
              return {
                ...j,
                status: 'Approved',
                approvedBy: officerName,
                approvedAt: new Date().toISOString()
              };
            }
            return j;
          })
        };
      }
      return e;
    }));
    showToast(`Job approved and verified by supervisor.`);
  };

  const handleRejectJob = (eventId: string, jobId: string, officerName: string, reason: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return {
          ...e,
          jobs: e.jobs.map(j => {
            if (j.id === jobId) {
              // Notify outbox
              j.claimants.forEach(c => {
                enqueueOutbox({
                  type: 'JOB_REJECTED',
                  recipient: c.memberName,
                  message: `[GreekOS Task Notice] Your job "${j.title}" on event "${e.title}" was returned with feedback: ${reason}`,
                  channel: 'SMS'
                });
              });

              return {
                ...j,
                status: 'In Progress',
                rejectionReason: reason
              };
            }
            return j;
          })
        };
      }
      return e;
    }));
    showToast(`Job rejected with feedback sent to brother outbox.`);
  };

  const handleAddJobToEvent = (eventId: string, jobData: Omit<EventJob, 'id' | 'claimants' | 'status'>) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        const newJob: EventJob = {
          ...jobData,
          id: 'job_' + Math.random().toString(36).substring(2, 9),
          claimants: [],
          status: 'To Do'
        };
        return { ...e, jobs: [...e.jobs, newJob] };
      }
      return e;
    }));
    showToast(`Added job to event.`);
  };

  const handleSendEventNotifyBlast = (eventId: string) => {
    const ev = events.find(e => e.id === eventId);
    if (!ev) return;

    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, notifiedAt: new Date().toISOString() } : e));
    enqueueOutbox({
      type: 'EVENT_NOTIFY',
      recipient: 'All Active Chapter Brothers (10)',
      message: `[GreekOS Broadcast] ${ev.title} on ${ev.date} at ${ev.time} (${ev.location}). Open jobs are ready for sign-up!`,
      channel: 'SMS'
    });
    showToast(`Notification blast dispatched to Chapter outbox!`);
  };

  const handleToggleCheckInLink = (eventId: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return { ...e, checkInLinkActive: !e.checkInLinkActive };
      }
      return e;
    }));
  };

  const handleAssignSecurity = (eventId: string, memberId: string, memberName: string, _station?: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        const newAssignment: SecurityAssignment = {
          id: 'sec_' + Math.random().toString(36).substring(2, 9),
          memberId,
          memberName,
          station: '',
          status: 'Confirmed'
        };
        return {
          ...e,
          securityAssignments: [...(e.securityAssignments || []), newAssignment]
        };
      }
      return e;
    }));
    syncApi(() => api.assignSecurity(eventId, memberId), () => refetchSecurity(eventId));
    enqueueOutbox({
      type: 'SECURITY_ASSIGNED',
      recipient: memberName,
      message: `[GreekOS Security] You have been assigned to a security shift.`,
      channel: 'SMS'
    });
    showToast(`Assigned ${memberName} to security shift.`);
  };

  const handleRequestSecuritySwap = (eventId: string, assignmentId: string, targetMemberId: string, targetMemberName: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId && e.securityAssignments) {
        return {
          ...e,
          securityAssignments: e.securityAssignments.map(s => {
            if (s.id === assignmentId) {
              return {
                ...s,
                swapRequestedWithId: targetMemberId,
                swapRequestedWithName: targetMemberName,
                swapStatus: 'Pending'
              };
            }
            return s;
          })
        };
      }
      return e;
    }));
    syncSwap(eventId, () => api.requestSwap(eventId, assignmentId, targetMemberId));

    enqueueOutbox({
      type: 'SECURITY_SWAP_REQUEST',
      recipient: targetMemberName,
      message: `[GreekOS Swap Request] A brother requested you to cover their security shift. Review in Events tab.`,
      channel: 'SMS'
    });
    showToast(`Shift swap request sent to ${targetMemberName}.`);
  };

  const handleRespondSecuritySwap = (eventId: string, assignmentId: string, accept: boolean) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId && e.securityAssignments) {
        return {
          ...e,
          securityAssignments: e.securityAssignments.map(s => {
            if (s.id === assignmentId) {
              if (accept && s.swapRequestedWithId && s.swapRequestedWithName) {
                return {
                  ...s,
                  memberId: s.swapRequestedWithId,
                  memberName: s.swapRequestedWithName,
                  swapRequestedWithId: undefined,
                  swapRequestedWithName: undefined,
                  swapStatus: 'Accepted'
                };
              } else {
                return {
                  ...s,
                  swapRequestedWithId: undefined,
                  swapRequestedWithName: undefined,
                  swapStatus: 'Declined'
                };
              }
            }
            return s;
          })
        };
      }
      return e;
    }));
    syncSwap(eventId, async () => {
      const swapId = await pendingSwapId(eventId, assignmentId);
      await (accept ? api.acceptSwap(eventId, swapId) : api.declineSwap(eventId, swapId));
    });
    showToast(accept ? 'Accepted security shift swap.' : 'Declined shift swap.');
  };

  /** The requester withdraws their own pending swap request. */
  const handleCancelSecuritySwap = (eventId: string, assignmentId: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId && e.securityAssignments) {
        return {
          ...e,
          securityAssignments: e.securityAssignments.map(s => s.id === assignmentId ? {
            ...s,
            swapRequestedWithId: undefined,
            swapRequestedWithName: undefined,
            swapStatus: 'None' as const
          } : s)
        };
      }
      return e;
    }));
    syncSwap(eventId, async () => {
      const swapId = await pendingSwapId(eventId, assignmentId);
      await api.cancelSwap(eventId, swapId);
    });
    showToast('Cancelled your shift swap request.');
  };

  return {
    events,
    setEvents,
    refetchEvents,
    handleAddEvent,
    handleUpdateEvent,
    handleVolunteerOrganizer,
    handleClaimJob,
    handleUnclaimJob,
    handleReportJobDone,
    handleApproveJob,
    handleRejectJob,
    handleAddJobToEvent,
    handleSendEventNotifyBlast,
    handleToggleCheckInLink,
    handleAssignSecurity,
    handleRequestSecuritySwap,
    handleRespondSecuritySwap,
    handleCancelSecuritySwap
  };
}
