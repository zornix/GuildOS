import { useState } from 'react';
import { ChapterEvent, EventJob, Member, SecurityAssignment } from '../types';
import { api } from '../api';
import { adaptCheckInLink, adaptEventDetail, adaptEvents, adaptSecurityAssignment, toEventBody } from '../adapters';
import { ShowToast } from './useToast';
import { SyncApi } from './useBackend';
import { describeError } from '../lib/sync';

/** 409 conflict tokens the jobs API raises, mapped to member-facing copy. */
const JOB_409: Record<string, string> = {
  job_not_editable: 'Job can no longer be edited',
  job_not_cancellable: 'Only unclaimed To-Do jobs can be deleted',
  job_capacity_below_claims: "Can't set spots below current claims",
  security_no_edit: 'Security shifts are managed from the Security panel',
  security_no_cancel: 'Security shifts are managed from the Security panel'
};

/** Refusals from the notify gate (409 completeness / recipients, 429 cooldown). */
const NOTIFY_409: Record<string, string> = {
  'not complete enough': 'Add a supervisor, an organizer and 3 jobs before notifying',
  'No SMS-reachable': 'No brother has a phone number on file to text',
  'count changed': 'The member list just changed — send the blast again',
  'within the last hour': 'This event was already notified in the last hour'
};

/** The swap RPC's 409 and the local pre-check read the same way. */
const SWAP_409: Record<string, string> = {
  swap_wrong_state: 'That swap request is no longer pending',
  'no longer pending': 'That swap request is no longer pending'
};

/** api.ts throws `Error('PATCH /path failed (409): <detail>')`, so the conflict
 *  token is matched inside the message rather than read off a field. */
const errorToast = (err: unknown, tokens: Record<string, string>, fallback: string) => {
  const msg = err instanceof Error ? err.message : '';
  const hit = Object.keys(tokens).find(token => msg.includes(token));
  return hit ? tokens[hit] : fallback;
};

interface Deps {
  members: Member[];
  syncApi: SyncApi;
  showToast: ShowToast;
  refetchJobs: () => Promise<void>;
}

/** Chapter events plus their claimable jobs and security shifts. */
export function useEvents({ members, syncApi, showToast, refetchJobs }: Deps) {
  const [events, setEvents] = useState<ChapterEvent[]>([]);

  // adaptEvents rebuilds rows with empty jobs, security and leader lists.
  // refetchJobs restamps the boards below; security shifts and everything that
  // only the detail endpoint carries (supervisors, organizers, notify stamp,
  // door code) load per event, so those are carried across rather than blanked.
  const refetchEvents = async () => {
    const rows = adaptEvents(await api.getEvents());
    setEvents(prev => {
      const byId = new Map<string, ChapterEvent>(prev.map(e => [e.id, e]));
      return rows.map(e => {
        const old = byId.get(e.id);
        return old ? {
          ...e,
          securityAssignments: old.securityAssignments,
          supervisors: old.supervisors,
          organizers: old.organizers,
          checkedInCount: old.checkedInCount,
          notifiedAt: old.notifiedAt,
          checkInToken: old.checkInToken,
          checkInLinkActive: old.checkInLinkActive
        } : e;
      });
    });
    await refetchJobs();
  };

  /** Supervisors, organizers, the notify stamp and the door code exist only
   *  on the per-event endpoints, so the selected event's row is patched here. */
  const refetchEventDetail = async (eventId: string) => {
    const [detail, link] = await Promise.all([api.getEvent(eventId), api.getCheckInLink(eventId)]);
    setEvents(prev => prev.map(e => e.id === eventId ? {
      ...e,
      ...adaptEventDetail(detail, members),
      ...adaptCheckInLink(link)
    } : e));
  };

  /** The events screen calls this whenever its selection lands on an event; a
   *  failure just leaves that row showing what it already had. */
  const handleSelectEvent = (eventId: string) => {
    refetchEventDetail(eventId).catch(err => console.error(`Event detail load failed for ${eventId}`, err));
  };

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
  const syncSwap = (eventId: string, call: () => Promise<unknown>, successMessage: string) =>
    syncApi(call, () => refetchSecurity(eventId), {
      onSuccess: () => showToast(successMessage),
      onError: err => showToast(errorToast(err, SWAP_409, describeError(err)))
    });

  const handleAddEvent = (newEvent: Omit<ChapterEvent, 'id' | 'attendanceTaken' | 'checkedInCount'>) => {
    const ev: ChapterEvent = {
      ...newEvent,
      id: 'e_' + Math.random().toString(36).substring(2, 9),
      attendanceTaken: false,
      checkedInCount: 0,
      // A fresh event has no check-in link until an officer opens the door.
      checkInLinkActive: false,
      securityAssignments: []
    };
    setEvents(prev => [ev, ...prev]);
    syncApi(() => api.createEvent(toEventBody(ev)), refetchEvents, `Created chapter event "${ev.title}"`);
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
          return {
            ...e,
            organizers: [...currentOrgs, memberName],
            organizerCount: (e.organizerCount || currentOrgs.length) + 1
          };
        }
      }
      return e;
    }));
    // The backend signs up the signed-in member; it has no impersonation concept.
    syncApi(() => api.addOrganizer(eventId), () => refetchEventDetail(eventId), 'Volunteered as Organizer for event!');
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
    syncApi(() => api.commitTask(jobId), refetchJobs, 'Claimed job successfully!');
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
    syncApi(() => api.uncommitTask(jobId), refetchJobs, 'Unclaimed job.');
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
    syncApi(() => api.reportJobDone(jobId), refetchJobs, 'Reported job complete! Awaiting supervisor sign-off.');
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
    syncApi(() => api.approveJob(jobId), refetchJobs, 'Job approved and verified by supervisor.');
  };

  const handleRejectJob = (eventId: string, jobId: string, officerName: string, reason: string) => {
    setEvents(prev => prev.map(e => {
      if (e.id === eventId) {
        return {
          ...e,
          jobs: e.jobs.map(j => {
            if (j.id === jobId) {
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
    syncApi(() => api.rejectJob(jobId, reason), refetchJobs, 'Job returned with feedback.');
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
      refetchJobs,
      'Added job to event.'
    );
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
        showToast(errorToast(err, JOB_409, 'Could not update job'));
      }
    }, refetchJobs);
  };

  const handleDeleteJob = (_eventId: string, jobId: string) => {
    syncApi(async () => {
      try {
        await api.deleteJob(jobId);
        showToast('Job deleted.');
      } catch (err) {
        showToast(errorToast(err, JOB_409, 'Could not delete job'));
      }
    }, refetchJobs);
  };

  const handleSendEventNotifyBlast = (eventId: string) => {
    const ev = events.find(e => e.id === eventId);
    if (!ev) return;

    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, notifiedAt: new Date().toISOString() } : e));
    // The refetch replaces the optimistic stamp with last_notified_at.
    syncApi(async () => {
      try {
        // Two-phase confirm: send back the count the preview just resolved.
        const preview = await api.notifyPreview(eventId);
        await api.notifyEvent(eventId, preview.recipient_count);
        // Say who was dropped, or the officer just sees a smaller blast (#89).
        const skipped = [
          preview.no_phone_count && `${preview.no_phone_count} without a phone`,
          preview.no_consent_count && `${preview.no_consent_count} without SMS consent`
        ].filter(Boolean).join(', ');
        showToast(
          `Notification blast sent to the chapter.${skipped ? ` Skipped ${skipped}.` : ''}`
        );
      } catch (err) {
        showToast(errorToast(err, NOTIFY_409, 'Could not send the notification blast'));
      }
    }, () => refetchEventDetail(eventId));
  };

  /** Opening the door creates a short-lived check-in link; closing it kills it. */
  const handleToggleCheckInLink = (eventId: string) => {
    const wasActive = !!events.find(e => e.id === eventId)?.checkInLinkActive;
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, checkInLinkActive: !wasActive } : e));
    syncApi(
      () => wasActive ? api.closeCheckInLink(eventId) : api.openCheckInLink(eventId),
      () => refetchEventDetail(eventId)
    );
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
    syncApi(() => api.assignSecurity(eventId, memberId), () => refetchSecurity(eventId), `Assigned ${memberName} to security shift.`);
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
    syncSwap(eventId, () => api.requestSwap(eventId, assignmentId, targetMemberId), `Shift swap request sent to ${targetMemberName}.`);
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
    }, accept ? 'Accepted security shift swap.' : 'Declined shift swap.');
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
    }, 'Cancelled your shift swap request.');
  };

  return {
    events,
    setEvents,
    refetchEvents,
    handleSelectEvent,
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
    handleRespondSecuritySwap,
    handleCancelSecuritySwap
  };
}
