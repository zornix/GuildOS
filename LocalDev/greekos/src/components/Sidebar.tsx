import { useState } from 'react';
import { ChevronDown, Shield, User } from 'lucide-react';
import { MemberRole } from '../types';
import { DEMO_NAV_ITEMS, NAV_ITEMS, NavItem } from '../config/navigation';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isOfficer: boolean;
  setIsOfficer: (val: boolean) => void;
  currentMemberName: string;
  setCurrentMemberName: (name: string) => void;
  allMembers: { id: string; name: string; role: MemberRole }[];
  /** Below lg the column is an overlay drawer; at lg+ it is always in flow. */
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  isOfficer,
  setIsOfficer,
  currentMemberName,
  setCurrentMemberName,
  allMembers,
  open,
  onClose
}: SidebarProps) {
  const safeAllMembers = allMembers || [];
  const currentMember = safeAllMembers.find(m => m.name === currentMemberName);
  const [switcherOpen, setSwitcherOpen] = useState(false);

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

        {item.demo && (
          <span className="text-xs font-medium bg-gold/20 text-gold px-1.5 py-0.5 rounded border border-gold/30">
            Demo
          </span>
        )}
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
      {/* Brand Header */}
      <div className="p-5 border-b border-[#1e2d42] flex items-center gap-3">
        <div className="w-9 h-9 bg-gold text-navy rounded-xl font-bold flex items-center justify-center shadow-xs">
          <span className="text-xl tracking-wider font-display font-black">Ω</span>
        </div>
        <div>
          <h1 className="font-display font-bold text-base tracking-tight text-white">GreekOS</h1>
          <p className="text-xs text-slate-400 font-sans">Alpha Chapter Operations</p>
        </div>
      </div>

      {/* Navigation items */}
      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.filter(item => isOfficer || !item.officerOnly).map(navRow)}

        <details className="mt-3 pt-3 border-t border-[#1e2d42]">
          <summary className="px-3 py-2 text-xs text-slate-400 hover:text-slate-200 cursor-pointer">
            Prototype demos
          </summary>
          <div className="space-y-1 pt-1">{DEMO_NAV_ITEMS.map(navRow)}</div>
        </details>
      </nav>

      {/* Footer: current user, expands into the role & view-as switcher */}
      <div className="border-t border-[#1e2d42] bg-[#0b172a]/50">
        <button
          onClick={() => setSwitcherOpen(v => !v)}
          aria-expanded={switcherOpen}
          className="w-full min-h-11 flex items-center gap-2.5 px-3.5 py-3 text-left hover:bg-slate-800/40 transition-all cursor-pointer"
        >
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0"></span>
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-semibold text-slate-200 truncate">
              {currentMember ? currentMember.name : currentMemberName}
            </span>
            <span className="block text-xs text-slate-400 truncate">
              {currentMember ? currentMember.role : (isOfficer ? 'Officer' : 'Member')}
            </span>
          </span>
          <ChevronDown className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${switcherOpen ? 'rotate-180' : ''}`} />
        </button>

        {switcherOpen && (
          <div className="px-3.5 pb-3.5 space-y-2.5">
            <div className="grid grid-cols-2 gap-1 p-0.5 bg-[#09101d] rounded-lg border border-[#1e2d42]">
              <button
                onClick={() => setIsOfficer(true)}
                className={`py-1.5 px-2 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                  isOfficer
                    ? 'bg-gold text-navy shadow-xs'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Shield className="w-3.5 h-3.5" />
                Officer
              </button>
              <button
                onClick={() => setIsOfficer(false)}
                className={`py-1.5 px-2 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                  !isOfficer
                    ? 'bg-gold text-navy shadow-xs'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <User className="w-3.5 h-3.5" />
                Member
              </button>
            </div>

            <div>
              <label htmlFor="view-as-member" className="text-xs text-slate-400 block mb-1">
                View as
              </label>
              <select
                id="view-as-member"
                value={currentMemberName}
                onChange={e => setCurrentMemberName(e.target.value)}
                className="w-full text-xs bg-[#09101d] border border-[#1e2d42] text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-gold transition-all cursor-pointer"
              >
                {safeAllMembers.map(m => (
                  <option key={m.id} value={m.name}>
                    {m.name} ({m.role})
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
