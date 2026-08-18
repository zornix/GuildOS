import React, { useState } from 'react';
import { 
  Calendar, 
  MapPin, 
  Clock, 
  Plus, 
  Shield, 
  UserCheck, 
  AlertTriangle, 
  CheckCircle2, 
  Send, 
  QrCode, 
  KeyRound, 
  ArrowLeftRight, 
  Lock, 
  Info,
  XCircle,
  Sparkles
} from 'lucide-react';
import { ChapterEvent, EventJob, Member, SecurityAssignment, EventType } from '../types';
import Modal from './ui/Modal';
import Card from './ui/Card';

interface EventsModuleProps {
  events: ChapterEvent[];
  members: Member[];
  isOfficer: boolean;
  currentMemberName: string;
  onAddEvent: (event: Omit<ChapterEvent, 'id' | 'attendanceTaken' | 'checkedInCount'>) => void;
  onUpdateEvent: (event: ChapterEvent) => void;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onClaimJob: (eventId: string, jobId: string, memberId: string, memberName: string) => void;
  onUnclaimJob: (eventId: string, jobId: string, memberId: string) => void;
  onReportJobDone: (eventId: string, jobId: string, memberName: string) => void;
  onApproveJob: (eventId: string, jobId: string, officerName: string) => void;
  onRejectJob: (eventId: string, jobId: string, officerName: string, reason: string) => void;
  onAddJobToEvent: (eventId: string, job: Omit<EventJob, 'id' | 'claimants' | 'status'>) => void;
  onSendEventNotifyBlast: (eventId: string) => void;
  onToggleCheckInLink: (eventId: string) => void;
  onAssignSecurity: (eventId: string, memberId: string, memberName: string, station: string) => void;
  onRequestSecuritySwap: (eventId: string, assignmentId: string, targetMemberId: string, targetMemberName: string) => void;
  onRespondSecuritySwap: (eventId: string, assignmentId: string, accept: boolean) => void;
}

export default function EventsModule({
  events,
  members,
  isOfficer,
  currentMemberName,
  onAddEvent,
  onUpdateEvent,
  onVolunteerOrganizer,
  onClaimJob,
  onUnclaimJob,
  onReportJobDone,
  onApproveJob,
  onRejectJob,
  onAddJobToEvent,
  onSendEventNotifyBlast,
  onToggleCheckInLink,
  onAssignSecurity,
  onRequestSecuritySwap,
  onRespondSecuritySwap
}: EventsModuleProps) {
  const [selectedEventId, setSelectedEventId] = useState<string>(events[0]?.id || '');
  const [filterType, setFilterType] = useState<string>('All');
  const [showAddForm, setShowAddForm] = useState(false);
  const [showAddJobModal, setShowAddJobModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState<{ eventId: string; jobId: string } | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [showSecurityAssignModal, setShowSecurityAssignModal] = useState(false);
  const [showSwapModal, setShowSwapModal] = useState<{ eventId: string; assignmentId: string } | null>(null);
  const [targetSwapMemberId, setTargetSwapMemberId] = useState('');
  const [showLiveQRModal, setShowLiveQRModal] = useState(false);

  // New Event Form State
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [date, setDate] = useState('2026-07-16');
  const [startTime, setStartTime] = useState('18:00');
  const [endTime, setEndTime] = useState('20:00');
  const [location, setLocation] = useState('');
  const [type, setType] = useState<EventType>('Chapter Meeting');
  const [audience, setAudience] = useState<'All Members' | 'Officers Only' | 'Actives Only' | 'Pledges Only'>('All Members');
  const [points, setPoints] = useState('5');
  const [required, setRequired] = useState(true);

  // New Job State
  const [jobTitle, setJobTitle] = useState('');
  const [jobDesc, setJobDesc] = useState('');
  const [jobPeopleNeeded, setJobPeopleNeeded] = useState(2);

  // Security Assign State
  const [selectedSecMemberId, setSelectedSecMemberId] = useState(members[0]?.id || '');
  const [secStation, setSecStation] = useState('Front Porch / Main Entry Door');

  const currentMember = members.find(m => m.name === currentMemberName);
  const selectedEvent = events.find(e => e.id === selectedEventId) || events[0];

  const handleCreateEvent = (e: React.FormEvent) => {
    e.preventDefault();
    onAddEvent({
      title,
      description,
      date,
      startTime,
      endTime,
      time: `${startTime} - ${endTime}`,
      location,
      type,
      audience,
      points: parseInt(points) || 5,
      required,
      supervisors: [isOfficer ? currentMemberName : 'Alexander Mercer'],
      organizers: [], // starts empty to highlight "Organizers Needed"
      jobs: [
        {
          id: 'job_' + Math.random().toString(36).substring(2, 9),
          title: 'Event Prep & Equipment Setup',
          description: 'Arrive 30 minutes early to arrange tables and equipment.',
          peopleNeeded: 2,
          claimants: [],
          status: 'To Do'
        }
      ]
    });

    setTitle('');
    setDescription('');
    setLocation('');
    setShowAddForm(false);
  };

  const handleAddJobSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEvent) return;
    onAddJobToEvent(selectedEvent.id, {
      title: jobTitle,
      description: jobDesc,
      peopleNeeded: Number(jobPeopleNeeded) || 1
    });
    setJobTitle('');
    setJobDesc('');
    setJobPeopleNeeded(2);
    setShowAddJobModal(false);
  };

  const handleConfirmReject = () => {
    if (!showRejectModal || !rejectReason.trim()) return;
    onRejectJob(showRejectModal.eventId, showRejectModal.jobId, currentMemberName, rejectReason);
    setShowRejectModal(null);
    setRejectReason('');
  };

  const handleConfirmSecurityAssign = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEvent) return;
    const targetMem = members.find(m => m.id === selectedSecMemberId);
    if (targetMem) {
      onAssignSecurity(selectedEvent.id, targetMem.id, targetMem.name, secStation);
    }
    setShowSecurityAssignModal(false);
  };

  const handleConfirmSwapRequest = () => {
    if (!showSwapModal || !targetSwapMemberId || !selectedEvent) return;
    const targetMem = members.find(m => m.id === targetSwapMemberId);
    if (targetMem) {
      onRequestSecuritySwap(selectedEvent.id, showSwapModal.assignmentId, targetMem.id, targetMem.name);
    }
    setShowSwapModal(null);
    setTargetSwapMemberId('');
  };

  // Helper check: Notify Gate criteria
  // ≥1 supervisor, ≥1 organizer, ≥3 jobs
  const supervisorCount = selectedEvent?.supervisors?.length || 0;
  const organizerCount = selectedEvent?.organizers?.length || 0;
  const jobsCount = selectedEvent?.jobs?.length || 0;
  const isNotifyGateReady = supervisorCount >= 1 && organizerCount >= 1 && jobsCount >= 3;

  // 36-hour lock simulation check
  const isWithin36Hours = (eventDateStr: string) => {
    // July 11, 2026 is current simulated date
    // Event on July 11 or July 12 is within 36 hours
    return eventDateStr <= '2026-07-13';
  };

  const safeEvents = events || [];
  const safeMembers = members || [];
  const filteredEvents = safeEvents.filter(e => filterType === 'All' || e.type === filterType);
  // Security picker order (D17): fewest prior shifts first — that's who to pick.
  const securityPickerMembers = [...safeMembers].sort(
    (a, b) => (a.priorSecurityShifts || 0) - (b.priorSecurityShifts || 0)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Calendar className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Events, Jobs & Operations
            </h2>
            <span className="text-xs font-mono font-bold bg-gold/15 text-gold-muted px-2 py-0.5 rounded-full border border-gold/30">
              Exec & Operations
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Plan chapter events, assign supervisors, recruit organizers, publish claimable jobs, and manage security shifts.
          </p>
        </div>

        {isOfficer && (
          <button
            onClick={() => setShowAddForm(true)}
            className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer w-full sm:w-auto justify-center"
          >
            <Plus className="w-4 h-4" />
            Create Chapter Event
          </button>
        )}
      </div>

      {/* Main Grid: Left Event List (1 col), Right Detailed Event View (2 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Events Directory */}
        <div className="space-y-4">
          {/* Category Filter */}
          <div className="bg-white rounded-xl border border-slate-200/80 p-3 shadow-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold text-slate-700 font-mono uppercase tracking-wider">Filter Events</span>
              <span className="text-[10px] text-slate-400 font-mono">{filteredEvents.length} items</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {['All', 'Chapter Meeting', 'Philanthropy', 'Brotherhood', 'Social', 'Pledge Education'].map(t => (
                <button
                  key={t}
                  onClick={() => setFilterType(t)}
                  className={`text-[11px] px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                    filterType === t 
                      ? 'bg-navy text-gold shadow-xs' 
                      : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Event Cards */}
          <div className="space-y-3 max-h-[75vh] overflow-y-auto pr-1">
            {filteredEvents.map(e => {
              const isSelected = e.id === selectedEventId;
              const hasNoOrganizers = (!e.organizers || e.organizers.length === 0);
              // Backend-decorated count (spec Screen 1) — the claim lure.
              const openJobCount = e.openJobCount || 0;

              return (
                <div
                  key={e.id}
                  onClick={() => setSelectedEventId(e.id)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    isSelected 
                      ? 'bg-white border-gold shadow-md ring-2 ring-gold/20' 
                      : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-xs'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-gold-muted bg-amber-50 px-2 py-0.5 rounded">
                      {e.type}
                    </span>
                    {e.required && (
                      <span className="text-[9px] font-mono font-extrabold uppercase bg-red-50 text-red-700 px-1.5 py-0.5 rounded border border-red-200">
                        Mandatory
                      </span>
                    )}
                  </div>

                  <h3 className="font-bold text-sm text-slate-900 leading-snug mb-1">
                    {e.title}
                  </h3>

                  <div className="text-[11px] text-slate-500 space-y-1 mb-3">
                    <p className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{e.date} &bull; {e.time}</span>
                    </p>
                    <p className="flex items-center gap-1.5 truncate">
                      <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{e.location}</span>
                    </p>
                  </div>

                  {/* Badges / Operational Flags */}
                  <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-100">
                    {hasNoOrganizers ? (
                      <span className="text-[10px] font-bold font-mono bg-red-100 text-red-800 px-2 py-0.5 rounded flex items-center gap-1 animate-pulse">
                        <AlertTriangle className="w-3 h-3 text-red-600" />
                        Organizers Needed!
                      </span>
                    ) : (
                      <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 flex items-center gap-1">
                        <UserCheck className="w-3 h-3" />
                        {e.organizers.length} Chair{e.organizers.length > 1 ? 's' : ''}
                      </span>
                    )}

                    {openJobCount > 0 && (
                      <span className="text-[10px] font-mono font-bold bg-gold/20 text-gold-muted px-2 py-0.5 rounded">
                        {openJobCount} open jobs
                      </span>
                    )}

                    {e.notifiedAt && (
                      <span className="text-[10px] font-mono text-blue-700 bg-blue-50 px-2 py-0.5 rounded flex items-center gap-1">
                        <Send className="w-3 h-3" />
                        Notified
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Detailed Event Canvas */}
        {selectedEvent ? (
          <div className="lg:col-span-2 space-y-6">
            {/* Top Event Banner */}
            <Card className="p-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold bg-navy text-gold px-2.5 py-0.5 rounded">
                      {selectedEvent.type}
                    </span>
                    {selectedEvent.required && (
                      <span className="text-xs font-mono font-bold bg-red-100 text-red-800 px-2 py-0.5 rounded">
                        Mandatory Attendance
                      </span>
                    )}
                    <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                      {selectedEvent.points} Points
                    </span>
                  </div>
                  <h2 className="text-xl font-display font-extrabold text-slate-900 tracking-tight pt-1">
                    {selectedEvent.title}
                  </h2>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    {selectedEvent.description || 'No description provided for this chapter operation.'}
                  </p>
                </div>

                {/* Quick Check-in & Door Action Buttons */}
                <div className="flex sm:flex-col gap-2 shrink-0">
                  <button
                    onClick={() => setShowLiveQRModal(true)}
                    className="bg-navy hover:bg-slate-800 text-gold font-bold text-xs px-3.5 py-2 rounded-lg flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                  >
                    <QrCode className="w-4 h-4" />
                    Live Door Mode
                  </button>

                  {isOfficer && (
                    <button
                      onClick={() => onToggleCheckInLink(selectedEvent.id)}
                      className={`text-xs font-semibold px-3 py-1.5 rounded-lg border flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                        selectedEvent.checkInLinkActive
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                          : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      <KeyRound className="w-3.5 h-3.5" />
                      {selectedEvent.checkInLinkActive ? 'Check-in: ACTIVE' : 'Enable Door Link'}
                    </button>
                  )}
                </div>
              </div>

              {/* Event Metadata Ribbon */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-100 text-xs">
                <div>
                  <span className="text-[10px] text-slate-400 font-mono block uppercase">Date</span>
                  <span className="font-semibold text-slate-800">{selectedEvent.date}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 font-mono block uppercase">Time Range</span>
                  <span className="font-semibold text-slate-800">{selectedEvent.time}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 font-mono block uppercase">Location</span>
                  <span className="font-semibold text-slate-800 truncate block">{selectedEvent.location}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 font-mono block uppercase">Audience</span>
                  <span className="font-semibold text-slate-800">{selectedEvent.audience}</span>
                </div>
              </div>

              {/* Leaders: Supervisors & Organizers Section */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-slate-100">
                {/* Supervisors (Officers) */}
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/70 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-slate-700 font-mono uppercase flex items-center gap-1.5">
                      <Shield className="w-3.5 h-3.5 text-blue-600" />
                      Supervisors (Officers)
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">{selectedEvent.supervisors?.length || 0} assigned</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedEvent.supervisors && selectedEvent.supervisors.length > 0 ? (
                      selectedEvent.supervisors.map(sup => (
                        <span key={sup} className="text-xs bg-white text-slate-800 px-2.5 py-1 rounded-md font-semibold border border-slate-200 shadow-2xs">
                          {sup}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-400 italic">No supervisor assigned</span>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-500">Supervisors own the event and sign off on completed jobs.</p>
                </div>

                {/* Organizers (Chairs on the Ground) */}
                <div className={`p-3 rounded-xl border space-y-1.5 ${
                  !selectedEvent.organizers || selectedEvent.organizers.length === 0
                    ? 'bg-red-50/70 border-red-200 text-red-900'
                    : 'bg-slate-50 border-slate-200/70 text-slate-800'
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold font-mono uppercase flex items-center gap-1.5">
                      <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
                      Organizers (Chairs)
                    </span>
                    {(!selectedEvent.organizers || selectedEvent.organizers.length === 0) && (
                      <span className="text-[10px] font-bold font-mono bg-red-200 text-red-800 px-1.5 py-0.5 rounded">
                        Needed
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {selectedEvent.organizers && selectedEvent.organizers.length > 0 ? (
                      selectedEvent.organizers.map(org => (
                        <span key={org} className="text-xs bg-white text-slate-800 px-2.5 py-1 rounded-md font-semibold border border-slate-200 shadow-2xs">
                          {org}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-red-600 font-medium">No chairs on the ground yet.</span>
                    )}

                    {/* Volunteer 1-tap button */}
                    {(!selectedEvent.organizers?.includes(currentMemberName)) && (
                      <button
                        onClick={() => onVolunteerOrganizer(selectedEvent.id, currentMemberName)}
                        className="text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-2.5 py-1 rounded-md transition-all cursor-pointer flex items-center gap-1 shadow-2xs"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        Volunteer as Organizer
                      </button>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-500">Chairs coordinate setup, attendance, and member jobs on site.</p>
                </div>
              </div>

              {/* Notify Gate Checklist & Trigger Banner */}
              <div className="p-4 bg-slate-900 text-white rounded-xl space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <h4 className="text-xs font-mono uppercase tracking-wider font-bold text-gold flex items-center gap-1.5">
                      <Send className="w-3.5 h-3.5" />
                      Notify Members Gate (SMS & Broadcast)
                    </h4>
                    <p className="text-[11px] text-slate-300">
                      Blast stays locked until the event is fully planned with supervisors, organizers, and jobs.
                    </p>
                  </div>

                  <button
                    disabled={!isNotifyGateReady || !!selectedEvent.notifiedAt}
                    onClick={() => onSendEventNotifyBlast(selectedEvent.id)}
                    className={`px-4 py-2 rounded-lg text-xs font-bold font-mono uppercase tracking-wider flex items-center justify-center gap-2 transition-all ${
                      selectedEvent.notifiedAt
                        ? 'bg-blue-900/60 text-blue-300 border border-blue-700 cursor-default'
                        : isNotifyGateReady
                        ? 'bg-gold hover:bg-[#c5a02b] text-navy cursor-pointer shadow-sm'
                        : 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                    }`}
                  >
                    {selectedEvent.notifiedAt ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-blue-400" />
                        Blast Sent ({selectedEvent.notifiedAt.substring(5, 16)})
                      </>
                    ) : isNotifyGateReady ? (
                      <>
                        <Send className="w-4 h-4" />
                        Send Notification Blast
                      </>
                    ) : (
                      <>
                        <Lock className="w-4 h-4" />
                        Planning Incomplete
                      </>
                    )}
                  </button>
                </div>

                {/* Inline Gate Checklist */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-slate-800 text-xs font-mono">
                  <div className={`flex items-center gap-2 px-2.5 py-1.5 rounded bg-slate-800/80 ${
                    supervisorCount >= 1 ? 'text-emerald-400' : 'text-amber-400'
                  }`}>
                    {supervisorCount >= 1 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                    <span>{supervisorCount} / 1 Supervisor</span>
                  </div>

                  <div className={`flex items-center gap-2 px-2.5 py-1.5 rounded bg-slate-800/80 ${
                    organizerCount >= 1 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {organizerCount >= 1 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                    <span>{organizerCount} / 1 Organizer</span>
                  </div>

                  <div className={`flex items-center gap-2 px-2.5 py-1.5 rounded bg-slate-800/80 ${
                    jobsCount >= 3 ? 'text-emerald-400' : 'text-amber-400'
                  }`}>
                    {jobsCount >= 3 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                    <span>{jobsCount} / 3 Claimable Jobs</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* Section 2: Claimable Jobs Machinery */}
            <Card className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-gold" />
                    Claimable Jobs & Shifts ({(selectedEvent.jobs || []).length})
                  </h3>
                  <p className="text-xs text-slate-500">
                    Open duties available for brothers to claim. Lifecycle: To-Do &rarr; In Progress &rarr; Done Reported &rarr; Supervisor Sign-off.
                  </p>
                </div>

                {isOfficer && (
                  <button
                    onClick={() => setShowAddJobModal(true)}
                    className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Job
                  </button>
                )}
              </div>

              {/* 36-Hour Lock Warning Banner */}
              {isWithin36Hours(selectedEvent.date) && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-center gap-2">
                  <Lock className="w-4 h-4 text-amber-700 shrink-0" />
                  <span>
                    <strong>36-Hour Lock Active:</strong> Unclaiming is locked for this event. Late volunteers are welcome to claim open spots!
                  </span>
                </div>
              )}

              {/* Jobs List */}
              <div className="space-y-3">
                {(!selectedEvent.jobs || selectedEvent.jobs.length === 0) ? (
                  <p className="text-xs text-slate-400 py-4 text-center">No jobs created yet. Click "Add Job" above.</p>
                ) : (
                  (selectedEvent.jobs || []).map(job => {
                    const claimants = job.claimants || [];
                    const isClaimedByMe = currentMember && claimants.some(c => c.memberId === currentMember.id);
                    const isFull = claimants.length >= (job.peopleNeeded || 1);
                    const isSupervisor = (selectedEvent.supervisors || []).includes(currentMemberName) || isOfficer;
                    const lockUnclaim = isWithin36Hours(selectedEvent.date);

                    return (
                      <div 
                        key={job.id} 
                        className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 transition-all space-y-3"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-bold text-sm text-slate-900">{job.title}</h4>
                              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                                job.status === 'Approved' 
                                  ? 'bg-emerald-100 text-emerald-800' 
                                  : job.status === 'Done Reported' 
                                  ? 'bg-blue-100 text-blue-800' 
                                  : job.status === 'In Progress' 
                                  ? 'bg-amber-100 text-amber-800' 
                                  : job.status === 'Rejected'
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-slate-200 text-slate-700'
                              }`}>
                                {job.status}
                              </span>
                            </div>
                            <p className="text-xs text-slate-600 mt-1">{job.description}</p>
                          </div>

                          <div className="flex items-center gap-2 shrink-0">
                            <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded-md border ${
                              isFull 
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200' 
                                : 'bg-amber-50 text-amber-800 border-amber-200'
                            }`}>
                              {job.claimants.length} / {job.peopleNeeded} Claimed
                            </span>
                          </div>
                        </div>

                        {/* Claimants list */}
                        <div className="flex flex-wrap items-center gap-2 text-xs pt-1">
                          <span className="text-[10px] text-slate-400 font-mono uppercase">Assigned:</span>
                          {job.claimants.length === 0 ? (
                            <span className="text-slate-400 italic">No volunteers yet</span>
                          ) : (
                            job.claimants.map(c => (
                              <span key={c.memberId} className="bg-white border border-slate-200 text-slate-800 font-semibold px-2 py-0.5 rounded text-xs">
                                {c.memberName}
                              </span>
                            ))
                          )}
                        </div>

                        {/* Rejection Notes if any */}
                        {job.rejectionReason && (
                          <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 space-y-1">
                            <span className="font-bold block">Supervisor Rejection Feedback:</span>
                            <p>{job.rejectionReason}</p>
                          </div>
                        )}

                        {/* Action Buttons */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/60">
                          <div className="flex items-center gap-2">
                            {/* Claim Button */}
                            {!isClaimedByMe && !isFull && job.status !== 'Approved' && (
                              <button
                                onClick={() => {
                                  if (currentMember) {
                                    onClaimJob(selectedEvent.id, job.id, currentMember.id, currentMember.name);
                                  }
                                }}
                                className="text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer"
                              >
                                Claim This Job
                              </button>
                            )}

                            {/* Unclaim Button */}
                            {isClaimedByMe && job.status !== 'Approved' && (
                              <button
                                disabled={lockUnclaim}
                                onClick={() => {
                                  if (currentMember) {
                                    onUnclaimJob(selectedEvent.id, job.id, currentMember.id);
                                  }
                                }}
                                className={`text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all ${
                                  lockUnclaim
                                    ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'
                                    : 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100 cursor-pointer'
                                }`}
                              >
                                {lockUnclaim ? 'Locked (<36h)' : 'Unclaim'}
                              </button>
                            )}

                            {/* Report Done Button for Claimants */}
                            {isClaimedByMe && job.status === 'In Progress' && (
                              <button
                                onClick={() => onReportJobDone(selectedEvent.id, job.id, currentMemberName)}
                                className="text-xs bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer"
                              >
                                Report Completed
                              </button>
                            )}
                          </div>

                          {/* Supervisor Sign-Off Controls */}
                          {isSupervisor && job.status === 'Done Reported' && (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => onApproveJob(selectedEvent.id, job.id, currentMemberName)}
                                className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                Approve Job
                              </button>

                              <button
                                onClick={() => setShowRejectModal({ eventId: selectedEvent.id, jobId: job.id })}
                                className="text-xs bg-red-600 hover:bg-red-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                                Reject with Reason
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </Card>

            {/* Section 3: Security Shifts & Security Swap (Optional / Pre-assigned) */}
            <Card className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                    <Shield className="w-5 h-5 text-blue-600" />
                    Security & Risk Shifts
                  </h3>
                  <p className="text-xs text-slate-500">
                    Direct officer assignments based on chapter standing and hours. Assigned members can propose a shift swap.
                  </p>
                </div>

                {isOfficer && (
                  <button
                    onClick={() => setShowSecurityAssignModal(true)}
                    className="text-xs bg-navy hover:bg-slate-800 text-gold font-bold px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Assign Member
                  </button>
                )}
              </div>

              {/* Security Assignments Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 font-mono uppercase text-[10px]">
                    <tr>
                      <th className="py-2.5 px-3">Station</th>
                      <th className="py-2.5 px-3">Assigned Brother</th>
                      <th className="py-2.5 px-3">Standing</th>
                      <th className="py-2.5 px-3">Swap Status</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selectedEvent.securityAssignments && selectedEvent.securityAssignments.length > 0 ? (
                      selectedEvent.securityAssignments.map(sec => {
                        const isMyAssignment = currentMember && sec.memberId === currentMember.id;
                        const isTargetOfSwap = currentMember && sec.swapRequestedWithId === currentMember.id;

                        return (
                          <tr key={sec.id} className="hover:bg-slate-50/60">
                            <td className="py-3 px-3 font-semibold text-slate-900">{sec.station}</td>
                            <td className="py-3 px-3">
                              <span className="font-bold text-slate-800">{sec.memberName}</span>
                            </td>
                            <td className="py-3 px-3">
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-semibold">
                                Good Standing
                              </span>
                            </td>
                            <td className="py-3 px-3">
                              {sec.swapStatus === 'Pending' ? (
                                <span className="text-[10px] font-mono font-bold bg-amber-100 text-amber-800 px-2 py-0.5 rounded flex items-center gap-1 w-fit">
                                  <ArrowLeftRight className="w-3 h-3" />
                                  Swap w/ {sec.swapRequestedWithName}
                                </span>
                              ) : (
                                <span className="text-[10px] font-mono text-slate-400">Confirmed</span>
                              )}
                            </td>
                            <td className="py-3 px-3 text-right">
                              {/* Request Swap Action */}
                              {isMyAssignment && sec.swapStatus !== 'Pending' && (
                                <button
                                  onClick={() => setShowSwapModal({ eventId: selectedEvent.id, assignmentId: sec.id })}
                                  className="text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold px-2.5 py-1 rounded transition-all cursor-pointer"
                                >
                                  Request Swap
                                </button>
                              )}

                              {/* Respond to swap if target brother */}
                              {isTargetOfSwap && sec.swapStatus === 'Pending' && (
                                <div className="flex items-center justify-end gap-1.5">
                                  <button
                                    onClick={() => onRespondSecuritySwap(selectedEvent.id, sec.id, true)}
                                    className="text-[10px] bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-2 py-1 rounded cursor-pointer"
                                  >
                                    Accept
                                  </button>
                                  <button
                                    onClick={() => onRespondSecuritySwap(selectedEvent.id, sec.id, false)}
                                    className="text-[10px] bg-red-600 hover:bg-red-700 text-white font-bold px-2 py-1 rounded cursor-pointer"
                                  >
                                    Decline
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-slate-400 italic">
                          No security stations required for this event type.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        ) : (
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-400">
            Select an event from the left list to inspect details.
          </div>
        )}
      </div>

      {/* MODAL: Create New Event */}
      {showAddForm && (
        <Modal maxWidth="max-w-lg">
            <div className="flex justify-between items-center mb-4 border-b border-slate-100 pb-3">
              <h3 className="font-display font-extrabold text-base text-slate-900 flex items-center gap-2">
                <Calendar className="w-5 h-5 text-gold" />
                Schedule Chapter Operation Event
              </h3>
              <button 
                onClick={() => setShowAddForm(false)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>
            
            <form onSubmit={handleCreateEvent} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Event Title</label>
                <input 
                  type="text" 
                  value={title} 
                  onChange={e => setTitle(e.target.value)}
                  placeholder="e.g. Formal Ritual Chapter Meeting"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Description & Agenda</label>
                <textarea 
                  value={description} 
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Briefly state purpose, attire, or items brothers need to bring..."
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Date</label>
                  <input 
                    type="date" 
                    value={date} 
                    onChange={e => setDate(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Start Time</label>
                  <input 
                    type="time" 
                    value={startTime} 
                    onChange={e => setStartTime(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">End Time</label>
                  <input 
                    type="time" 
                    value={endTime} 
                    onChange={e => setEndTime(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Location</label>
                  <input 
                    type="text" 
                    value={location} 
                    onChange={e => setLocation(e.target.value)}
                    placeholder="Chapter Room, Rec Center..."
                    className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Category</label>
                  <select 
                    value={type} 
                    onChange={e => setType(e.target.value as EventType)}
                    className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    <option value="Chapter Meeting">Chapter Meeting</option>
                    <option value="Philanthropy">Philanthropy</option>
                    <option value="Brotherhood">Brotherhood</option>
                    <option value="Social">Social</option>
                    <option value="Recruitment">Recruitment</option>
                    <option value="Pledge Education">Pledge Education</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Target Audience</label>
                  <select 
                    value={audience} 
                    onChange={e => setAudience(e.target.value as any)}
                    className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    <option value="All Members">All Members</option>
                    <option value="Officers Only">Officers Only</option>
                    <option value="Actives Only">Actives Only</option>
                    <option value="Pledges Only">Pledges Only</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Point Value</label>
                  <input 
                    type="number" 
                    value={points} 
                    onChange={e => setPoints(e.target.value)}
                    className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input 
                  type="checkbox" 
                  id="reqEvt" 
                  checked={required} 
                  onChange={e => setRequired(e.target.checked)}
                  className="rounded text-gold focus:ring-gold"
                />
                <label htmlFor="reqEvt" className="text-xs font-semibold text-slate-700 cursor-pointer">
                  Mandatory attendance (unexcused absence incurs standard fine)
                </label>
              </div>

              <button 
                type="submit" 
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 rounded-lg text-xs uppercase tracking-wider transition-all mt-3 cursor-pointer"
              >
                Create Event & Open Planning Gate
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Add Job to Event */}
      {showAddJobModal && selectedEvent && (
        <Modal>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <Plus className="w-5 h-5 text-gold" />
                Add Claimable Job / Shift
              </h3>
              <button onClick={() => setShowAddJobModal(false)} className="text-slate-400 hover:text-slate-600 font-bold">✕</button>
            </div>
            
            <form onSubmit={handleAddJobSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Job Title</label>
                <input 
                  type="text" 
                  value={jobTitle} 
                  onChange={e => setJobTitle(e.target.value)}
                  placeholder="e.g. Sound System Setup & Mic Check"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Description / Instructions</label>
                <textarea 
                  value={jobDesc} 
                  onChange={e => setJobDesc(e.target.value)}
                  placeholder="Exact steps to complete and reporting instructions..."
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Brothers Needed</label>
                <input 
                  type="number" 
                  min={1} 
                  max={10} 
                  value={jobPeopleNeeded} 
                  onChange={e => setJobPeopleNeeded(Number(e.target.value))}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <button 
                type="submit" 
                className="w-full bg-gold hover:bg-[#c5a02b] text-navy font-bold py-3 rounded-lg text-xs uppercase tracking-wider transition-all cursor-pointer"
              >
                Publish Job to Event
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Reject Job with Reason */}
      {showRejectModal && (
        <Modal>
            <h3 className="font-display font-extrabold text-base text-red-900 flex items-center gap-2 mb-2">
              <XCircle className="w-5 h-5 text-red-600" />
              Reject Job Completion
            </h3>
            <p className="text-xs text-slate-600 mb-4">
              Work is never silently undone. State the exact reason why this task was rejected so claimants receive the notice in their SMS / push outbox.
            </p>

            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              placeholder="e.g. Ritual table candles were missing and rostrum wasn't dusted. Please complete before 17:45."
              rows={3}
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-red-500 mb-4"
              required
            />

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowRejectModal(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                disabled={!rejectReason.trim()}
                onClick={handleConfirmReject}
                className="px-4 py-2 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
              >
                Confirm Rejection & Send Notice
              </button>
            </div>
        </Modal>
      )}

      {/* MODAL: Assign Security Member from Stats Table */}
      {showSecurityAssignModal && selectedEvent && (
        <Modal maxWidth="max-w-lg">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <Shield className="w-5 h-5 text-blue-600" />
                Assign Member to Security Shift
              </h3>
              <button onClick={() => setShowSecurityAssignModal(false)} className="text-slate-400 hover:text-slate-600 font-bold">✕</button>
            </div>

            <form onSubmit={handleConfirmSecurityAssign} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Select Brother (Roster Stats)</label>
                <select
                  value={selectedSecMemberId}
                  onChange={e => setSelectedSecMemberId(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                >
                  {securityPickerMembers.map(m => (
                    <option key={m.id} value={m.id}>
                      {m.name} &bull; Prior shifts: {m.priorSecurityShifts || 0} &bull; GPA: {m.gpa} &bull; Att: {m.attendanceRate}% &bull; Standing: {m.standing} &bull; Sec Hrs: {m.securityHoursServed || 0}h
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 mt-1 font-mono">
                  Ordered by prior security shifts — fewest first.
                </p>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Assigned Security Post / Station</label>
                <input
                  type="text"
                  value={secStation}
                  onChange={e => setSecStation(e.target.value)}
                  placeholder="e.g. Front Door Wristband Scan"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 rounded-lg text-xs uppercase tracking-wider transition-all"
              >
                Confirm Shift Assignment
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Request Security Shift Swap */}
      {showSwapModal && (
        <Modal>
            <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2 mb-2">
              <ArrowLeftRight className="w-5 h-5 text-amber-600" />
              Propose Security Shift Swap
            </h3>
            <p className="text-xs text-slate-600 mb-4">
              Select an active brother to take your shift. The brother will be notified via outbox and can accept or decline.
            </p>

            <select
              value={targetSwapMemberId}
              onChange={e => setTargetSwapMemberId(e.target.value)}
              className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold mb-4"
            >
              <option value="">-- Choose brother to swap with --</option>
              {members.filter(m => m.name !== currentMemberName).map(m => (
                <option key={m.id} value={m.id}>{m.name} ({m.role})</option>
              ))}
            </select>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowSwapModal(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                disabled={!targetSwapMemberId}
                onClick={handleConfirmSwapRequest}
                className="px-4 py-2 text-xs font-bold bg-gold text-navy hover:bg-[#c5a02b] rounded-lg disabled:opacity-50"
              >
                Send Swap Request
              </button>
            </div>
        </Modal>
      )}

      {/* MODAL: Live Door Mode & QR Code View */}
      {showLiveQRModal && selectedEvent && (
        <Modal maxWidth="max-w-sm" className="text-center space-y-4" overlayClassName="bg-slate-900/70">
            <div className="flex justify-between items-center border-b border-slate-100 pb-2">
              <span className="text-xs font-mono font-bold uppercase text-slate-400">Live Door Mode</span>
              <button onClick={() => setShowLiveQRModal(false)} className="text-slate-400 hover:text-slate-600 font-bold">✕</button>
            </div>

            <div className="space-y-1">
              <h3 className="font-display font-extrabold text-lg text-slate-900">{selectedEvent.title}</h3>
              <p className="text-xs text-slate-500">{selectedEvent.location} &bull; {selectedEvent.time}</p>
            </div>

            {/* QR Code Canvas Box */}
            <div className="p-6 bg-slate-50 rounded-2xl border border-slate-200 flex flex-col items-center justify-center space-y-3">
              <div className="w-36 h-36 bg-navy text-gold rounded-xl flex items-center justify-center p-3 shadow-inner">
                <QrCode className="w-28 h-28" />
              </div>
              <span className="text-[10px] font-mono text-slate-400">Scan via GreekOS Mobile</span>
            </div>

            {/* PIN Code Box */}
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl space-y-1">
              <span className="text-[10px] font-mono uppercase text-amber-800 font-bold">4-Digit Door PIN Gate</span>
              <div className="text-2xl font-mono font-extrabold tracking-widest text-slate-900">
                {selectedEvent.checkInPin || '4892'}
              </div>
            </div>

            <button
              onClick={() => setShowLiveQRModal(false)}
              className="w-full bg-navy text-white font-bold py-2.5 rounded-lg text-xs"
            >
              Close Door View
            </button>
        </Modal>
      )}
    </div>
  );
}
