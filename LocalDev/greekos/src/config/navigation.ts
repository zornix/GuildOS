import {
  LayoutDashboard,
  Users,
  Calendar,
  DollarSign,
  ClipboardList,
  UserPlus,
  BookOpen,
  CheckSquare,
  Sparkles,
  Send,
  CalendarDays,
  Terminal,
  type LucideIcon
} from 'lucide-react';

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  /** No backend behind this tab yet — the shell gates it behind a demo notice. */
  demo?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'events', label: 'Events & Jobs', icon: Calendar },
  { id: 'calendar', label: 'Unified Calendar', icon: CalendarDays },
  { id: 'initiatives', label: 'Chair Initiatives', icon: Sparkles },
  { id: 'attendance', label: 'Attendance & Door', icon: CheckSquare },
  { id: 'finance', label: 'Treasury & Ledger', icon: DollarSign },
  { id: 'roster', label: 'Roster & Standings', icon: Users },
  { id: 'tasks', label: 'House Tasks', icon: ClipboardList },
  { id: 'recruitment', label: 'Recruitment (PNMs)', icon: UserPlus },
  { id: 'command', label: 'Command Console', icon: Terminal, demo: true },
  { id: 'rules', label: 'Bylaws & Conduct', icon: BookOpen, demo: true },
  { id: 'outbox', label: 'SMS / Push Outbox', icon: Send, demo: true }
];

export const isDemoTab = (tabId: string) => NAV_ITEMS.some(i => i.id === tabId && i.demo);
