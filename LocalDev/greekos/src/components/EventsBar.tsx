import { Plus } from 'lucide-react';
import { EVENT_FILTER_TYPES } from '../lib/events';
import type { EventsView } from '../hooks/useEventsChrome';

interface EventsBarProps {
  view: EventsView;
  onViewChange: (view: EventsView) => void;
  filterType: string;
  onFilterChange: (type: string) => void;
  isOfficer: boolean;
  onCreate: () => void;
}

/** One horizontal bar: type chips, list/calendar toggle, officer Create. */
export default function EventsBar({ view, onViewChange, filterType, onFilterChange, isOfficer, onCreate }: EventsBarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3">
      <div role="group" aria-label="Filter events by type" className="flex flex-wrap gap-1.5 flex-1">
        {EVENT_FILTER_TYPES.map(t => (
          <button
            key={t}
            type="button"
            aria-pressed={filterType === t}
            onClick={() => onFilterChange(t)}
            className={`text-xs px-2.5 py-1.5 min-h-9 rounded-md font-semibold transition-all cursor-pointer ${
              filterType === t ? 'bg-navy text-gold shadow-xs' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div role="group" aria-label="Events view" className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg w-fit">
        {(['calendar', 'list'] as const).map(v => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => onViewChange(v)}
            className={`px-3 py-2 min-h-9 rounded-md text-xs font-medium capitalize transition-all cursor-pointer ${
              view === v ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      {isOfficer && (
        <button
          type="button"
          onClick={onCreate}
          className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center justify-center gap-2 transition-all cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          Create event
        </button>
      )}
    </div>
  );
}
