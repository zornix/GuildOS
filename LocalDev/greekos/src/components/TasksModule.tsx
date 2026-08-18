import React, { useState } from 'react';
import { 
  CheckSquare, 
  Plus, 
  Clock, 
  User, 
  CheckCircle2, 
  AlertCircle, 
  Calendar 
} from 'lucide-react';
import { Task, Member } from '../types';
import Modal from './ui/Modal';

interface TasksModuleProps {
  tasks: Task[];
  members: Member[];
  isOfficer: boolean;
  currentMemberName: string;
  onAddTask: (task: Omit<Task, 'id' | 'status'>) => void;
  onToggleTaskStatus: (taskId: string) => void;
  onClaimTask: (taskId: string, memberName: string, memberId: string) => void;
}

export default function TasksModule({
  tasks,
  members,
  isOfficer,
  currentMemberName,
  onAddTask,
  onToggleTaskStatus,
  onClaimTask
}: TasksModuleProps) {
  const safeTasks = tasks || [];
  const safeMembers = members || [];

  const [filterPriority, setFilterPriority] = useState<string>('ALL');
  const [showAddModal, setShowAddModal] = useState(false);

  // New Task Form
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [assignedToId, setAssignedToId] = useState(safeMembers[0]?.id || '');
  const [dueDate, setDueDate] = useState('2026-07-16');
  const [priority, setPriority] = useState<Task['priority']>('Medium');

  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  const filteredTasks = safeTasks.filter(t => {
    if (filterPriority !== 'ALL' && t.priority !== filterPriority) return false;
    return true;
  });

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const assignedMem = safeMembers.find(m => m.id === assignedToId);
    onAddTask({
      title,
      description,
      assignedTo: assignedMem ? assignedMem.name : 'Unassigned',
      assignedToId: assignedMem ? assignedMem.id : undefined,
      dueDate,
      priority
    });

    setTitle('');
    setDescription('');
    setShowAddModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <CheckSquare className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              House Duties & Officer Chores
            </h2>
            <span className="text-xs font-mono font-bold bg-navy text-gold px-2 py-0.5 rounded-full">
              {tasks.filter(t => t.status === 'Pending').length} Pending
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Weekly chore assignments, house manager work orders, and committee task boards.
          </p>
        </div>

        {isOfficer && (
          <button
            onClick={() => setShowAddModal(true)}
            className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Assign House Task
          </button>
        )}
      </div>

      {/* Filter Ribbon */}
      <div className="flex items-center gap-2 text-xs font-mono">
        <span className="text-slate-400 font-bold uppercase">Priority:</span>
        {['ALL', 'Urgent', 'High', 'Medium', 'Low'].map(p => (
          <button
            key={p}
            onClick={() => setFilterPriority(p)}
            className={`px-2.5 py-1 rounded-md font-semibold cursor-pointer transition-all ${
              filterPriority === p ? 'bg-navy text-gold' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Tasks Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredTasks.map(task => {
          const isDone = task.status === 'Completed';
          const isMyTask = task.assignedTo === currentMemberName;

          return (
            <div
              key={task.id}
              className={`p-4 rounded-xl border transition-all space-y-3 ${
                isDone 
                  ? 'bg-slate-50 border-slate-200 opacity-75' 
                  : 'bg-white border-slate-200 hover:border-gold shadow-xs'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className={`text-[9px] font-mono font-bold uppercase px-2 py-0.5 rounded ${
                  task.priority === 'Urgent' 
                    ? 'bg-red-100 text-red-800' 
                    : task.priority === 'High' 
                    ? 'bg-amber-100 text-amber-800' 
                    : 'bg-blue-100 text-blue-800'
                }`}>
                  {task.priority} Priority
                </span>

                <button
                  onClick={() => onToggleTaskStatus(task.id)}
                  className={`text-xs font-mono font-bold px-2 py-0.5 rounded flex items-center gap-1 cursor-pointer transition-all ${
                    isDone 
                      ? 'bg-emerald-100 text-emerald-800' 
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <CheckCircle2 className="w-3 h-3" />
                  {task.status}
                </button>
              </div>

              <div>
                <h4 className={`font-bold text-sm text-slate-900 ${isDone ? 'line-through text-slate-500' : ''}`}>
                  {task.title}
                </h4>
                <p className="text-xs text-slate-600 mt-1">{task.description}</p>
              </div>

              <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs font-mono text-slate-500">
                <span className="flex items-center gap-1">
                  <User className="w-3 h-3 text-slate-400" />
                  <strong className={isMyTask ? 'text-gold-muted' : 'text-slate-700'}>{task.assignedTo}</strong>
                </span>

                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3 text-slate-400" />
                  {task.dueDate}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* MODAL: Assign Task */}
      {showAddModal && (
        <Modal>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <CheckSquare className="w-5 h-5 text-gold" />
                Assign House Duty or Chore
              </h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-600 font-bold">✕</button>
            </div>

            <form onSubmit={handleAddSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Task Title</label>
                <input
                  type="text"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="e.g. Kitchen Trash & Recycling Empty"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Instructions</label>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="e.g. Empty all 3 bins, wipe counter, and take bags to outer dumpster."
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Assign Brother</label>
                  <select
                    value={assignedToId}
                    onChange={e => setAssignedToId(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    {members.map(m => (
                      <option key={m.id} value={m.id}>{m.name} ({m.role})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Priority</label>
                  <select
                    value={priority}
                    onChange={e => setPriority(e.target.value as any)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Urgent">Urgent</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Due Date</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={e => setDueDate(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 rounded-lg text-xs uppercase tracking-wider transition-all"
              >
                Assign Task
              </button>
            </form>
        </Modal>
      )}
    </div>
  );
}
