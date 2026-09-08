import { Calendar, KeyRound, Wallet } from 'lucide-react';
import type { ChapterEvent, Member } from '../../types';
import type { ContributionSummary } from '../../lib/contribution';
import { MemberBalance, balanceStatusLine } from '../../lib/balance';
import DoorCodeField from './DoorCodeField';

interface WelcomeBannerProps {
  member: Member | undefined;
  currentMemberName: string;
  memberCount: number;
  isOfficer: boolean;
  contribution: ContributionSummary;
  myBalance: MemberBalance | null;
  liveDoorEvent: ChapterEvent | undefined;
  onScheduleEvent: () => void;
  onOpenTreasury: () => void;
  onOpenAttendance: () => void;
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
}

/** Name, role, standing, the member's own upcoming counts, balance owed, and
 *  the two actions that finish on this screen: schedule (officer) and
 *  check in (member, when a door is open). */
export default function WelcomeBanner({
  member, currentMemberName, memberCount, isOfficer, contribution, myBalance, liveDoorEvent,
  onScheduleEvent, onOpenTreasury, onOpenAttendance, onSelfCheckIn
}: WelcomeBannerProps) {
  const counts = [
    `Organizing ${contribution.eventsOrganized}`,
    ...(isOfficer ? [`Supervising ${contribution.eventsSupervised}`] : []),
    `Chairing ${contribution.initiativesChaired}`
  ];
  const balanceLine = balanceStatusLine(myBalance);

  return (
    <div className="bg-navy text-white rounded-2xl p-6 shadow-md border border-[#1e2d42] space-y-4">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold bg-gold text-navy px-2.5 py-0.5 rounded">
              {member?.role || 'Brother'}
            </span>
            <span className="text-xs text-slate-300">{member?.standing || 'Good Standing'}</span>
          </div>
          <h1 className="text-2xl font-display font-extrabold text-white tracking-tight">
            Welcome back, {currentMemberName}
          </h1>
          <p className="text-xs text-slate-300">
            Alpha Chapter &bull; {memberCount} members
          </p>
          {/* Personal, upcoming-only. Facts of assignment shown to the member
              themself — never a ranking, never a standing input (ADR-0004). */}
          <p className="text-xs text-slate-200 pt-1">
            <span className="text-slate-400">Upcoming:</span> {counts.join(' · ')}
          </p>
        </div>

        <div className="flex flex-col items-start md:items-end gap-2">
          {balanceLine && (
            <button
              type="button"
              onClick={onOpenTreasury}
              className="text-xs font-semibold text-slate-100 hover:text-gold flex items-center gap-1.5 cursor-pointer"
            >
              <Wallet className="w-3.5 h-3.5 text-gold" />
              {balanceLine} &rarr;
            </button>
          )}

          {isOfficer && (
            <button
              type="button"
              onClick={onScheduleEvent}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg transition-all flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <Calendar className="w-4 h-4" />
              Schedule event
            </button>
          )}
        </div>
      </div>

      {!isOfficer && (
        <div className="border-t border-[#1e2d42] pt-4">
          {liveDoorEvent ? (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-gold" />
                Door open for <span className="text-white">{liveDoorEvent.title}</span>
              </p>
              <DoorCodeField onSelfCheckIn={onSelfCheckIn} compact />
            </div>
          ) : (
            <button
              type="button"
              onClick={onOpenAttendance}
              className="text-xs text-slate-300 hover:text-gold cursor-pointer"
            >
              No door open right now &middot; Attendance &rarr;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
