import React, { useEffect, useState } from 'react';
import { Menu, Sparkles, X } from 'lucide-react';
import Sidebar from '../Sidebar';

interface AppShellProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isOfficer: boolean;
  permissions: Set<string>;
  currentMemberName: string;
  onLogout: () => void;
  toastMessage: string | null;
  onDismissToast: () => void;
  loading: boolean;
  backendDown: boolean;
  children: React.ReactNode;
}

/** Sidebar + top navbar + toast around the active module. */
export default function AppShell({
  activeTab,
  setActiveTab,
  isOfficer,
  permissions,
  currentMemberName,
  onLogout,
  toastMessage,
  onDismissToast,
  loading,
  backendDown,
  children
}: AppShellProps) {
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
      <div role="status" aria-live="polite" className="fixed bottom-6 right-6 z-50">
        {toastMessage && (
          <div className="bg-navy text-white pl-4 pr-2 py-3 rounded-xl border border-gold shadow-2xl flex items-center gap-2.5 animate-in fade-in slide-in-from-bottom-5">
            <Sparkles className="w-4 h-4 text-gold shrink-0" />
            <span className="text-xs font-semibold">{toastMessage}</span>
            <button type="button" onClick={onDismissToast} aria-label="Dismiss notification" className="ml-2 p-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 cursor-pointer">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
          className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden"
        />
      )}

      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isOfficer={isOfficer}
        permissions={permissions}
        currentMemberName={currentMemberName}
        onLogout={onLogout}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200/80 px-4 sm:px-6 py-3 flex items-center justify-between gap-3 sticky top-0 z-20">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              className="lg:hidden -ml-1 p-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
            >
              <Menu className="w-5 h-5" />
            </button>
            <span className="text-xs font-medium text-slate-600">GreekOS</span>
          </div>

          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200/80 px-2 sm:px-3 py-1.5 rounded-xl">
            <div className="w-6 h-6 rounded-full bg-navy text-gold flex items-center justify-center font-bold text-xs">
              {(currentMemberName || '?').substring(0, 2).toUpperCase()}
            </div>
            <div className="hidden sm:block text-left">
              <span className="text-xs font-bold text-slate-900 block leading-tight">{currentMemberName || '…'}</span>
              <span className="text-xs text-slate-600 block">{isOfficer ? 'Officer' : 'Member'}</span>
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto space-y-6">
          {loading && (
            <div className="text-xs text-slate-500">Connecting to chapter server…</div>
          )}

          {backendDown && (
            <div className="bg-amber-50 border border-amber-200 text-amber-900 text-xs font-semibold px-4 py-2.5 rounded-xl">
              Can't reach the chapter server. Sign out and try again, or check that the API is up.
            </div>
          )}

          {children}
        </main>
      </div>
    </div>
  );
}
