import { Shield, User } from 'lucide-react';
import { MemberRole } from '../types';
import { NAV_ITEMS } from '../config/navigation';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isOfficer: boolean;
  setIsOfficer: (val: boolean) => void;
  currentMemberName: string;
  setCurrentMemberName: (name: string) => void;
  allMembers: { id: string; name: string; role: MemberRole }[];
  outboxCount: number;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  isOfficer,
  setIsOfficer,
  currentMemberName,
  setCurrentMemberName,
  allMembers,
  outboxCount
}: SidebarProps) {
  const safeAllMembers = allMembers || [];
  const currentMember = safeAllMembers.find(m => m.name === currentMemberName);

  return (
    <aside id="greekos-sidebar" className="w-64 bg-navy text-slate-100 flex flex-col border-r border-[#1e2d42] h-screen sticky top-0 shrink-0 select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-[#1e2d42] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gold text-navy rounded-xl font-bold flex items-center justify-center shadow-xs">
            <span className="text-xl tracking-wider font-display font-black">Ω</span>
          </div>
          <div>
            <h1 className="font-display font-bold text-base tracking-tight text-white flex items-center gap-1.5">
              GreekOS <span className="text-[9px] uppercase font-mono tracking-widest bg-gold/20 text-gold px-1.5 py-0.5 rounded font-bold">OS v2.4</span>
            </h1>
            <p className="text-[11px] text-slate-400 font-sans">Alpha Chapter Operations</p>
          </div>
        </div>
      </div>

      {/* Role & Mode Switcher */}
      <div className="px-4 py-3 border-b border-[#1e2d42] bg-[#0b172a]/60">
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Active Role & View</label>
          <span className="text-[9px] text-gold font-mono font-bold">
            {isOfficer ? 'EXEC PRIVILEGES' : 'MEMBER ACCESS'}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-1 p-0.5 bg-[#09101d] rounded-lg border border-[#1e2d42] mb-2.5">
          <button
            onClick={() => setIsOfficer(true)}
            className={`py-1.5 px-2 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              isOfficer 
                ? 'bg-gold text-navy shadow-xs' 
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            Officer (Exec)
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
            Member / Chair
          </button>
        </div>

        {/* Impersonate Brother dropdown */}
        <div>
          <label className="text-[9px] text-slate-400 font-mono block mb-1 uppercase tracking-wider">
            {isOfficer ? 'Active Officer Profile' : 'Impersonate Brother'}
          </label>
          <select
            value={currentMemberName}
            onChange={(e) => {
              const name = e.target.value;
              setCurrentMemberName(name);
              const mem = safeAllMembers.find(m => m.name === name);
              if (mem) {
                // If member has executive role, auto toggle officer or let user pick
                const isExecRole = ['President', 'Vice President', 'Treasurer', 'Secretary', 'Risk Manager'].includes(mem.role);
                if (isExecRole && !isOfficer) {
                  // Keep user toggle or switch
                }
              }
            }}
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

      {/* Navigation items */}
      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          const count = item.id === 'outbox' ? outboxCount : undefined;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                isActive
                  ? 'bg-gold/20 text-gold border-l-4 border-gold font-bold shadow-xs'
                  : 'text-slate-300 hover:bg-slate-800/50 hover:text-white'
              }`}
            >
              <div className="flex items-center gap-2.5 truncate">
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-gold' : 'text-slate-400'}`} />
                <span className="truncate">{item.label}</span>
              </div>

              {item.demo && (
                <span className="text-[9px] font-mono font-bold bg-gold/20 text-gold px-1.5 py-0.5 rounded border border-gold/30">
                  DEMO
                </span>
              )}

              {count !== undefined && count > 0 && (
                <span className="text-[9px] font-mono font-bold bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer User Info */}
      <div className="p-3.5 border-t border-[#1e2d42] bg-[#0b172a]/50 text-xs">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0"></div>
          <div className="min-w-0 flex-1">
            <div className="text-slate-200 font-semibold truncate text-xs">
              {currentMember ? currentMember.name : currentMemberName}
            </div>
            <div className="text-[10px] text-gold font-mono truncate">
              {currentMember ? currentMember.role : (isOfficer ? 'Executive Board' : 'Active Member')}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
