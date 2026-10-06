import {
  LayoutDashboard,
  Users,
  Calendar,
  DollarSign,
  ClipboardList,
  CheckSquare,
  Sparkles,
  Terminal,
  Send,
  type LucideIcon
} from 'lucide-react';

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
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
  { id: 'outbox', label: 'Outbox', icon: Send, permission: 'announcements:send' },
  { id: 'command', label: 'Command console', icon: Terminal, permission: 'nl_controller:execute' }
];
