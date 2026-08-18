import { useState } from 'react';
import { INITIAL_EVENTS } from '../data/mockData';
import { ChapterEvent, EventJob, SecurityAssignment } from '../types';
import { api } from '../api';
import { adaptEvents, toEventBody } from '../adapters';
import { ShowToast } from './useToast';
import { EnqueueOutbox } from './useOutbox';
import { SyncApi } from './useBackend';

/** 409 conflict tokens the jobs API raises, mapped to member-facing copy. */
const JOB_409: Record<string, string> = {
  job_not_editable: 'Job can no longer be edited',
  job_not_cancellable: 'Only unclaimed To-Do jobs can be deleted',
  job_capacity_below_claims: "Can't set spots below current claims",
  security_no_edit: 'Security shifts are managed from the Security panel',
  security_no_cancel: 'Security shifts are managed from the Security panel'
};

/** api.ts throws `Error('PATCH /path failed (409): <detail>')`, so the conflict
 *  token is matched inside the message rather than read off a field. */
const jobErrorToast = (err: unknown, fallback: string) => {
  const msg = err instanceof Error ? err.message : '';
  const hit = Object.keys(JOB_409).find(token => msg.includes(token));
  return hit ? JOB_409[hit] : fallback;
};

interface Deps {
  syncApi: SyncApi;
  showToast: ShowToast;
  enqueueOutbox: EnqueueOutbox;
  refetchJobs: () => Promise<void>;
}

/** Chapter events plus their claimable jobs and security shifts. */
export function useEvents({ syncApi, showToast, enqueueOutbox, refetchJobs }: Deps) {
  const [events, setEvents] = useState<ChapterEvent[]>(INITIAL_EVENTS);

  // adaptEvents rebuilds rows with an empty jobs list, so restamp the boards after.
  const refetchEvents = async () => {
    setEvents(adaptEvents(await api.getEvents()));
    await refetchJobs();
  };

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
    // The backend commits the signed-in member; it has no impersonation concept.
    syncApi(() => api.commitTask(jobId), refetchJobs);
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
    syncApi(() => api.uncommitTask(jobId), refetchJobs);
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
    syncApi(() => api.reportJobDone(jobId), refetchJobs);
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
    syncApi(() => api.approveJob(jobId), refetchJobs);
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
    syncApi(() => api.rejectJob(jobId, reason), refetchJobs);
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
    syncApi(
      () =>
        api.createJob({
          title: jobData.title,
          description: jobData.description,
          people_needed: jobData.peopleNeeded,
          event_id: eventId
        }),
      refetchJobs
    );
    showToast(`Added job to event.`);
  };

  // Edit/delete are not applied optimistically: the backend can refuse either
  // (claimed job, capacity below claims, security shift), so the refetch is the
  // only source of truth and the 409 copy explains the refusal.
  const handleEditJob = (
    _eventId: string,
    jobId: string,
    patch: { title?: string; description?: string; peopleNeeded?: number }
  ) => {
    syncApi(async () => {
      try {
        await api.updateJob(jobId, {
          title: patch.title,
          description: patch.description,
          people_needed: patch.peopleNeeded
        });
        showToast('Job updated.');
      } catch (err) {
        showToast(jobErrorToast(err, 'Could not update job'));
      }
    }, refetchJobs);
  };

  const handleDeleteJob = (_eventId: string, jobId: string) => {
    syncApi(async () => {
      try {
        await api.deleteJob(jobId);
        showToast('Job deleted.');
      } catch (err) {
        showToast(jobErrorToast(err, 'Could not delete job'));
      }
    }, refetchJobs);
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

  const handleAssignSecurity = (eventId: string, memberId: string, memberName: string, station: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        const newAssignment: SecurityAssignment = {
          id: 'sec_' + Math.random().toString(36).substring(2, 9),
          memberId,
          memberName,
          station,
          status: 'Confirmed'
        };
        return {
          ...e,
          securityAssignments: [...(e.securityAssignments || []), newAssignment]
        };
      }
      return e;
    }));
    enqueueOutbox({
      type: 'SECURITY_ASSIGNED',
      recipient: memberName,
      message: `[GreekOS Security] You have been assigned to station: ${station}`,
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
    showToast(accept ? 'Accepted security shift swap.' : 'Declined shift swap.');
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
    handleEditJob,
    handleDeleteJob,
    handleSendEventNotifyBlast,
    handleToggleCheckInLink,
    handleAssignSecurity,
    handleRequestSecuritySwap,
    handleRespondSecuritySwap
  };
}
