import { useEffect, useState } from 'react';
import { logout } from './api';
import { useAppData } from './hooks/useAppData';
import AppShell from './components/layout/AppShell';
import LoginScreen from './components/LoginScreen';
import OnboardingScreen from './components/OnboardingScreen';
import DashboardOverview from './components/DashboardOverview';
import CalendarModule from './components/CalendarModule';
import EventsModule from './components/EventsModule';
import InitiativesModule from './components/InitiativesModule';
import RosterModule from './components/RosterModule';
import AttendanceModule from './components/AttendanceModule';
import FinanceModule from './components/FinanceModule';
import TasksModule from './components/TasksModule';
import RecruitmentModule from './components/RecruitmentModule';
import CommandModule from './components/CommandModule';
import OutboxModule from './components/OutboxModule';
import EventsBar from './components/EventsBar';
import { useEventsChrome } from './hooks/useEventsChrome';
import { filterEventsByType } from './lib/events';
import { balanceForMember } from './lib/balance';
import { can, isOfficerView } from './lib/session';
import { CHECKIN_STORAGE_KEY, readCheckinCode, stripCheckinParam } from './lib/checkinLink';

export default function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem('g_token'));
  const [onboarding, setOnboarding] = useState(false);
  // A /?checkin=CODE link (where the backend's /c/CODE redirect lands) must
  // survive the login screen, so the code is parked until a member is signed in.
  useEffect(() => {
    const code = readCheckinCode(location.search);
    if (code) sessionStorage.setItem(CHECKIN_STORAGE_KEY, code);
  }, []);
  if (!authed) {
    return onboarding
      ? <OnboardingScreen onBack={() => setOnboarding(false)} />
      : <LoginScreen onLoggedIn={() => setAuthed(true)} onStartChapter={() => setOnboarding(true)} />;
  }
  return <ChapterApp onLogout={() => { logout(); setAuthed(false); }} />;
}

function ChapterApp({ onLogout }: { onLogout: () => void }) {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const chrome = useEventsChrome();
  const app = useAppData();
  const { roster, events, initiatives, finance, attendance, tasks, recruitment } = app;
  const { currentMemberId, currentMemberName } = app;
  const currentMember = roster.members.find(member => member.id === currentMemberId);
  const viewedBalance = balanceForMember(app.myBalance, currentMember?.id);
  const canMarkAttendance = can(app.permissions, 'attendance:override');
  const canCreateEvent = can(app.permissions, 'calendar:event:create');
  const canManageJobs = can(app.permissions, 'tasks:assign');
  const canInviteMembers = can(app.permissions, 'members:invite');

  // Consume a parked door code exactly once, after the session has loaded.
  useEffect(() => {
    if (app.loading || !currentMemberId) return;
    const code = sessionStorage.getItem(CHECKIN_STORAGE_KEY);
    if (!code) return;
    sessionStorage.removeItem(CHECKIN_STORAGE_KEY);
    history.replaceState(null, '', stripCheckinParam(location.href));
    attendance.handleSelfCheckIn(code).then(result => app.showToast(result.message));
  }, [app.loading, currentMemberId]);

  return (
    <AppShell
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      permissions={app.permissions}
      currentMemberName={currentMemberName || app.sessionName}
      onLogout={onLogout}
      toastMessage={app.toastMessage}
      onDismissToast={app.dismissToast}
      loading={app.loading}
      backendDown={app.backendDown}
    >
      {activeTab === 'dashboard' && (
        <DashboardOverview
          members={roster.members}
          events={events.events}
          tasks={tasks.tasks}
          initiatives={initiatives.initiatives}
          announcements={app.announcements}
          officerView={isOfficerView(app.permissions)}
          canScheduleEvent={canCreateEvent}
          canDeleteAnnouncement={can(app.permissions, 'announcements:create')}
          currentMemberId={currentMemberId}
          currentMemberName={currentMemberName}
          contribution={app.contribution}
          myBalance={viewedBalance}
          onNavigateTab={setActiveTab}
          onOpenEvent={id => { chrome.openEvent(id); setActiveTab('events'); }}
          onScheduleEvent={() => { chrome.openCreate(); setActiveTab('events'); }}
          onVolunteerOrganizer={events.handleVolunteerOrganizer}
          onSelfCheckIn={attendance.handleSelfCheckIn}
          onDeleteAnnouncement={app.handleDeleteAnnouncement}
        />
      )}

      {activeTab === 'events' && (
        <>
          <EventsBar
            view={chrome.view}
            onViewChange={chrome.setView}
            filterType={chrome.filterType}
            onFilterChange={chrome.setFilterType}
            canCreateEvent={canCreateEvent}
            onCreate={chrome.openCreate}
          />

          {chrome.view === 'calendar' && (
            <CalendarModule
              events={filterEventsByType(events.events, chrome.filterType)}
              initiatives={initiatives.initiatives}
              announcements={app.announcements}
              currentMemberName={currentMemberName}
              onVolunteerOrganizer={events.handleVolunteerOrganizer}
              onOpenEvent={chrome.openEvent}
            />
          )}

          {chrome.view === 'list' && (
            <EventsModule
              events={events.events}
              members={roster.members}
              canCreateEvent={canCreateEvent}
              canManageEvent={can(app.permissions, 'calendar:event:update')}
              canManageCheckInLink={can(app.permissions, 'attendance:checkin_link:manage')}
              canManageJobs={canManageJobs}
              currentMemberName={currentMemberName}
              filterType={chrome.filterType}
              createOpen={chrome.createOpen}
              onCreateOpenChange={chrome.setCreateOpen}
              selectedEventId={chrome.selectedEventId}
              onSelectEventId={chrome.setSelectedEventId}
              onSelectEvent={events.handleSelectEvent}
              onAddEvent={events.handleAddEvent}
              onUpdateEvent={events.handleUpdateEvent}
              canDeleteEvent={can(app.permissions, 'calendar:event:delete')}
              onDeleteEvent={events.handleDeleteEvent}
              onVolunteerOrganizer={events.handleVolunteerOrganizer}
              onClaimJob={events.handleClaimJob}
              onUnclaimJob={events.handleUnclaimJob}
              onReportJobDone={events.handleReportJobDone}
              onApproveJob={events.handleApproveJob}
              onRejectJob={events.handleRejectJob}
              onAddJobToEvent={events.handleAddJobToEvent}
              onEditJob={events.handleEditJob}
              onDeleteJob={events.handleDeleteJob}
              onSendEventNotifyBlast={events.handleSendEventNotifyBlast}
              onToggleCheckInLink={events.handleToggleCheckInLink}
              onAssignSecurity={events.handleAssignSecurity}
              onRequestSecuritySwap={events.handleRequestSecuritySwap}
              onRespondSecuritySwap={events.handleRespondSecuritySwap}
              onCancelSecuritySwap={events.handleCancelSecuritySwap}
            />
          )}
        </>
      )}

      {activeTab === 'initiatives' && (
        <InitiativesModule
          initiatives={initiatives.initiatives}
          members={roster.members}
          canCreateInitiative={can(app.permissions, 'calendar:initiative:create')}
          canManageJobs={canManageJobs}
          currentMemberName={currentMemberName}
          onAddInitiative={initiatives.handleAddInitiative}
          onAddJobToInitiative={initiatives.handleAddJobToInitiative}
          onClaimInitiativeJob={initiatives.handleClaimInitiativeJob}
          onUnclaimInitiativeJob={initiatives.handleUnclaimInitiativeJob}
          onReportInitiativeJobDone={initiatives.handleReportInitiativeJobDone}
          onApproveInitiativeJob={initiatives.handleApproveInitiativeJob}
        />
      )}

      {activeTab === 'attendance' && (
        <AttendanceModule
          events={events.events}
          members={roster.members}
          excuses={attendance.excuses}
          canMarkAttendance={canMarkAttendance}
          canReviewExcuses={can(app.permissions, 'attendance:excuse:review')}
          canSeeAttendanceRates={can(app.permissions, 'standing:view_all')}
          currentMemberName={currentMemberName}
          initialTab={canMarkAttendance ? 'roster_check' : 'self_pin'}
          onRecordAttendance={attendance.handleRecordAttendance}
          onSubmitExcuse={attendance.handleSubmitExcuse}
          onReviewExcuse={attendance.handleReviewExcuse}
          onSelfCheckIn={attendance.handleSelfCheckIn}
        />
      )}

      {activeTab === 'finance' && (
        <FinanceModule
          members={roster.members}
          fines={finance.fines}
          payments={finance.payments}
          events={events.events}
          permissions={app.permissions}
          chapterName={app.chapterName}
          currentMemberId={currentMember?.id}
          myInvoices={finance.myInvoices}
          pendingProofCentsOf={finance.pendingProofCentsOf}
          submissions={finance.submissions}
          queueLoading={finance.queueLoading}
          onRefreshQueue={finance.refreshQueue}
          onCreateDuesRun={finance.handleCreateDuesRun}
          onSubmitProof={finance.handleSubmitProof}
          onVerifyProof={finance.handleVerifyProof}
          onRejectProof={finance.handleRejectProof}
          onOpenEvidence={finance.openEvidence}
          balanceCentsOf={finance.balanceCentsOf}
          onSubmitTransaction={finance.submitTransaction}
        />
      )}

      {activeTab === 'roster' && (
        <RosterModule
          members={roster.members}
          canInviteMembers={canInviteMembers}
          canSeeStandingDetail={can(app.permissions, 'standing:view_all')}
          canAssignRoles={can(app.permissions, 'roles:assign')}
          canSeeSmsConsent={canInviteMembers}
          onImportRoster={file => roster.handleImportRoster(app.chapterId, file)}
          onRolesChanged={app.refreshOwnPermissions}
        />
      )}

      {activeTab === 'tasks' && (
        <TasksModule
          tasks={tasks.tasks}
          members={roster.members}
          canCreateTask={can(app.permissions, 'tasks:create')}
          currentMemberName={currentMemberName}
          onAddTask={tasks.handleAddTask}
          onToggleTaskStatus={tasks.handleToggleTaskStatus}
          onClaimTask={tasks.handleClaimTask}
        />
      )}

      {activeTab === 'recruitment' && (
        <RecruitmentModule
          pnms={recruitment.pnms}
          canUpdate={can(app.permissions, 'recruitment:pipeline:update')}
          onAddPNM={recruitment.handleAddPNM}
          onVotePNM={recruitment.handleVotePNM}
          onExtendBid={recruitment.handleExtendBid}
        />
      )}

      {activeTab === 'outbox' && <OutboxModule />}

      {activeTab === 'command' && (
        <CommandModule
          members={roster.members}
          events={events.events}
          currentMemberName={currentMemberName}
          onExecuteCommand={app.handleExecuteCommand}
        />
      )}
    </AppShell>
  );
}
