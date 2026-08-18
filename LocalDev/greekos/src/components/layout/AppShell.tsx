import React, { useState } from 'react';
import { Sparkles, Bell } from 'lucide-react';
import { Member } from '../../types';
import { isDemoTab } from '../../config/navigation';
import Sidebar from '../Sidebar';
import DemoGate from './DemoGate';

interface AppShellProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isOfficer: boolean;
  setIsOfficer: (val: boolean) => void;
  currentMemberName: string;
  setCurrentMemberName: (name: string) => void;
  members: Member[];
  outboxCount: number;
  toastMessage: string | null;
  loading: boolean;
  backendDown: boolean;
  children: React.ReactNode;
}

/** Sidebar + top navbar + toast + the load/demo notices around the active module. */
export default function AppShell({
  activeTab,
  setActiveTab,
  isOfficer,
  setIsOfficer,
  currentMemberName,
  setCurrentMemberName,
  members,
  outboxCount,
  toastMessage,
  loading,
  backendDown,
  children
}: AppShellProps) {
  // Which demo-only tabs the user has acknowledged this session
  const [demoUnlocked, setDemoUnlocked] = useState<Record<string, boolean>>({});
  const gated = isDemoTab(activeTab) && !demoUnlocked[activeTab];

  return (
    <div className="flex min-h-screen bg-[#f8fafc] text-slate-900 font-sans antialiased">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 bg-navy text-white px-4 py-3 rounded-xl border border-gold shadow-2xl flex items-center gap-2.5 z-50 animate-in fade-in slide-in-from-bottom-5">
          <Sparkles className="w-4 h-4 text-gold" />
          <span className="text-xs font-semibold">{toastMessage}</span>
        </div>
      )}

      {/* Left Sidebar (Dark Navy, Full Command Menu) */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isOfficer={isOfficer}
        setIsOfficer={setIsOfficer}
        currentMemberName={currentMemberName}
        setCurrentMemberName={setCurrentMemberName}
        allMembers={members}
        outboxCount={outboxCount}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Top Navbar */}
        <header className="bg-white border-b border-slate-200/80 px-6 py-3.5 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400">
              Alpha Chapter &bull; GreekOS v3.5
            </span>
          </div>

          <div className="flex items-center gap-4">
            {/* Quick Outbox Badge */}
            <button
              onClick={() => setActiveTab('outbox')}
              className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-all relative cursor-pointer"
              title="View SMS & Transactional Outbox"
            >
              <Bell className="w-4 h-4" />
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-gold"></span>
            </button>

            {/* Impersonated Member Chip */}
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200/80 px-3 py-1.5 rounded-xl">
              <div className="w-6 h-6 rounded-full bg-navy text-gold flex items-center justify-center font-bold text-[10px]">
                {currentMemberName.substring(0, 2).toUpperCase()}
              </div>
              <div className="text-left">
                <span className="text-xs font-bold text-slate-900 block leading-tight">{currentMemberName}</span>
                <span className="text-[9px] font-mono text-gold-muted font-semibold block">{isOfficer ? 'Officer' : 'Active Member'}</span>
              </div>
            </div>
          </div>
        </header>

        {/* Scrollable View Container */}
        <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
          {loading && (
            <div className="text-xs font-mono text-slate-400">Connecting to chapter server…</div>
          )}

          {backendDown && (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs font-semibold px-4 py-2.5 rounded-xl">
              Backend unreachable — showing demo data
            </div>
          )}

          {gated
            ? <DemoGate onContinue={() => setDemoUnlocked(prev => ({ ...prev, [activeTab]: true }))} />
            : children}
        </main>
      </div>
    </div>
  );
}
