import React from 'react';
import Modal from './Modal';

interface ConfirmDialogProps {
  title: string;
  /** Who, what, consequence. Keep it to two short lines. */
  body: React.ReactNode;
  confirmLabel: string;
  tone?: 'default' | 'danger';
  onConfirm: () => void;
  onCancel: () => void;
}

/** One question, two buttons. Cancel is always on the left and never styled as primary. */
export default function ConfirmDialog({ title, body, confirmLabel, tone = 'default', onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <Modal maxWidth="max-w-sm" title={title} onClose={onCancel}>
      <div className="text-xs text-slate-700 mb-5 space-y-1">{body}</div>
      <div className="flex gap-2">
        <button type="button" onClick={onCancel} autoFocus
          className="flex-1 min-h-11 border border-slate-200 text-slate-700 font-bold rounded-lg text-xs cursor-pointer hover:bg-slate-50">
          Cancel
        </button>
        <button type="button" onClick={onConfirm}
          className={`flex-1 min-h-11 font-bold rounded-lg text-xs cursor-pointer ${tone === 'danger' ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-navy hover:bg-slate-800 text-gold'}`}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
