import React, { useState } from 'react';
import { 
  CalendarDays, 
  ChevronLeft, 
  ChevronRight, 
  MapPin, 
  Clock, 
  AlertTriangle, 
  Sparkles, 
  Megaphone, 
  Calendar as CalendarIcon,
  CheckCircle2,
  Users
} from 'lucide-react';
import { ChapterEvent, Initiative, Announcement } from '../types';
import { isoDay, monthCells } from '../formatters';
import Card from './ui/Card';

interface CalendarModuleProps {
  events: ChapterEvent[];
  initiatives: Initiative[];
  announcements: Announcement[];
  currentMemberName: string;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onNavigateToEvent: (eventId: string) => void;
}

export default function CalendarModule({
  events,
  initiatives,
  announcements,
  currentMemberName,
  onVolunteerOrganizer,
  onNavigateToEvent
}: CalendarModuleProps) {
  const today = isoDay();
  const [selectedDateStr, setSelectedDateStr] = useState<string>(today);
  // The month on screen: the 1st of it, so prev/next is plain Date arithmetic.
  const [month, setMonth] = useState<Date>(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const shiftMonth = (delta: number) =>
    setMonth(m => new Date(m.getFullYear(), m.getMonth() + delta, 1));

  const calendarCells = monthCells(month.getFullYear(), month.getMonth()).map(dateStr => ({
    day: dateStr ? Number(dateStr.substring(8)) : null,
    dateStr
  }));

  const safeEvents = events || [];
  const safeInitiatives = initiatives || [];
  const safeAnnouncements = announcements || [];

  // An announcement with a backend calendar slot sits on that day; one without
  // falls back to the day it was posted.
  const announcementDay = (a: Announcement) => a.calendarDate || a.date;

  // Items on selected day
  const dayEvents = safeEvents.filter(e => e.date === selectedDateStr);
  const dayInitiatives = safeInitiatives.filter(i => (i.startDate || '') <= selectedDateStr && (i.targetDate || '') >= selectedDateStr);
  const dayAnnouncements = safeAnnouncements.filter(a => announcementDay(a) === selectedDateStr);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <CalendarDays className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Chapter Master Calendar
            </h2>
            <span className="text-xs font-mono font-bold bg-navy text-gold px-2 py-0.5 rounded-full">
              Unified Schedule
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            One single calendar showing chapter events, chair initiatives, and executive announcements.
          </p>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
          <span className="flex items-center gap-1 text-slate-700 font-semibold">
            <span className="w-2.5 h-2.5 rounded-full bg-gold"></span> Chapter Events
          </span>
          <span className="flex items-center gap-1 text-slate-700 font-semibold">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-500"></span> Initiatives
          </span>
          <span className="flex items-center gap-1 text-slate-700 font-semibold">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span> Announcements
          </span>
        </div>
      </div>

      {/* Main Grid: 2 cols Calendar on Left, 1 col Day Details on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar Box */}
        <Card className="lg:col-span-2 p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h3 className="font-display font-extrabold text-slate-900 text-lg">
                {month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              </h3>
              <p className="text-xs text-slate-400">Click any date to inspect scheduled chapter operations.</p>
            </div>

            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg text-xs font-mono font-bold text-slate-600">
              <button
                onClick={() => shiftMonth(-1)}
                aria-label="Previous month"
                className="px-2 py-1 rounded hover:bg-white hover:text-slate-900 transition-all cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}
                className="px-2.5 py-1 bg-white text-slate-900 rounded shadow-2xs cursor-pointer"
              >
                {month.toLocaleDateString('en-US', { month: 'short' })}
              </button>
              <button
                onClick={() => shiftMonth(1)}
                aria-label="Next month"
                className="px-2 py-1 rounded hover:bg-white hover:text-slate-900 transition-all cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Weekday headers */}
          <div className="grid grid-cols-7 text-center text-xs font-bold text-slate-400 uppercase tracking-widest py-1 font-mono">
            <span>Sun</span>
            <span>Mon</span>
            <span>Tue</span>
            <span>Wed</span>
            <span>Thu</span>
            <span>Fri</span>
            <span>Sat</span>
          </div>

          {/* Calendar Grid */}
          <div className="grid grid-cols-7 gap-1.5">
            {calendarCells.map((cell, idx) => {
              const isSelected = cell.dateStr === selectedDateStr;
              const isToday = cell.dateStr === today;
              const cellEvents = cell.dateStr ? safeEvents.filter(e => e.date === cell.dateStr) : [];
              const cellAnnouncements = cell.dateStr ? safeAnnouncements.filter(a => announcementDay(a) === cell.dateStr) : [];
              const hasOrganizersNeeded = cellEvents.some(e => (e.organizerCount ?? (e.organizers || []).length) === 0);

              return (
                <div
                  key={idx}
                  onClick={() => cell.dateStr && setSelectedDateStr(cell.dateStr)}
                  className={`min-h-[84px] p-1.5 rounded-xl border flex flex-col justify-between transition-all ${
                    !cell.day
                      ? 'bg-slate-50/40 border-dashed border-slate-100 cursor-default'
                      : isSelected
                      ? 'bg-slate-900 text-white border-slate-900 shadow-md ring-2 ring-gold/30 cursor-pointer'
                      : isToday
                      ? 'bg-amber-50/60 border-gold hover:border-gold cursor-pointer'
                      : 'bg-white border-slate-200 hover:border-gold cursor-pointer'
                  }`}
                >
                  {cell.day && (
                    <>
                      <div className="flex justify-between items-start">
                        <span className={`text-xs font-mono font-bold ${
                          isSelected ? 'text-gold' : isToday ? 'text-gold-muted' : 'text-slate-700'
                        }`}>
                          {cell.day}
                        </span>

                        {hasOrganizersNeeded && (
                          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" title="Organizers Needed!"></span>
                        )}
                      </div>

                      {/* Content dots & small pills */}
                      <div className="space-y-1 mt-auto">
                        {cellEvents.map(e => (
                          <React.Fragment key={e.id}>
                            <div
                              className={`text-[9px] truncate rounded px-1 py-0.5 font-semibold ${
                                isSelected
                                  ? 'bg-slate-800 text-gold'
                                  : 'bg-amber-50 text-amber-900 border border-amber-200/60'
                              }`}
                            >
                              {e.title}
                            </div>

                            {!!e.openJobCount && (
                              <div className="text-[9px] truncate rounded px-1 py-0.5 font-semibold bg-gold/20 text-gold-muted">
                                {e.openJobCount} open jobs
                              </div>
                            )}
                          </React.Fragment>
                        ))}

                        {cellAnnouncements.map(a => (
                          <div 
                            key={a.id}
                            className={`text-[9px] truncate rounded px-1 py-0.5 font-semibold ${
                              isSelected 
                                ? 'bg-blue-900/60 text-blue-300' 
                                : 'bg-blue-50 text-blue-800 border border-blue-200/60'
                            }`}
                          >
                            📢 {a.title}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        {/* Right Column: Selected Day Schedule Breakdown */}
        <div className="space-y-4">
          <Card className="p-5 space-y-4">
            <div className="border-b border-slate-100 pb-3">
              <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">Agenda for Date</span>
              <h3 className="font-display font-extrabold text-slate-900 text-lg">
                {selectedDateStr}
              </h3>
            </div>

            {/* Events for this day */}
            <div className="space-y-3">
              <span className="text-xs font-mono font-bold text-slate-500 uppercase tracking-wider block">
                Chapter Events ({dayEvents.length})
              </span>

              {dayEvents.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No chapter events scheduled on this day.</p>
              ) : (
                dayEvents.map(e => {
                  const hasNoOrganizers = (e.organizerCount ?? (e.organizers || []).length) === 0;

                  return (
                    <div key={e.id} className="p-3 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-1.5">
                            <h4 className="font-bold text-xs text-slate-900">{e.title}</h4>
                            {e.required && (
                              <span className="text-[8px] font-mono font-bold bg-red-100 text-red-800 px-1 rounded uppercase">Mandatory</span>
                            )}
                          </div>
                          <span className="text-[10px] text-gold-muted font-semibold uppercase font-mono">{e.type}</span>
                        </div>

                        <span className="text-[10px] font-mono font-bold bg-white text-slate-800 px-2 py-0.5 rounded border border-slate-200">
                          +{e.points} pts
                        </span>
                      </div>

                      <div className="text-[11px] text-slate-500 space-y-0.5">
                        <p className="flex items-center gap-1.5"><Clock className="w-3 h-3 text-slate-400 shrink-0" /> {e.time}</p>
                        <p className="flex items-center gap-1.5"><MapPin className="w-3 h-3 text-slate-400 shrink-0" /> {e.location}</p>
                      </div>

                      {/* Organizers Needed Flag & Action */}
                      {hasNoOrganizers && (
                        <div className="p-2 bg-red-100 text-red-900 rounded-lg flex items-center justify-between text-xs">
                          <span className="font-bold flex items-center gap-1 text-[11px]">
                            <AlertTriangle className="w-3.5 h-3.5 text-red-600 shrink-0" />
                            Organizers Needed!
                          </span>
                          <button
                            onClick={() => onVolunteerOrganizer(e.id, currentMemberName)}
                            className="text-[10px] font-bold bg-red-700 text-white hover:bg-red-800 px-2 py-1 rounded cursor-pointer transition-all"
                          >
                            Volunteer
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Announcements for this day */}
            <div className="space-y-3 pt-3 border-t border-slate-100">
              <span className="text-xs font-mono font-bold text-slate-500 uppercase tracking-wider block">
                Broadcast Announcements ({dayAnnouncements.length})
              </span>

              {dayAnnouncements.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No executive broadcasts on this day.</p>
              ) : (
                dayAnnouncements.map(a => (
                  <div key={a.id} className="p-3 rounded-xl border border-blue-200 bg-blue-50/50 space-y-1">
                    <div className="flex items-center justify-between">
                      <h4 className="font-bold text-xs text-blue-950 flex items-center gap-1">
                        <Megaphone className="w-3.5 h-3.5 text-blue-600" />
                        {a.title}
                      </h4>
                      <span className="text-[9px] font-mono bg-blue-200 text-blue-900 px-1.5 rounded font-bold">
                        {a.priority}
                      </span>
                    </div>
                    <p className="text-xs text-blue-900 leading-relaxed">{a.content}</p>
                    <span className="text-[10px] text-blue-600 block pt-1 font-mono">&mdash; {a.author}</span>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
