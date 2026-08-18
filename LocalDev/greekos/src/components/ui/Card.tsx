import React from 'react';

interface CardProps {
  children: React.ReactNode;
  /** Padding / spacing / layout variants ride on className. */
  className?: string;
  /** This project has no @types/react, so `key` is not special-cased in JSX. */
  key?: string | number;
}

/** White surface panel. Padding and spacing stay with the caller. */
export default function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 shadow-xs ${className}`}>
      {children}
    </div>
  );
}
