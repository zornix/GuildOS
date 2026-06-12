"use client";

const PATHS: Record<string, string> = {
  home: "M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3v-6h6v6h3a1 1 0 001-1V10",
  cal: "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18",
  users: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 3a4 4 0 100 8 4 4 0 000-8M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75",
  dollar: "M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6",
  wallet: "M3 7a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7zM17 12h4M17 12a2 2 0 100 4h4v-4h-4zM3 8h18",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  link: "M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71",
  plus: "M12 5v14M5 12h14",
  check: "M20 6L9 17l-5-5",
  x: "M18 6L6 18M6 6l12 12",
  chev: "M9 18l6-6-6-6",
  out: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9",
  clock: "M12 2a10 10 0 100 20 10 10 0 000-20M12 6v6l4 2",
  file: "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6",
  alert: "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01",
  megaphone: "M3 11l18-5v12L3 13v-2zM11.6 16.8a3 3 0 11-5.8-1.6",
  target: "M12 2a10 10 0 100 20 10 10 0 000-20M12 6a6 6 0 100 12 6 6 0 000-12M12 10a2 2 0 100 4 2 2 0 000-4",
  zap: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  key: "M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m3 3L22 7l-3-3",
};

interface IconProps {
  type: string;
  size?: number;
}

export function Icon({ type, size = 18 }: IconProps) {
  return (
    <svg
      style={{ width: size, height: size, display: "inline-block", verticalAlign: "middle" }}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[type] || ""} />
    </svg>
  );
}
