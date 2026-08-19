import React, { useEffect, useState } from 'react';
import { Menu, Sparkles } from 'lucide-react';
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
  toastMessage,
  loading,
  backendDown,
  children
}: AppShellProps) {
  // Which demo-only tabs the user has acknowledged this session
  const [demoUnlocked, setDemoUnlocked] = useState<Record<string, boolean>>({});
  const gated = isDemoTab(activeTab) && !demoUnlocked[activeTab];

  // Below lg the sidebar is an overlay drawer.
  const [drawerOpen, setDrawerOpen] = useState(false);
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  return (
    <div className="flex min-h-screen bg-[#f8fafc] text-slate-900 font-sans antialiased">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 bg-navy text-white px-4 py-3 rounded-xl border border-gold shadow-2xl flex items-center gap-2.5 z-50 animate-in fade-in slide-in-from-bottom-5">
          <Sparkles className="w-4 h-4 text-gold" />
          <span className="text-xs font-semibold">{toastMessage}</span>
        </div>
      )}

      {drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
          className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden"
        />
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
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Top Navbar */}
        <header className="bg-white border-b border-slate-200/80 px-4 sm:px-6 py-3 flex items-center justify-between gap-3 sticky top-0 z-20">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              className="lg:hidden -ml-1 p-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
            >
              <Menu className="w-5 h-5" />
            </button>
            <span className="text-xs font-medium text-slate-600">Alpha Chapter</span>
          </div>

          {/* Impersonated Member Chip */}
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200/80 px-2 sm:px-3 py-1.5 rounded-xl">
            <div className="w-6 h-6 rounded-full bg-navy text-gold flex items-center justify-center font-bold text-xs">
              {currentMemberName.substring(0, 2).toUpperCase()}
            </div>
            <div className="hidden sm:block text-left">
              <span className="text-xs font-bold text-slate-900 block leading-tight">{currentMemberName}</span>
              <span className="text-xs text-slate-600 block">{isOfficer ? 'Officer' : 'Member'}</span>
            </div>
          </div>
        </header>

        {/* Scrollable View Container */}
        <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto space-y-6">
          {loading && (
            <div className="text-xs text-slate-500">Connecting to chapter server…</div>
          )}

          {backendDown && (
            <div className="bg-amber-50 border border-amber-200 text-amber-900 text-xs font-semibold px-4 py-2.5 rounded-xl">
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
