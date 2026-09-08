import { useState } from 'react';
import { useAppData } from './hooks/useAppData';
import AppShell from './components/layout/AppShell';
import DashboardOverview from './components/DashboardOverview';
import CalendarModule from './components/CalendarModule';
import EventsModule from './components/EventsModule';
import InitiativesModule from './components/InitiativesModule';
import RosterModule from './components/RosterModule';
import AttendanceModule from './components/AttendanceModule';
import FinanceModule from './components/FinanceModule';
import TasksModule from './components/TasksModule';
import RecruitmentModule from './components/RecruitmentModule';
import RulesModule from './components/RulesModule';
import CommandModule from './components/CommandModule';
import OutboxModule from './components/OutboxModule';

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  // The events screen shows the same data as a list or on the calendar.
  const [eventsView, setEventsView] = useState<'list' | 'calendar'>('list');
  const app = useAppData();
  const { roster, events, initiatives, finance, attendance, tasks, recruitment, outbox } = app;
  const { isOfficer, currentMemberName } = app;

  return (
    <AppShell
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      isOfficer={isOfficer}
      permissions={app.permissions}
      setIsOfficer={app.setIsOfficer}
      currentMemberName={currentMemberName}
      setCurrentMemberName={app.setCurrentMemberName}
      members={roster.members}
      toastMessage={app.toastMessage}
      loading={app.loading}
      backendDown={app.backendDown}
    >
      {activeTab === 'dashboard' && (
        <DashboardOverview
          members={roster.members}
          events={events.events}
          tasks={tasks.tasks}
          fines={finance.fines}
          initiatives={initiatives.initiatives}
          announcements={app.announcements}
          ledger={finance.ledger}
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          onNavigateTab={setActiveTab}
          onVolunteerOrganizer={events.handleVolunteerOrganizer}
          onPayDuesQuick={() => setActiveTab('finance')}
          onDeleteAnnouncement={app.handleDeleteAnnouncement}
        />
      )}

      {activeTab === 'events' && (
        <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg w-fit">
          {(['list', 'calendar'] as const).map(view => (
            <button
              key={view}
              onClick={() => setEventsView(view)}
              className={`px-3 py-2 rounded-md text-xs font-medium capitalize transition-all cursor-pointer ${
                eventsView === view ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {view}
            </button>
          ))}
        </div>
      )}

      {activeTab === 'events' && eventsView === 'calendar' && (
        <CalendarModule
          events={events.events}
          initiatives={initiatives.initiatives}
          announcements={app.announcements}
          currentMemberName={currentMemberName}
          onVolunteerOrganizer={events.handleVolunteerOrganizer}
        />
      )}

      {activeTab === 'events' && eventsView === 'list' && (
        <EventsModule
          events={events.events}
          members={roster.members}
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          onSelectEvent={events.handleSelectEvent}
          onAddEvent={events.handleAddEvent}
          onUpdateEvent={events.handleUpdateEvent}
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

      {activeTab === 'initiatives' && (
        <InitiativesModule
          initiatives={initiatives.initiatives}
          members={roster.members}
          isOfficer={isOfficer}
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
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
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
          ledger={finance.ledger}
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          onRecordPayment={finance.handleRecordPayment}
          onIssueFine={finance.handleIssueFine}
          onApproveFinePayment={finance.handleApproveFinePayment}
          onPostLedgerCorrection={finance.handlePostLedgerCorrection}
        />
      )}

      {activeTab === 'roster' && (
        <RosterModule
          members={roster.members}
          isOfficer={isOfficer}
          onAddMember={roster.handleAddMember}
          onUpdateStanding={roster.handleUpdateStanding}
        />
      )}

      {activeTab === 'tasks' && (
        <TasksModule
          tasks={tasks.tasks}
          members={roster.members}
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          onAddTask={tasks.handleAddTask}
          onToggleTaskStatus={tasks.handleToggleTaskStatus}
          onClaimTask={tasks.handleClaimTask}
        />
      )}

      {activeTab === 'recruitment' && (
        <RecruitmentModule
          pnms={recruitment.pnms}
          isOfficer={isOfficer}
          onAddPNM={recruitment.handleAddPNM}
          onVotePNM={recruitment.handleVotePNM}
          onExtendBid={recruitment.handleExtendBid}
        />
      )}

      {activeTab === 'rules' && <RulesModule rules={app.rules} />}

      {activeTab === 'command' && (
        <CommandModule
          members={roster.members}
          events={events.events}
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          onExecuteCommand={app.handleExecuteCommand}
        />
      )}

      {activeTab === 'outbox' && (
        <OutboxModule
          notifications={outbox.outbox}
          isOfficer={isOfficer}
          onRetryNotification={() => app.showToast('Re-queued message for transmission.')}
          onClearDelivered={outbox.clearDelivered}
        />
      )}
    </AppShell>
  );
}
