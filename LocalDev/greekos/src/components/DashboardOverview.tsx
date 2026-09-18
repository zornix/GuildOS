import React, { useState } from 'react';
import { AlertTriangle, Calendar, CheckSquare, Clock, Megaphone, Sparkles, X } from 'lucide-react';
import { ChapterEvent, Member, Task, Initiative, Announcement } from '../types';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';
import { isoDay } from '../formatters';
import type { ContributionRecord } from '../lib/contribution';
import type { MemberBalance } from '../lib/balance';
import { liveDoorEvent } from '../lib/events';
import { isTaskComplete } from '../lib/tasks';
import WelcomeBanner from './home/WelcomeBanner';
import MyRecord from './home/MyRecord';
import SmsConsentCard from './home/SmsConsentCard';

interface DashboardOverviewProps {
  members: Member[];
  events: ChapterEvent[];
  tasks: Task[];
  initiatives: Initiative[];
  announcements: Announcement[];
  isOfficer: boolean;
  currentMemberId: string;
  currentMemberName: string;
  contribution: ContributionRecord;
  myBalance: MemberBalance | null;
  onNavigateTab: (tab: string) => void;
  onOpenEvent: (eventId: string) => void;
  onScheduleEvent: () => void;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
  onDeleteAnnouncement: (announcementId: string) => void;
}

const TILE_LIMIT = 3;

function TileHeader({ icon, title, onAll, allLabel }: { icon: React.ReactNode; title: string; onAll: () => void; allLabel: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-2">
      <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
        {icon}
        {title}
      </h3>
      <button type="button" onClick={onAll} className="text-xs font-semibold text-navy hover:text-gold-muted cursor-pointer">
        {allLabel} &rarr;
      </button>
    </div>
  );
}

/** Home: welcome banner over four content tiles. No chapter KPIs, no ranking. */
export default function DashboardOverview({
  members, events, tasks, initiatives, announcements, isOfficer, currentMemberId, currentMemberName,
  contribution, myBalance, onNavigateTab, onOpenEvent, onScheduleEvent,
  onVolunteerOrganizer, onSelfCheckIn, onDeleteAnnouncement
}: DashboardOverviewProps) {
  const safeMembers = members || [];
  const safeEvents = events || [];
  const safeTasks = tasks || [];
  const safeInitiatives = initiatives || [];
  const safeAnnouncements = announcements || [];

  const [pendingDelete, setPendingDelete] = useState<Announcement | null>(null);

  const currentMember = safeMembers.find(m => m.id === currentMemberId);
  const today = isoDay();
  const upcomingEvents = safeEvents.filter(e => e.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, TILE_LIMIT);
  const pendingJobSignOffs = safeEvents.flatMap(e => (e.jobs || []).filter(j => j.status === 'Done Reported'));
  const openTasks = safeTasks.filter(t => !isTaskComplete(t));

  return (
    <div className="space-y-6">
      <WelcomeBanner
        member={currentMember}
        currentMemberName={currentMemberName}
        memberCount={safeMembers.length}
        isOfficer={isOfficer}
        contribution={contribution}
        myBalance={myBalance}
        liveDoorEvent={liveDoorEvent(safeEvents, today)}
        onScheduleEvent={onScheduleEvent}
        onOpenTreasury={() => onNavigateTab('finance')}
        onOpenAttendance={() => onNavigateTab('attendance')}
        onSelfCheckIn={onSelfCheckIn}
      />

      <MyRecord record={contribution} />

      {/* Only once the roster has loaded: an absent row would render "off" for
          a member who has in fact opted in. */}
      {currentMember && <SmsConsentCard consented={currentMember.smsConsent === true} />}

      {isOfficer && pendingJobSignOffs.length > 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-3">
            <Clock className="w-5 h-5 text-amber-900 shrink-0" />
            <p className="text-xs text-amber-950">
              <strong>{pendingJobSignOffs.length} job{pendingJobSignOffs.length > 1 ? 's' : ''} reported done</strong> and waiting for your sign-off.
            </p>
          </div>
          <button type="button" onClick={() => onNavigateTab('events')} className="text-xs bg-navy hover:bg-slate-800 text-gold font-bold px-3.5 py-2 rounded-lg cursor-pointer shrink-0">
            Review in Events
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upcoming events */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<Calendar className="w-4 h-4 text-gold" />} title="Upcoming events" onAll={() => onNavigateTab('events')} allLabel="All events" />
          {upcomingEvents.length === 0 && <p className="text-xs text-slate-500">No upcoming events.</p>}
          {upcomingEvents.map(event => {
            const orgCount = event.organizerCount ?? (event.organizers || []).length;
            const openJobs = event.openJobCount || 0;
            return (
              <div key={event.id} className="p-3 rounded-xl border border-slate-200/90 bg-slate-50/50 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <button type="button" onClick={() => onOpenEvent(event.id)} className="text-left font-bold text-sm text-slate-900 hover:text-navy cursor-pointer">
                    {event.title}
                  </button>
                  <span className="text-xs text-slate-500 text-right shrink-0">{event.date}<br />{event.time}</span>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-bold text-amber-900 bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">{event.type}</span>
                  {event.required && <span className="text-xs font-extrabold bg-red-50 text-red-700 px-1.5 py-0.5 rounded border border-red-200">Mandatory</span>}
                  {orgCount === 0 ? (
                    <span className="text-xs font-semibold bg-red-100 text-red-800 px-2 py-0.5 rounded flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3 text-red-600" /> Organizers needed
                    </span>
                  ) : (
                    <span className="text-xs text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                      {orgCount} organizer{orgCount > 1 ? 's' : ''}
                    </span>
                  )}
                  {openJobs > 0 && <span className="text-xs text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">{openJobs} open job{openJobs > 1 ? 's' : ''}</span>}
                  {orgCount === 0 && (
                    <button type="button" onClick={() => onVolunteerOrganizer(event.id, currentMemberName)} className="ml-auto text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-2.5 py-1 rounded-md cursor-pointer">
                      Volunteer as organizer
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </Card>

        {/* Announcements */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<Megaphone className="w-4 h-4 text-blue-600" />} title="Announcements" onAll={() => onNavigateTab('events')} allLabel="Calendar" />
          {safeAnnouncements.length === 0 && <p className="text-xs text-slate-500">No announcements yet.</p>}
          {safeAnnouncements.slice(0, TILE_LIMIT).map(a => (
            <div key={a.id} className="p-3 bg-blue-50/50 rounded-xl border border-blue-100 space-y-1">
              <div className="flex justify-between items-center gap-2">
                <span className="font-bold text-xs text-blue-950">{a.title}</span>
                {isOfficer && (
                  <button
                    type="button"
                    onClick={() => setPendingDelete(a)}
                    aria-label={`Remove announcement "${a.title}" from calendar`}
                    className="text-blue-400 hover:text-red-600 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <p className="text-xs text-blue-900 leading-relaxed">{a.content}</p>
              <div className="text-xs text-blue-600">{a.date} &bull; {a.author}</div>
            </div>
          ))}
        </Card>

        {/* Jobs */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<CheckSquare className="w-4 h-4 text-gold" />} title="Jobs" onAll={() => onNavigateTab('tasks')} allLabel="All jobs" />
          {openTasks.length === 0 && <p className="text-xs text-slate-500">No jobs yet.</p>}
          {openTasks.slice(0, TILE_LIMIT).map(task => (
            <div key={task.id} className="p-2.5 rounded-lg border border-slate-100 bg-slate-50 flex items-center justify-between text-xs gap-2">
              <div>
                <div className="font-bold text-slate-800">{task.title}</div>
                <div className="text-xs text-slate-500">{task.assignedTo}{task.parent && <> · {task.parent.title}</>}</div>
              </div>
              <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 shrink-0">{task.status}</span>
            </div>
          ))}
        </Card>

        {/* Initiatives */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<Sparkles className="w-4 h-4 text-purple-600" />} title="Initiatives" onAll={() => onNavigateTab('initiatives')} allLabel="All initiatives" />
          {safeInitiatives.length === 0 && <p className="text-xs text-slate-500">No initiatives yet.</p>}
          {safeInitiatives.slice(0, TILE_LIMIT).map(init => (
            <div key={init.id} className="p-3 bg-purple-50/40 rounded-xl border border-purple-100 space-y-1">
              <div className="flex justify-between items-start gap-2">
                <h4 className="font-bold text-xs text-slate-900">{init.title}</h4>
                <span className="text-xs text-slate-500 shrink-0">Target {(init.targetDate || '').substring(5)}</span>
              </div>
              <p className="text-xs text-slate-500 line-clamp-1">{init.description}</p>
              <span className="text-xs text-purple-700 block font-semibold">Chairs: {(init.leadChairs || []).join(', ')}</span>
            </div>
          ))}
        </Card>
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Remove announcement?"
          tone="danger"
          body={<p>"<strong>{pendingDelete.title}</strong>" comes off the calendar for everyone. Already-sent messages are not recalled.</p>}
          confirmLabel="Remove"
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => { onDeleteAnnouncement(pendingDelete.id); setPendingDelete(null); }}
        />
      )}
    </div>
  );
}
