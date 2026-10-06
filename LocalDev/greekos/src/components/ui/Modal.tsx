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
 *  Focus starts on the panel, Tab cycles inside it, and closing hands focus
 *  back to whatever opened it. */
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
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => opener?.focus();
  }, []);

  /** Tab from the last focusable element wraps to the first, Shift+Tab the other way. */
  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !panel.current) return;
    const focusable = panel.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) { e.preventDefault(); return; }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === panel.current)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  };

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
        onKeyDown={trapTab}
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
