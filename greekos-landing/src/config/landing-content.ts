export type NavLink = {
  label: string;
  href: string;
};

export type Feature = {
  title: string;
  description: string;
  icon: string;
  eyebrow: string;
  gradient: string;
  size: "large" | "small";
};

export type Step = {
  number: string;
  title: string;
  description: string;
};

export type PricingPlan = {
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  cta: string;
  highlight: boolean;
};

export const NAV_LINKS: NavLink[] = [
  { label: "Features", href: "#features" },
  { label: "AI Layer", href: "#ai-layer" },
  { label: "How It Works", href: "#workflow" },
  { label: "Pricing", href: "#pricing" },
];

export const FEATURES: Feature[] = [
  {
    title: "Treasury & Dues",
    description:
      "Track dues, rent, fines, Zelle proof uploads, payment status, approvals, and officer edits without chasing screenshots in group chats.",
    icon: "₿",
    eyebrow: "Finance",
    gradient: "feature-gradient-1",
    size: "large",
  },
  {
    title: "Event Operations",
    description:
      "Create events, verify attendance, manage excuses, and auto-generate setup, cleanup, tabling, and risk tasks.",
    icon: "✦",
    eyebrow: "Events",
    gradient: "feature-gradient-2",
    size: "small",
  },
  {
    title: "Member Accountability",
    description:
      "Centralize roles, class years, attendance, member engagement, service hours, fines, and chapter standing in one member record.",
    icon: "Σ",
    eyebrow: "Roster",
    gradient: "feature-gradient-3",
    size: "small",
  },
  {
    title: "Officer Permissions",
    description:
      "Give chapter executives access to the exact tools they need.",
    icon: "Ω",
    eyebrow: "Exec",
    gradient: "feature-gradient-1",
    size: "small",
  },
  {
    title: "Standards & Compliance",
    description:
      "Track event coordination, GPA requirements, national reporting, and chapter expectations before they become emergencies.",
    icon: "Λ",
    eyebrow: "Standards",
    gradient: "feature-gradient-2",
    size: "small",
  },
  {
    title: "Chapter Knowledge Base",
    description:
      "Turn chapter bylaws, transition docs, meeting minutes, history, and more into searchable institutional memory.",
    icon: "◈",
    eyebrow: "Knowledge",
    gradient: "feature-gradient-3",
    size: "large",
  },
];

export const AI_FEATURES: string[] = [
  "Ask questions about bylaws, officer duties, event history, or chapter policy",
  "Generate task lists for philanthropy weeks, parties, brotherhood events, and meetings",
  "Summarize exec notes into action items, owners, deadlines, and follow-ups",
  "Flag unpaid balances, missing attendance, incomplete training, and risky patterns",
];

export const STEPS: Step[] = [
  {
    number: "01",
    title: "Map the chapter",
    description:
      "Add members, officers, committees, dues categories, house roles, events, and chapter-specific workflows.",
  },
  {
    number: "02",
    title: "Run operations",
    description:
      "Use GreekOS for finances, events, member accountability, and chapter management. See the AI layer in action.",
  },
  {
    number: "03",
    title: "Keep memory alive",
    description:
      "Every semester adds more context, so future officers inherit a system instead of a half-broken folder of old files.",
  },
];

export const PRICING: PricingPlan[] = [
  {
    name: "Founding Chapter",
    price: "Free",
    period: "pilot",
    description: "For early chapters helping shape GreekOS before broad launch.",
    features: ["Core roster", "Event attendance", "Fine tracking", "Officer dashboard"],
    cta: "Join the pilot",
    highlight: false,
  },
  {
    name: "Chapter OS",
    price: "$149",
    period: "/mo",
    description: "For chapters ready to replace spreadsheets and group-chat operations.",
    features: [
      "Treasury workflows",
      "Zelle proof review",
      "Task generation",
      "Role permissions",
      "AI chapter knowledge base",
    ],
    cta: "Request access",
    highlight: true,
  },
  {
    name: "Council / HQ",
    price: "Custom",
    period: "",
    description: "For multi-chapter councils and larger Greek-letter organizations.",
    features: ["Multi-chapter reporting", "Custom onboarding", "Analytics", "Roadmap partnership"],
    cta: "Talk to us",
    highlight: false,
  },
];

export const OPS: string[] = ["Dues", "Rent", "Fines", "Attendance", "Excuses", "Tasks", "Bylaws", "Reports", "Recruitment", "Transitions"];
