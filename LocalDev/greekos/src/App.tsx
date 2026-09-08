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
import EventsBar from './components/EventsBar';
import { useEventsChrome } from './hooks/useEventsChrome';
import { filterEventsByType } from './lib/events';

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const chrome = useEventsChrome();
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
        <>
          <EventsBar
            view={chrome.view}
            onViewChange={chrome.setView}
            filterType={chrome.filterType}
            onFilterChange={chrome.setFilterType}
            isOfficer={isOfficer}
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
              isOfficer={isOfficer}
              currentMemberName={currentMemberName}
              filterType={chrome.filterType}
              createOpen={chrome.createOpen}
              onCreateOpenChange={chrome.setCreateOpen}
              selectedEventId={chrome.selectedEventId}
              onSelectEventId={chrome.setSelectedEventId}
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
        </>
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
