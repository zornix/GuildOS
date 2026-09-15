import { Fragment, useState } from 'react';
import { logout } from './api';
import { useAppData } from './hooks/useAppData';
import AppShell from './components/layout/AppShell';
import LoginScreen from './components/LoginScreen';
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
import { can } from './lib/session';

export default function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem('g_token'));
  if (!authed) return <LoginScreen onLoggedIn={() => setAuthed(true)} />;
  return <ChapterApp onLogout={() => { logout(); setAuthed(false); }} />;
}

function ChapterApp({ onLogout }: { onLogout: () => void }) {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const chrome = useEventsChrome();
  const app = useAppData();
  const { roster, events, initiatives, finance, attendance, tasks, recruitment } = app;
  const { isOfficer, currentMemberName } = app;
  const currentMember = roster.members.find(member => member.name === currentMemberName);
  const viewedBalance = balanceForMember(app.myBalance, currentMember?.id);

  return (
    <AppShell
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      isOfficer={isOfficer}
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
          isOfficer={isOfficer}
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
          initialTab={isOfficer ? 'roster_check' : 'self_pin'}
          onRecordAttendance={attendance.handleRecordAttendance}
          onSubmitExcuse={attendance.handleSubmitExcuse}
          onReviewExcuse={attendance.handleReviewExcuse}
          onSelfCheckIn={attendance.handleSelfCheckIn}
        />
      )}

      {activeTab === 'finance' && (
        <Fragment key={currentMember?.id ?? currentMemberName}>
          <FinanceModule
            members={roster.members}
            fines={finance.fines}
            payments={finance.payments}
            ledger={finance.ledger}
            isOfficer={isOfficer}
            currentMemberName={currentMemberName}
            myBalance={viewedBalance}
            balanceCentsOf={finance.balanceCentsOf}
            onRecordPayment={finance.handleRecordPayment}
            onIssueFine={finance.handleIssueFine}
            onPostInvoice={finance.handlePostInvoice}
            onApproveFinePayment={finance.handleApproveFinePayment}
            onPostLedgerCorrection={finance.handlePostLedgerCorrection}
          />
        </Fragment>
      )}

      {activeTab === 'roster' && (
        <RosterModule
          members={roster.members}
          isOfficer={isOfficer}
          canAssignRoles={can(app.permissions, 'roles:assign')}
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
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          onExecuteCommand={app.handleExecuteCommand}
        />
      )}
    </AppShell>
  );
}
