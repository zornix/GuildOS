import { useState } from 'react';
import { INITIAL_TASKS } from '../data/mockData';
import { Member, Task } from '../types';
import { api } from '../api';
import { adaptTasks } from '../adapters';
import { ShowToast } from './useToast';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  syncApi: SyncApi;
  showToast: ShowToast;
  titles: () => { events: Map<string, string>; initiatives: Map<string, string> };
}

/** Jobs: standalone or attached to an event or initiative. */
export function useTasks({ members, syncApi, showToast, titles }: Deps) {
  const [tasks, setTasks] = useState<Task[]>(INITIAL_TASKS);

  const refetchTasks = async () => setTasks(adaptTasks(await api.getTasks(), members, titles()));

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
      refetchTasks
    );
    showToast(`Added job "${t.title}"`);
  };

  const handleToggleTaskStatus = (taskId: string) => {
    const current = tasks.find(t => t.id === taskId);
    const nextStatus = current && current.status === 'Completed' ? 'To Do' : 'Completed';
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: nextStatus } : t));
    syncApi(() => api.setTaskStatus(taskId, nextStatus === 'Completed' ? 'done' : 'open'), refetchTasks);
  };

  const handleClaimTask = (taskId: string, memberName: string, memberId: string) => {
    setTasks(prev => prev.map(t => {
      if (t.id === taskId) {
        return { ...t, assignedTo: memberName, assignedToId: memberId, status: 'In Progress' };
      }
      return t;
    }));
    syncApi(() => api.commitTask(taskId, memberId), refetchTasks);
    showToast(`Claimed job.`);
  };

  return { tasks, setTasks, handleAddTask, handleToggleTaskStatus, handleClaimTask };
}
