import React, { useState } from 'react';
import { 
  BookOpen, 
  Shield, 
  AlertTriangle, 
  DollarSign, 
  Award, 
  FileText, 
  ChevronDown, 
  ChevronRight 
} from 'lucide-react';
import { ChapterRule } from '../types';

interface RulesModuleProps {
  rules: ChapterRule[];
}

export default function RulesModule({ rules }: RulesModuleProps) {
  const safeRules = rules || [];
  const [activeCategory, setActiveCategory] = useState<string>('ALL');
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(safeRules[0]?.id || null);

  const categories = ['ALL', 'Bylaws & Governance', 'Attendance & Fines', 'Risk Management & Safety', 'Academic Standing'];

  const filteredRules = safeRules.filter(r => {
    if (activeCategory === 'ALL') return true;
    return r.category === activeCategory;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Chapter Bylaws, Rules & Policies
            </h2>
            <span className="text-xs font-mono font-bold bg-navy text-gold px-2 py-0.5 rounded-full">
              Official Constitution
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Governing rules, mandatory attendance clauses, fine schedules, and IFC risk guidelines.
          </p>
        </div>
      </div>

      {/* Category selector */}
      <div className="flex flex-wrap gap-2 text-xs font-mono">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
              activeCategory === cat
                ? 'bg-navy text-gold shadow-xs'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Rules list */}
      <div className="space-y-3">
        {filteredRules.map(rule => {
          const isExpanded = expandedRuleId === rule.id;

          return (
            <div
              key={rule.id}
              className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs hover:border-slate-300 transition-all"
            >
              <div
                onClick={() => setExpandedRuleId(isExpanded ? null : rule.id)}
                className="p-4 flex items-center justify-between cursor-pointer bg-slate-50/50 hover:bg-slate-50"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono font-bold text-gold-muted bg-amber-50 px-2 py-1 rounded border border-amber-200/60">
                    {rule.category}
                  </span>
                  <h3 className="font-bold text-sm text-slate-900">{rule.title}</h3>
                </div>

                <div className="flex items-center gap-3">
                  {rule.fineAmount && (
                    <span className="text-xs font-mono font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded border border-red-200">
                      Fine: ${rule.fineAmount}
                    </span>
                  )}
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                </div>
              </div>

              {isExpanded && (
                <div className="p-5 border-t border-slate-100 bg-white space-y-3 text-xs text-slate-700 leading-relaxed">
                  <p>{rule.description || rule.content}</p>
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] font-mono text-slate-400">
                    <span>Alpha Chapter Constitution &bull; Article II &bull; Ratified 2026</span>
                    <span>Executive Board Enforced</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
