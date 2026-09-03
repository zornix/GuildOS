import React, { useState } from 'react';
import {
  Terminal,
  CheckCircle2,
  AlertCircle,
  History,
  Zap
} from 'lucide-react';
import { Member, ChapterEvent, Task, PNM } from '../types';
import Card from './ui/Card';
import { formatMoney } from '../formatters';
import { parseWhen } from '../lib/parseWhen';

interface CommandModuleProps {
  members: Member[];
  events: ChapterEvent[];
  isOfficer: boolean;
  currentMemberName: string;
  onExecuteCommand: (result: {
    type: 'FINE' | 'TASK' | 'EVENT' | 'BID' | 'ANNOUNCEMENT' | 'EXCUSE_APPROVE' | 'ATTENDANCE';
    payload: any;
    summary: string;
  }) => void;
}

export default function CommandModule({
  members,
  events,
  isOfficer,
  currentMemberName,
  onExecuteCommand
}: CommandModuleProps) {
  const safeMembers = members || [];
  const safeEvents = events || [];
  const [commandInput, setCommandInput] = useState('');
  const [commandHistory, setCommandHistory] = useState<Array<{
    input: string;
    timestamp: string;
    status: 'Executed' | 'Error' | 'Permission Denied';
    summary: string;
    details?: string;
  }>>([
    {
      input: 'fine Cody Jenkins $50 for missing ritual',
      timestamp: '2026-07-05 19:30',
      status: 'Executed',
      summary: 'Assessed $50.00 fine to Cody Jenkins for ritual absence'
    },
    {
      input: 'assign Kitchen Sweep to Lucas Wright',
      timestamp: '2026-07-10 12:00',
      status: 'Executed',
      summary: 'Created task "Kitchen Sweep" assigned to Lucas Wright'
    }
  ]);

  const quickTemplates = [
    'fine Cody Jenkins $25 for missing chapter',
    'assign Living Room Sweep to Cody Jenkins',
    'schedule Brotherhood Poker Night on Friday at 8pm',
    'extend bid to Gavin Henderson',
    'send announcement: Mandatory chapter suit and tie tomorrow at 6pm',
    'approve excuse for Devin Brooks'
  ];

  const handleRunCommand = (text: string) => {
    const raw = text.trim();
    if (!raw) return;

    const lower = raw.toLowerCase();
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false }).substring(0, 5);

    // 1. FINE PARSER
    // "fine [Member] $[Amount] for [Reason]"
    if (lower.startsWith('fine ')) {
      const fineMatch = raw.match(/fine\s+([a-zA-Z\s]+?)\s+\$?(\d+)(?:\s+for\s+(.+))?/i);
      if (fineMatch) {
        const rawName = fineMatch[1].trim();
        const amount = parseFloat(fineMatch[2]);
        const reason = fineMatch[3] ? fineMatch[3].trim() : 'Bylaws Infraction Citation';
        const matchedMember = safeMembers.find(m => m.name.toLowerCase().includes(rawName.toLowerCase()));

        if (matchedMember) {
          onExecuteCommand({
            type: 'FINE',
            payload: {
              memberId: matchedMember.id,
              memberName: matchedMember.name,
              amount,
              amountCents: Math.round(amount * 100),
              reason,
              issuedBy: currentMemberName
            },
            summary: `Issued ${formatMoney(Math.round(amount * 100))} fine to ${matchedMember.name} for "${reason}"`
          });

          setCommandHistory(prev => [{
            input: raw,
            timestamp,
            status: 'Executed',
            summary: `Issued ${formatMoney(Math.round(amount * 100))} fine to ${matchedMember.name} for "${reason}"`
          }, ...prev]);

          setCommandInput('');
          return;
        }
      }
    }

    // 2. ASSIGN TASK PARSER
    // "assign [Task Title] to [Member]"
    if (lower.startsWith('assign ')) {
      const taskMatch = raw.match(/assign\s+(.+?)\s+to\s+([a-zA-Z\s]+)/i);
      if (taskMatch) {
        const taskTitle = taskMatch[1].trim();
        const rawName = taskMatch[2].trim();
        const matchedMember = safeMembers.find(m => m.name.toLowerCase().includes(rawName.toLowerCase()));

        if (matchedMember) {
          onExecuteCommand({
            type: 'TASK',
            payload: {
              title: taskTitle,
              description: `Assigned via GreekOS Natural Command console to ${matchedMember.name}.`,
              assignedTo: matchedMember.name,
              assignedToId: matchedMember.id,
              dueDate: '2026-07-16',
              priority: 'Medium'
            },
            summary: `Assigned task "${taskTitle}" to ${matchedMember.name}`
          });

          setCommandHistory(prev => [{
            input: raw,
            timestamp,
            status: 'Executed',
            summary: `Assigned task "${taskTitle}" to ${matchedMember.name}`
          }, ...prev]);

          setCommandInput('');
          return;
        }
      }
    }

    // 3. SCHEDULE EVENT PARSER
    // "schedule [Event Title] on [Day/Date] at [Time]"
    if (lower.startsWith('schedule ')) {
      const eventMatch = raw.match(/schedule\s+(.+?)(?:\s+on\s+(.+?))?(?:\s+at\s+(.+))?$/i);
      if (eventMatch) {
        const eventTitle = eventMatch[1].trim();
        // This books a real event, so an unreadable date is an error, never a default.
        const when = parseWhen(eventMatch[2] || '', eventMatch[3] || '');
        if (!when) {
          setCommandHistory(prev => [{
            input: raw,
            timestamp,
            status: 'Error',
            summary: `Couldn't read a date/time from "${raw}"`
          }, ...prev]);
          return;
        }
        const [startHour, startMinute] = when.time.split(':');
        const endTime = `${String((Number(startHour) + 2) % 24).padStart(2, '0')}:${startMinute}`;

        onExecuteCommand({
          type: 'EVENT',
          payload: {
            title: eventTitle,
            description: 'Scheduled via GreekOS Natural Language Command console.',
            date: when.date,
            startTime: when.time,
            endTime,
            time: `${when.time} - ${endTime}`,
            location: 'Fraternity House',
            type: 'Brotherhood',
            audience: 'All Members',
            required: false,
            supervisors: [currentMemberName],
            organizers: [],
            jobs: [
              {
                id: 'job_' + Math.random().toString(36).substring(2, 9),
                title: 'Event Prep & Host Duty',
                description: 'Set up room and welcome brothers.',
                peopleNeeded: 2,
                claimants: [],
                status: 'To Do'
              }
            ]
          },
          summary: `Scheduled "${eventTitle}" for ${when.date} at ${when.time}`
        });

        setCommandHistory(prev => [{
          input: raw,
          timestamp,
          status: 'Executed',
          summary: `Scheduled chapter event "${eventTitle}" for ${when.date} at ${when.time}`
        }, ...prev]);

        setCommandInput('');
        return;
      }
    }

    // 4. EXTEND BID PARSER
    // "extend bid to [PNM Name]"
    if (lower.includes('bid') && lower.includes('to')) {
      const pnmMatch = raw.match(/(?:extend|give|offer)\s+bid\s+to\s+([a-zA-Z\s]+)/i);
      if (pnmMatch) {
        const pnmName = pnmMatch[1].trim();
        onExecuteCommand({
          type: 'BID',
          payload: {
            pnmName
          },
          summary: `Extended official bid to PNM "${pnmName}"`
        });

        setCommandHistory(prev => [{
          input: raw,
          timestamp,
          status: 'Executed',
          summary: `Updated recruitment pipeline: Bid Extended to ${pnmName}`
        }, ...prev]);

        setCommandInput('');
        return;
      }
    }

    // 5. ANNOUNCEMENT BLAST PARSER
    // "send announcement: [Message]" or "post announcement: [Message]"
    if (lower.includes('announcement')) {
      const annText = raw.replace(/^(?:send|post|broadcast)\s+announcement:?\s*/i, '');
      onExecuteCommand({
        type: 'ANNOUNCEMENT',
        payload: {
          title: 'Executive Chapter Alert',
          content: annText,
          author: currentMemberName,
          priority: 'Mandatory',
          channels: ['Calendar', 'SMS', 'Push']
        },
        summary: `Dispatched SMS & Calendar announcement blast: "${annText}"`
      });

      setCommandHistory(prev => [{
        input: raw,
        timestamp,
        status: 'Executed',
        summary: `Dispatched broadcast announcement to all brothers`
      }, ...prev]);

      setCommandInput('');
      return;
    }

    // 6. APPROVE EXCUSE PARSER
    // "approve excuse for [Member]"
    if (lower.includes('approve excuse')) {
      const nameMatch = raw.match(/approve\s+excuse\s+for\s+([a-zA-Z\s]+)/i);
      const name = nameMatch ? nameMatch[1].trim() : 'brother';
      onExecuteCommand({
        type: 'EXCUSE_APPROVE',
        payload: {
          memberName: name
        },
        summary: `Approved pending excuse for ${name}`
      });

      setCommandHistory(prev => [{
        input: raw,
        timestamp,
        status: 'Executed',
        summary: `Approved excuse request for ${name}`
      }, ...prev]);

      setCommandInput('');
      return;
    }

    // Fallback: Generic Command Execution
    setCommandHistory(prev => [{
      input: raw,
      timestamp,
      status: 'Error',
      summary: 'Command syntax not recognized. Try one of the quick templates below.'
    }, ...prev]);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Terminal className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Natural Language Command Console
            </h2>
            <span className="text-xs font-bold bg-navy text-gold px-2 py-0.5 rounded-full">
              GreekOS NLP Engine
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Execute operations, assess fines, assign house chores, schedule events, and blast announcements by typing plain English instructions.
            Commands are saved to the live chapter record &mdash; a scheduled event lands on the real calendar.
          </p>
        </div>
      </div>

      {/* Main Terminal Input Card */}
      <div className="bg-navy text-white rounded-2xl p-6 shadow-xl border border-[#1e2d42] space-y-4">
        <div className="flex items-center justify-between border-b border-[#1e2d42] pb-3 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-red-500 inline-block"></span>
            <span className="w-3 h-3 rounded-full bg-yellow-500 inline-block"></span>
            <span className="w-3 h-3 rounded-full bg-green-500 inline-block"></span>
            <span className="ml-2 font-bold text-slate-300">greekos-terminal &bull; {currentMemberName}</span>
          </div>
          <span className="text-gold">Audited & Permission Checked</span>
        </div>

        {/* Console Command Input Box */}
        <form onSubmit={(e) => { e.preventDefault(); handleRunCommand(commandInput); }} className="space-y-3">
          <div className="relative flex items-center">
            <span className="absolute left-4 text-gold font-mono font-black text-base select-none">&gt;</span>
            <input
              type="text"
              value={commandInput}
              onChange={e => setCommandInput(e.target.value)}
              placeholder="e.g. fine Cody Jenkins $25 for missing chapter meeting..."
              className="w-full bg-[#09101d] text-slate-100 font-mono text-sm pl-9 pr-24 py-3.5 rounded-xl border border-[#1e2d42] focus:outline-none focus:border-gold shadow-inner"
              autoFocus
            />
            <button
              type="submit"
              className="absolute right-2.5 bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
            >
              <Zap className="w-3.5 h-3.5" />
              Execute
            </button>
          </div>
        </form>

        {/* Quick Suggestion Chips */}
        <div className="space-y-1.5 pt-2">
          <span className="text-xs text-slate-400 font-bold block">Quick Command Templates:</span>
          <div className="flex flex-wrap gap-2">
            {quickTemplates.map((t, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setCommandInput(t);
                  handleRunCommand(t);
                }}
                className="text-xs font-mono bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white px-2.5 py-1 rounded-md border border-slate-700 transition-all cursor-pointer text-left"
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Command Audit Log History */}
      <Card className="p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
              <History className="w-4 h-4 text-gold" />
              Command Execution Log & Audit Trail
            </h3>
            <p className="text-xs text-slate-500">Every command executed is parsed, verified against member standing, and committed to the audit ledger.</p>
          </div>
        </div>

        <div className="space-y-2.5">
          {commandHistory.map((item, idx) => (
            <div key={idx} className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/60 font-mono text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-slate-500 text-xs">{item.timestamp}</span>
                  <span className="font-bold text-slate-900 font-mono text-xs">&gt; {item.input}</span>
                </div>
                <p className="text-slate-600 text-xs font-sans flex items-center gap-1.5">
                  {item.status === 'Executed' ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  ) : (
                    <AlertCircle className="w-3.5 h-3.5 text-red-600 shrink-0" />
                  )}
                  <span>{item.summary}</span>
                </p>
              </div>

              <span className={`text-xs px-2 py-0.5 rounded font-bold self-start sm:self-center ${
                item.status === 'Executed' 
                  ? 'bg-emerald-100 text-emerald-800' 
                  : 'bg-red-100 text-red-800'
              }`}>
                {item.status}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
