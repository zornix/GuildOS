import { Shield } from 'lucide-react';

/** Shown instead of a tab that has no backend behind it yet. */
export default function DemoGate({ onContinue }: { onContinue: () => void }) {
  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-8 max-w-xl mx-auto text-center shadow-xs">
      <Shield className="w-8 h-8 text-gold mx-auto mb-3" />
      <h2 className="font-display font-bold text-lg text-slate-900 mb-2">Demo mode only</h2>
      <p className="text-sm text-slate-500 mb-5">
        This feature isn't wired to the backend yet — what you see next is demo data and nothing is saved.
      </p>
      <button
        onClick={onContinue}
        className="bg-navy hover:bg-[#16304f] text-white text-xs font-semibold px-4 py-2.5 rounded-xl transition-all cursor-pointer"
      >
        Continue with demo data
      </button>
    </div>
  );
}
