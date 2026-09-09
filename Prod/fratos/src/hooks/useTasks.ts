import { useState } from 'react';
import { Task } from '../types';
import { api } from '../api';
import { canClaimTask, taskClaimants } from '../lib/tasks';
import { ShowToast } from './useToast';
import { SyncApi } from './useBackend';

interface Deps {
  syncApi: SyncApi;
  showToast: ShowToast;
  refetchJobs: () => Promise<void>;
}

/** Jobs: standalone or attached to an event or initiative. */
export function useTasks({ syncApi, showToast, refetchJobs }: Deps) {
  const [tasks, setTasks] = useState<Task[]>([]);

  const handleAddTask = (newTask: Omit<Task, 'id' | 'status'>) => {
    const t: Task = {
      ...newTask,
      id: 't_' + Math.random().toString(36).substring(2, 9),
      status: 'To Do'
    };
    setTasks(prev => [t, ...prev]);
    syncApi(
      () =>
        api.createTask({
          title: t.title,
          description: t.description || null,
          assigned_member_id: t.assignedToId || null,
          required: t.priority === 'High' || t.priority === 'Urgent',
          due_at: t.dueDate ? `${t.dueDate}T12:00:00Z` : null
        }),
      refetchJobs
    );
    showToast(`Added job "${t.title}"`);
  };

  const handleToggleTaskStatus = (taskId: string) => {
    const current = tasks.find(t => t.id === taskId);
    if (!current || current.parent || ['Done Reported', 'Approved', 'Cancelled', 'Unknown'].includes(current.status)) return;
    const nextStatus = current && current.status === 'Completed' ? 'To Do' : 'Completed';
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: nextStatus } : t));
    syncApi(() => api.setTaskStatus(taskId, nextStatus === 'Completed' ? 'done' : 'open'), refetchJobs);
  };

  const handleClaimTask = (taskId: string, memberName: string, memberId: string) => {
    const current = tasks.find(t => t.id === taskId);
    if (!current || !canClaimTask(current, memberId)) return;
    setTasks(prev => prev.map(t => {
      if (t.id === taskId) {
        const claimants = [...taskClaimants(t), { memberId, memberName, claimedAt: new Date().toISOString() }];
        return { ...t, claimants, claimedCount: Math.max(t.claimedCount ?? 0, claimants.length - 1) + 1,
          assignedTo: claimants.map(c => c.memberName).join(', '), status: 'In Progress' };
      }
      return t;
    }));
    syncApi(() => api.commitTask(taskId, memberId), refetchJobs, {
      onSuccess: () => showToast('Claimed job.')
    });
  };

  return { tasks, setTasks, handleAddTask, handleToggleTaskStatus, handleClaimTask };
}
