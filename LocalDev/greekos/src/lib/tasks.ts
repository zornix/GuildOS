import type { Task } from '../types';

/** API commitments own capacity. Assignment is only a fallback for demo rows. */
export function taskClaimants(task: Task): NonNullable<Task['claimants']> {
  return task.claimants ?? (task.assignedToId
    ? [{ memberId: task.assignedToId, memberName: task.assignedTo, claimedAt: '' }]
    : []);
}

export function canClaimTask(task: Task, memberId: string | undefined): boolean {
  if (!memberId || !['To Do', 'Pending', 'In Progress'].includes(task.status)) return false;
  const claimants = taskClaimants(task);
  return !claimants.some(c => c.memberId === memberId)
    && Math.max(task.claimedCount ?? 0, claimants.length) < (task.peopleNeeded ?? 1);
}

export function isTaskComplete(task: Task): boolean {
  return ['Completed', 'Approved', 'Cancelled'].includes(task.status);
}
