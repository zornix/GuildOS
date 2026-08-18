import { useState } from 'react';
import { INITIAL_INITIATIVES } from '../data/mockData';
import { EventJob, Initiative, Member } from '../types';
import { api } from '../api';
import { adaptInitiatives } from '../adapters';
import { ShowToast } from './useToast';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  syncApi: SyncApi;
  showToast: ShowToast;
}

/** Chair-led initiatives and their claimable tasks. */
export function useInitiatives({ members, syncApi, showToast }: Deps) {
  const [initiatives, setInitiatives] = useState<Initiative[]>(INITIAL_INITIATIVES);

  const refetchInitiatives = async () =>
    setInitiatives(adaptInitiatives(await api.getInitiatives(), members));

  const handleAddInitiative = (newInit: Omit<Initiative, 'id'>) => {
    const init: Initiative = {
      ...newInit,
      id: 'init_' + Math.random().toString(36).substring(2, 9)
    };
    setInitiatives(prev => [init, ...prev]);
    syncApi(
      () =>
        api.createInitiative({
          title: init.title,
          description: init.description || null,
          date: init.startDate,
          // The prototype has no time-of-day for initiatives; the API requires one.
          time: '12:00:00',
          end_date: init.targetDate || null
        }),
      refetchInitiatives
    );
    showToast(`Launched chair initiative "${init.title}"`);
  };

  const handleAddJobToInitiative = (initId: string, jobData: Omit<EventJob, 'id' | 'claimants' | 'status'>) => {
    setInitiatives(prev => prev.map(i => {
      if (i.id === initId) {
        const newJob: EventJob = {
          ...jobData,
          id: 'ijob_' + Math.random().toString(36).substring(2, 9),
          claimants: [],
          status: 'To Do'
        };
        return { ...i, jobs: [...i.jobs, newJob] };
      }
      return i;
    }));
    showToast(`Added task to initiative.`);
  };

  const handleClaimInitiativeJob = (initId: string, jobId: string, memberId: string, memberName: string) => {
    setInitiatives(prev => prev.map(i => {
      if (i.id === initId) {
        return {
          ...i,
          jobs: i.jobs.map(j => {
            if (j.id === jobId && j.claimants.length < j.peopleNeeded) {
              return {
                ...j,
                claimants: [...j.claimants, { memberId, memberName, claimedAt: new Date().toISOString() }],
                status: 'In Progress'
              };
            }
            return j;
          })
        };
      }
      return i;
    }));
  };

  const handleUnclaimInitiativeJob = (initId: string, jobId: string, memberId: string) => {
    setInitiatives(prev => prev.map(i => {
      if (i.id === initId) {
        return {
          ...i,
          jobs: i.jobs.map(j => {
            if (j.id === jobId) {
              const remaining = j.claimants.filter(c => c.memberId !== memberId);
              return {
                ...j,
                claimants: remaining,
                status: remaining.length === 0 ? 'To Do' : j.status
              };
            }
            return j;
          })
        };
      }
      return i;
    }));
  };

  const handleReportInitiativeJobDone = (initId: string, jobId: string, memberName: string) => {
    setInitiatives(prev => prev.map(i => {
      if (i.id === initId) {
        return {
          ...i,
          jobs: i.jobs.map(j => {
            if (j.id === jobId) {
              return { ...j, status: 'Done Reported', reportedBy: memberName, reportedAt: new Date().toISOString() };
            }
            return j;
          })
        };
      }
      return i;
    }));
    showToast(`Reported initiative task complete!`);
  };

  const handleApproveInitiativeJob = (initId: string, jobId: string, approverName: string) => {
    setInitiatives(prev => prev.map(i => {
      if (i.id === initId) {
        return {
          ...i,
          jobs: i.jobs.map(j => {
            if (j.id === jobId) {
              return { ...j, status: 'Approved', approvedBy: approverName, approvedAt: new Date().toISOString() };
            }
            return j;
          })
        };
      }
      return i;
    }));
    showToast(`Chair sign-off confirmed.`);
  };

  return {
    initiatives,
    setInitiatives,
    handleAddInitiative,
    handleAddJobToInitiative,
    handleClaimInitiativeJob,
    handleUnclaimInitiativeJob,
    handleReportInitiativeJobDone,
    handleApproveInitiativeJob
  };
}
