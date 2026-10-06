import { LogOut } from 'lucide-react';
import { NAV_ITEMS, NavItem } from '../config/navigation';
import { can, isOfficerView } from '../lib/session';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  permissions: Set<string>;
  currentMemberName: string;
  onLogout: () => void;
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  permissions,
  currentMemberName,
  onLogout,
  open,
  onClose
}: SidebarProps) {
  const navRow = (item: NavItem) => {
    const Icon = item.icon;
    const isActive = activeTab === item.id;
    return (
      <button
        key={item.id}
        onClick={() => {
          setActiveTab(item.id);
          onClose();
        }}
        className={`w-full min-h-11 flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-xs transition-all cursor-pointer ${
          isActive
            ? 'bg-gold/20 text-gold font-semibold'
            : 'text-slate-300 font-medium hover:bg-slate-800/50 hover:text-white'
        }`}
      >
        <span className="flex items-center gap-2.5 truncate">
          <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-gold' : 'text-slate-400'}`} />
          <span className="truncate">{item.label}</span>
        </span>
      </button>
    );
  };

  return (
    <aside
      id="greekos-sidebar"
      className={`fixed inset-y-0 left-0 z-40 w-64 h-screen bg-navy text-slate-100 flex flex-col border-r border-[#1e2d42] select-none transition-transform lg:sticky lg:top-0 lg:shrink-0 lg:translate-x-0 ${
        open ? 'translate-x-0' : '-translate-x-full'
      }`}
    >
      <div className="p-5 border-b border-[#1e2d42] flex items-center gap-3">
        <div className="w-9 h-9 bg-gold text-navy rounded-xl font-bold flex items-center justify-center shadow-xs">
          <span className="text-xl tracking-wider font-display font-black">Ω</span>
        </div>
        <div>
          <h1 className="font-display font-bold text-base tracking-tight text-white">GreekOS</h1>
          <p className="text-xs text-slate-400 font-sans">Chapter ops</p>
        </div>
      </div>

      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.filter(item => !item.permission || can(permissions, item.permission)).map(navRow)}
      </nav>

      <div className="border-t border-[#1e2d42] bg-[#0b172a]/50 p-3 space-y-2">
        <div className="flex items-center gap-2.5 px-1">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0"></span>
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-semibold text-slate-200 truncate">
              {currentMemberName || 'Signed in'}
            </span>
            <span className="block text-xs text-slate-400 truncate">
              {isOfficerView(permissions) ? 'Officer' : 'Member'}
            </span>
          </span>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="w-full min-h-11 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-slate-300 hover:bg-slate-800/50 hover:text-white cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
