import React from 'react';

interface ModalProps {
  children: React.ReactNode;
  /** Tailwind max-width for the panel. */
  maxWidth?: string;
  /** Extra panel classes (e.g. text-center space-y-4). */
  className?: string;
  /** Overlay tint override. */
  overlayClassName?: string;
}

/** Fixed overlay + centered white panel. Shared shell for every modal in the app. */
export default function Modal({
  children,
  maxWidth = 'max-w-md',
  className = '',
  overlayClassName = 'bg-slate-900/60'
}: ModalProps) {
  return (
    <div className={`fixed inset-0 ${overlayClassName} backdrop-blur-xs flex items-center justify-center p-4 z-50`}>
      <div className={`bg-white rounded-2xl border border-slate-200 shadow-2xl ${maxWidth} w-full p-6 animate-in fade-in zoom-in duration-150 ${className}`}>
        {children}
      </div>
    </div>
  );
}
