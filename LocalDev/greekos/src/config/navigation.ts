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
  /** Shown when the session holds this module's permission key. */
  permission?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Home', icon: LayoutDashboard },
  { id: 'events', label: 'Events', icon: Calendar },
  { id: 'initiatives', label: 'Initiatives', icon: Sparkles },
  { id: 'attendance', label: 'Attendance', icon: CheckSquare },
  { id: 'finance', label: 'Treasury', icon: DollarSign },
  { id: 'tasks', label: 'Jobs', icon: ClipboardList },
  { id: 'roster', label: 'Roster', icon: Users },
  { id: 'recruitment', label: 'Recruitment', icon: UserPlus, permission: 'recruitment:pipeline:view' },
  // Not a demo: every command it runs is a real write (fines, jobs, events, blasts).
  { id: 'command', label: 'Command console', icon: Terminal, permission: 'nl_controller:execute' }
];

/** Prototype surfaces with no backend — collapsed at the bottom of the nav. */
export const DEMO_NAV_ITEMS: NavItem[] = [
  { id: 'rules', label: 'Bylaws', icon: BookOpen, demo: true },
  { id: 'outbox', label: 'Message outbox', icon: Send, demo: true }
];

export const isDemoTab = (tabId: string) => DEMO_NAV_ITEMS.some(i => i.id === tabId);
