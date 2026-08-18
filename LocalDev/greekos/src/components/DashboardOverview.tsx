import React from 'react';
import { 
  Users, 
  Calendar, 
  DollarSign, 
  CheckSquare, 
  AlertTriangle, 
  Sparkles, 
  ArrowUpRight, 
  Shield, 
  UserCheck, 
  Send, 
  CheckCircle2, 
  Clock,
  TrendingUp,
  Megaphone,
  CreditCard,
  QrCode,
  X
} from 'lucide-react';
import { ChapterEvent, Member, Task, Fine, Initiative, Announcement, LedgerEntry } from '../types';
import Card from './ui/Card';
import { formatMoney } from '../formatters';

interface DashboardOverviewProps {
  members: Member[];
  events: ChapterEvent[];
  tasks: Task[];
  fines: Fine[];
  initiatives: Initiative[];
  announcements: Announcement[];
  ledger: LedgerEntry[];
  isOfficer: boolean;
  currentMemberName: string;
  onNavigateTab: (tab: string) => void;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onPayDuesQuick: () => void;
  onDeleteAnnouncement: (announcementId: string) => void;
}

export default function DashboardOverview({
  members,
  events,
  tasks,
  fines,
  initiatives,
  announcements,
  ledger,
  isOfficer,
  currentMemberName,
  onNavigateTab,
  onVolunteerOrganizer,
  onPayDuesQuick,
  onDeleteAnnouncement
}: DashboardOverviewProps) {
  const safeMembers = members || [];
  const safeEvents = events || [];
  const safeTasks = tasks || [];
  const safeInitiatives = initiatives || [];
  const safeAnnouncements = announcements || [];
  const safeLedger = ledger || [];

  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  // Computations
  const totalReceivablesCents = safeMembers.reduce((sum, m) => sum + (m.duesBalanceCents || Math.round((m.duesBalance || 0) * 100)), 0);
  const avgAttendance = Math.round(safeMembers.reduce((sum, m) => sum + (m.attendanceRate || 0), 0) / (safeMembers.length || 1));
  const activeMembersCount = safeMembers.filter(m => m.role !== 'Pledge' && m.role !== 'Alumni').length;
  const pendingTasks = safeTasks.filter(t => t.status !== 'Completed').length;
  const upcomingEvents = safeEvents.slice(0, 3);
  
  // Pending officer sign-offs
  const pendingJobSignOffs = safeEvents.flatMap(e => 
    (e.jobs || []).filter(j => j.status === 'Done Reported').map(j => ({ event: e, job: j }))
  );

  return (
    <div className="space-y-6">
      {/* Top Banner: Member Context & Standing */}
      <div className="bg-navy text-white rounded-2xl p-6 shadow-md border border-[#1e2d42] flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold bg-gold text-navy px-2.5 py-0.5 rounded">
              {currentMember?.role || 'Brother'}
            </span>
            <span className="text-xs font-mono text-slate-300">
              {currentMember?.standing || 'Good Standing'}
            </span>
          </div>
          <h1 className="text-2xl font-display font-extrabold text-white tracking-tight">
            Welcome back, {currentMemberName}
          </h1>
          <p className="text-xs text-slate-300">
            Alpha Chapter &bull; Fall 2026 Academic Term &bull; 42 Brothers Active
          </p>
        </div>

        {/* Quick Brother Actions */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => onNavigateTab('command')}
            className="bg-slate-800 hover:bg-slate-700 text-gold font-bold text-xs px-4 py-2.5 rounded-lg border border-slate-700 transition-all flex items-center gap-2 cursor-pointer shadow-xs"
          >
            <Sparkles className="w-4 h-4 text-gold" />
            Natural Command Line
          </button>

          {!isOfficer && currentMember && currentMember.duesBalance > 0 && (
            <button
              onClick={onPayDuesQuick}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 rounded-lg transition-all flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <CreditCard className="w-4 h-4" />
              Pay Balance (${currentMember.duesBalance})
            </button>
          )}

          {isOfficer && (
            <button
              onClick={() => onNavigateTab('events')}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 rounded-lg transition-all flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <Calendar className="w-4 h-4" />
              Schedule Event
            </button>
          )}
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold font-mono uppercase tracking-wider text-slate-500">Active Roster</span>
            <Users className="w-4 h-4 text-blue-600" />
          </div>
          <div className="text-2xl font-display font-black text-slate-900">{activeMembersCount}</div>
          <div className="text-[10px] text-slate-400 font-mono">100% Initiation Verified</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold font-mono uppercase tracking-wider text-slate-500">Avg Attendance</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-2xl font-display font-black text-emerald-600">{avgAttendance}%</div>
          <div className="text-[10px] text-emerald-700/80 font-mono">+4% vs previous semester</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold font-mono uppercase tracking-wider text-slate-500">Chapter Receivables</span>
            <DollarSign className="w-4 h-4 text-amber-600" />
          </div>
          <div className="text-2xl font-display font-black text-slate-900">
            {formatMoney(totalReceivablesCents)}
          </div>
          <div className="text-[10px] text-slate-400 font-mono">Across {members.length} brothers</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold font-mono uppercase tracking-wider text-slate-500">Open Chores / Tasks</span>
            <CheckSquare className="w-4 h-4 text-purple-600" />
          </div>
          <div className="text-2xl font-display font-black text-slate-900">{pendingTasks}</div>
          <div className="text-[10px] text-purple-700/80 font-mono">House & officer duties</div>
        </div>
      </div>

      {/* Officer Alert: Pending Job Sign-offs */}
      {isOfficer && pendingJobSignOffs.length > 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-200/80 flex items-center justify-center text-amber-900 shrink-0">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h4 className="font-bold text-xs text-amber-950 font-mono uppercase">
                {pendingJobSignOffs.length} Event Job{pendingJobSignOffs.length > 1 ? 's' : ''} Awaiting Supervisor Sign-Off
              </h4>
              <p className="text-xs text-amber-900">
                Brothers have completed duties on site and reported done. Review and approve or provide feedback.
              </p>
            </div>
          </div>

          <button
            onClick={() => onNavigateTab('events')}
            className="text-xs bg-navy hover:bg-slate-800 text-gold font-bold px-3.5 py-2 rounded-lg transition-all cursor-pointer shrink-0"
          >
            Review Jobs in Events
          </button>
        </div>
      )}

      {/* Main Grid: Upcoming Events & Chapter Initiatives */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left 2 Cols: Upcoming Chapter Operations */}
        <div className="lg:col-span-2 space-y-4">
          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-gold" />
                  Upcoming Chapter Operations
                </h3>
                <p className="text-xs text-slate-500">Upcoming mandatory meetings, brotherhood, and service events.</p>
              </div>

              <button
                onClick={() => onNavigateTab('events')}
                className="text-xs font-semibold text-navy hover:text-gold-muted flex items-center gap-1 cursor-pointer"
              >
                View All Events &rarr;
              </button>
            </div>

            {/* Event cards */}
            <div className="space-y-3">
              {upcomingEvents.map(event => {
                const orgs = event.organizers || [];
                const hasNoOrganizers = orgs.length === 0;
                const eventJobs = event.jobs || [];
                const openJobs = eventJobs.filter(j => (j.claimants || []).length < (j.peopleNeeded || 1)).length;

                return (
                  <div 
                    key={event.id}
                    className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-gold transition-all space-y-2"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono font-bold uppercase text-gold-muted bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">
                            {event.type}
                          </span>
                          {event.required && (
                            <span className="text-[9px] font-mono font-extrabold uppercase bg-red-50 text-red-700 px-1.5 py-0.5 rounded border border-red-200">
                              Mandatory
                            </span>
                          )}
                        </div>
                        <h4 className="font-bold text-sm text-slate-900">{event.title}</h4>
                      </div>

                      <div className="text-right text-xs text-slate-500 font-mono">
                        <span className="font-bold text-slate-800 block">{event.date}</span>
                        <span>{event.time}</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/60">
                      <div className="flex flex-wrap items-center gap-2">
                        {hasNoOrganizers ? (
                          <span className="text-[10px] font-mono font-bold bg-red-100 text-red-800 px-2 py-0.5 rounded flex items-center gap-1 animate-pulse">
                            <AlertTriangle className="w-3 h-3 text-red-600" />
                            Organizers Needed!
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                            Chairs: {orgs.join(', ')}
                          </span>
                        )}

                        {openJobs > 0 && (
                          <span className="text-[10px] font-mono text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                            {openJobs} Open Job{openJobs > 1 ? 's' : ''}
                          </span>
                        )}
                      </div>

                      {hasNoOrganizers && (
                        <button
                          onClick={() => onVolunteerOrganizer(event.id, currentMemberName)}
                          className="text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-2.5 py-1 rounded-md transition-all cursor-pointer shadow-2xs"
                        >
                          Volunteer as Organizer
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Chair Initiatives Strip */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-600" />
                Active Committee Initiatives
              </h3>
              <button
                onClick={() => onNavigateTab('initiatives')}
                className="text-xs font-semibold text-purple-700 hover:text-purple-900 cursor-pointer"
              >
                All Initiatives &rarr;
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {safeInitiatives.map(init => (
                <div key={init.id} className="p-3 bg-purple-50/40 rounded-xl border border-purple-100 space-y-1.5">
                  <div className="flex justify-between items-start">
                    <span className="text-[10px] font-mono font-bold text-purple-800 bg-purple-100 px-2 py-0.5 rounded">
                      {init.category}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">Target: {(init.targetDate || '').substring(5)}</span>
                  </div>
                  <h4 className="font-bold text-xs text-slate-900">{init.title}</h4>
                  <p className="text-[11px] text-slate-500 line-clamp-1">{init.description}</p>
                  <span className="text-[10px] font-mono text-purple-700 block font-semibold">
                    Leads: {(init.leadChairs || []).join(', ')}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Right 1 Col: Broadcasts & Chapter Feed */}
        <div className="space-y-4">
          {/* Executive Announcements */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
                <Megaphone className="w-4 h-4 text-blue-600" />
                Executive Chapter Broadcasts
              </h3>
            </div>

            <div className="space-y-3">
              {safeAnnouncements.map(a => (
                <div key={a.id} className="p-3 bg-blue-50/50 rounded-xl border border-blue-100 space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-xs text-blue-950">{a.title}</span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] font-mono bg-blue-200 text-blue-900 px-1.5 rounded font-bold">
                        {a.priority}
                      </span>
                      {isOfficer && (
                        <button
                          onClick={() => onDeleteAnnouncement(a.id)}
                          title="Remove from calendar"
                          aria-label={`Remove announcement "${a.title}" from calendar`}
                          className="text-blue-400 hover:text-red-600 cursor-pointer"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-blue-900 leading-relaxed">{a.content}</p>
                  <div className="text-[10px] text-blue-600 font-mono pt-1">
                    {a.date} &bull; {a.author}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Quick House Chores */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
                <CheckSquare className="w-4 h-4 text-gold" />
                House Duties & Chores
              </h3>
              <button
                onClick={() => onNavigateTab('tasks')}
                className="text-xs font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
              >
                View &rarr;
              </button>
            </div>

            <div className="space-y-2">
              {safeTasks.slice(0, 3).map(task => (
                <div key={task.id} className="p-2.5 rounded-lg border border-slate-100 bg-slate-50 flex items-center justify-between text-xs">
                  <div>
                    <div className="font-bold text-slate-800">{task.title}</div>
                    <div className="text-[10px] text-slate-400 font-mono">Assigned: {task.assignedTo}</div>
                  </div>
                  <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    task.status === 'Completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                  }`}>
                    {task.status}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>

      </div>
    </div>
  );
}
