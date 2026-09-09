import { useState } from 'react';

export type EventsView = 'calendar' | 'list';

/** The Events screen's chrome: which view, which type filter, whether the
 *  create form is open, and which event is selected. Lives above the screen
 *  so Home can open the form or jump to an event. */
export function useEventsChrome() {
  const [view, setView] = useState<EventsView>('calendar');
  const [filterType, setFilterType] = useState<string>('All');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  /** The create form lives in the list view. */
  const openCreate = () => {
    setView('list');
    setCreateOpen(true);
  };

  /** Calendar day click and Home tiles land on the event's detail. */
  const openEvent = (eventId: string) => {
    setSelectedEventId(eventId);
    setView('list');
  };

  return {
    view, setView, filterType, setFilterType, createOpen, setCreateOpen,
    selectedEventId, setSelectedEventId, openCreate, openEvent
  };
}
