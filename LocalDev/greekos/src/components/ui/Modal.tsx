import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  children: React.ReactNode;
  /** Tailwind max-width for the panel. */
  maxWidth?: string;
  /** Extra panel classes (e.g. text-center space-y-4). */
  className?: string;
  /** Overlay tint override. */
  overlayClassName?: string;
  /** Heading text. Renders a header row with the close button. */
  title?: string;
  /** Escape, overlay click and the close button all call this. */
  onClose?: () => void;
}

/** Fixed overlay + centered white panel. Shared shell for every modal in the app.
 *  ponytail: no focus trap — initial focus lands on the panel, Escape and overlay
 *  close it. Add a trap only if keyboard users report tabbing out. */
export default function Modal({
  children,
  maxWidth = 'max-w-md',
  className = '',
  overlayClassName = 'bg-slate-900/60',
  title,
  onClose
}: ModalProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  // Mount only. Call sites pass an inline `onClose`, so a focus() keyed on it
  // would re-run on every keystroke in a modal form and yank focus off the input.
  useEffect(() => { panel.current?.focus(); }, []);

  useEffect(() => {
    if (!onClose) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      className={`fixed inset-0 ${overlayClassName} backdrop-blur-xs flex items-center justify-center p-4 z-50`}
    >
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        onClick={e => e.stopPropagation()}
        className={`bg-white rounded-2xl border border-slate-200 shadow-2xl ${maxWidth} w-full max-h-[calc(100dvh-2rem)] overflow-y-auto p-4 sm:p-6 animate-in fade-in zoom-in duration-150 outline-none ${className}`}
      >
        {(title || onClose) && (
          <div className="flex justify-between items-center mb-4">
            {title ? <h3 id={titleId} className="font-display font-bold text-base text-slate-900">{title}</h3> : <span />}
            {onClose && (
              <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 -mr-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
