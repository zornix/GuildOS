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
  Terminal,
  type LucideIcon
} from 'lucide-react';

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  /** No backend behind this tab yet — the shell gates it behind a demo notice. */
  demo?: boolean;
  /** Hidden from the nav while the session is in member view. */
  officerOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Home', icon: LayoutDashboard },
  { id: 'events', label: 'Events', icon: Calendar },
  { id: 'initiatives', label: 'Initiatives', icon: Sparkles },
  { id: 'attendance', label: 'Attendance', icon: CheckSquare },
  { id: 'finance', label: 'Treasury', icon: DollarSign },
  { id: 'tasks', label: 'Jobs', icon: ClipboardList },
  { id: 'roster', label: 'Roster', icon: Users },
  { id: 'recruitment', label: 'Recruitment', icon: UserPlus, officerOnly: true }
];

/** Prototype surfaces with no backend — collapsed at the bottom of the nav. */
export const DEMO_NAV_ITEMS: NavItem[] = [
  { id: 'command', label: 'Command console', icon: Terminal, demo: true },
  { id: 'rules', label: 'Bylaws', icon: BookOpen, demo: true },
  { id: 'outbox', label: 'Message outbox', icon: Send, demo: true }
];

export const isDemoTab = (tabId: string) => DEMO_NAV_ITEMS.some(i => i.id === tabId);
