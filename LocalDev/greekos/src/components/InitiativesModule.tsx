import React, { useState } from 'react';
import { 
  Sparkles, 
  Plus, 
  Users, 
  CheckCircle2, 
  Clock, 
  Calendar, 
  Target, 
  Layers,
  XCircle,
  AlertCircle
} from 'lucide-react';
import { Initiative, EventJob, Member } from '../types';
import Modal from './ui/Modal';
import Card from './ui/Card';

interface InitiativesModuleProps {
  initiatives: Initiative[];
  members: Member[];
  isOfficer: boolean;
  currentMemberName: string;
  onAddInitiative: (init: Omit<Initiative, 'id'>) => void;
  onAddJobToInitiative: (initId: string, job: Omit<EventJob, 'id' | 'claimants' | 'status'>) => void;
  onClaimInitiativeJob: (initId: string, jobId: string, memberId: string, memberName: string) => void;
  onUnclaimInitiativeJob: (initId: string, jobId: string, memberId: string) => void;
  onReportInitiativeJobDone: (initId: string, jobId: string, memberName: string) => void;
  onApproveInitiativeJob: (initId: string, jobId: string, approverName: string) => void;
}

export default function InitiativesModule({
  initiatives,
  members,
  isOfficer,
  currentMemberName,
  onAddInitiative,
  onAddJobToInitiative,
  onClaimInitiativeJob,
  onUnclaimInitiativeJob,
  onReportInitiativeJobDone,
  onApproveInitiativeJob
}: InitiativesModuleProps) {
  const safeInitiatives = initiatives || [];
  const safeMembers = members || [];
  const [selectedInitId, setSelectedInitId] = useState<string>(safeInitiatives[0]?.id || '');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddJobModal, setShowAddJobModal] = useState(false);

  // New Initiative Form State
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<Initiative['category']>('Philanthropy');
  const [leadChairs, setLeadChairs] = useState<string[]>([currentMemberName]);
  const [startDate, setStartDate] = useState('2026-07-15');
  const [targetDate, setTargetDate] = useState('2026-10-01');

  // Job Form State
  const [jobTitle, setJobTitle] = useState('');
  const [jobDesc, setJobDesc] = useState('');
  const [jobPeopleNeeded, setJobPeopleNeeded] = useState(2);

  const selectedInit = safeInitiatives.find(i => i.id === selectedInitId) || safeInitiatives[0];
  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (leadChairs.length === 0) return;
    onAddInitiative({
      title,
      description,
      category,
      leadChairs,
      startDate,
      targetDate,
      status: 'Active',
      jobs: [
        {
          id: 'ijob_' + Math.random().toString(36).substring(2, 9),
          title: 'Kickoff Proposal & Project Budget Outline',
          description: 'Draft the 1-page milestone roadmap and vendor quotes.',
          peopleNeeded: 1,
          claimants: [],
          status: 'To Do'
        }
      ]
    });

    setTitle('');
    setDescription('');
    setShowCreateModal(false);
  };

  const handleAddJobSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInit) return;
    onAddJobToInitiative(selectedInit.id, {
      title: jobTitle,
      description: jobDesc,
      peopleNeeded: Number(jobPeopleNeeded) || 1
    });

    setJobTitle('');
    setJobDesc('');
    setJobPeopleNeeded(2);
    setShowAddJobModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Chair Initiatives & Special Projects
            </h2>
            <span className="text-xs font-mono font-bold bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full border border-purple-200">
              Chair-Led
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Chair-led projects run independently by chapter committee leads. Any number of chairs can manage initiatives without officer gates.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer w-full sm:w-auto justify-center"
        >
          <Plus className="w-4 h-4" />
          Launch New Initiative
        </button>
      </div>

      {/* Grid: Left Initiatives List, Right Initiative Canvas */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left: Initiatives Directory */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-bold font-mono text-slate-500 uppercase tracking-wider">Active Initiatives</span>
            <span className="text-xs font-mono text-slate-400">{initiatives.length} total</span>
          </div>

          {safeInitiatives.map(init => {
            const isSelected = init.id === selectedInitId;
            const initJobs = init.jobs || [];
            const completedJobs = initJobs.filter(j => j.status === 'Approved').length;
            const progress = initJobs.length > 0 ? Math.round((completedJobs / initJobs.length) * 100) : 0;

            return (
              <div
                key={init.id}
                onClick={() => setSelectedInitId(init.id)}
                className={`p-4 rounded-xl border transition-all cursor-pointer ${
                  isSelected 
                    ? 'bg-white border-gold shadow-md ring-2 ring-gold/20' 
                    : 'bg-white border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-purple-700 bg-purple-50 px-2 py-0.5 rounded">
                    {init.category}
                  </span>
                  <span className="text-[9px] font-mono text-slate-400">
                    Target: {init.targetDate.substring(5)}
                  </span>
                </div>

                <h3 className="font-bold text-sm text-slate-900 leading-snug mb-1">
                  {init.title}
                </h3>

                <p className="text-xs text-slate-500 line-clamp-2 mb-3">
                  {init.description}
                </p>

                {/* Progress bar */}
                <div className="space-y-1 pt-2 border-t border-slate-100">
                  <div className="flex justify-between text-[10px] font-mono text-slate-500">
                    <span>Progress ({completedJobs}/{init.jobs.length} jobs)</span>
                    <span className="font-bold">{progress}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-gold rounded-full transition-all" style={{ width: `${progress}%` }}></div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Selected Initiative Details & Jobs */}
        {selectedInit ? (
          <div className="lg:col-span-2 space-y-6">
            <Card className="p-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold bg-purple-100 text-purple-900 px-2.5 py-0.5 rounded">
                      {selectedInit.category}
                    </span>
                    <span className="text-xs font-mono bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded font-semibold border border-emerald-200">
                      {selectedInit.status}
                    </span>
                  </div>

                  <h2 className="text-xl font-display font-extrabold text-slate-900 tracking-tight pt-1">
                    {selectedInit.title}
                  </h2>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    {selectedInit.description}
                  </p>
                </div>

                <div className="text-right text-xs shrink-0 font-mono">
                  <span className="text-slate-400 block text-[10px]">Timeline</span>
                  <span className="font-semibold text-slate-800">{selectedInit.startDate} &rarr; {selectedInit.targetDate}</span>
                </div>
              </div>

              {/* Lead Chairs Section (Never Zero Chairs) */}
              <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/70 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-700 font-mono uppercase flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5 text-gold" />
                    Assigned Lead Chairs
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {selectedInit.leadChairs.length} Chair{selectedInit.leadChairs.length > 1 ? 's' : ''} (Minimum 1 Required)
                  </span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {selectedInit.leadChairs.map(chair => (
                    <span key={chair} className="text-xs bg-white text-slate-800 px-2.5 py-1 rounded-md font-semibold border border-slate-200 shadow-2xs">
                      {chair}
                    </span>
                  ))}
                </div>
                <p className="text-[10px] text-slate-500">Lead chairs approve work reported by brothers on this initiative.</p>
              </div>
            </Card>

            {/* Initiative Jobs Section */}
            <Card className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                    <Layers className="w-5 h-5 text-gold" />
                    Initiative Tasks & Jobs ({selectedInit.jobs.length})
                  </h3>
                  <p className="text-xs text-slate-500">
                    Open duties decompose into claimable jobs open to all brothers. Chairs verify and sign off.
                  </p>
                </div>

                <button
                  onClick={() => setShowAddJobModal(true)}
                  className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Task
                </button>
              </div>

              {/* Jobs List */}
              <div className="space-y-3">
                {selectedInit.jobs.map(job => {
                  const isClaimedByMe = currentMember && job.claimants.some(c => c.memberId === currentMember.id);
                  const isFull = job.claimants.length >= job.peopleNeeded;
                  const isLeadChair = selectedInit.leadChairs.includes(currentMemberName) || isOfficer;

                  return (
                    <div key={job.id} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 transition-all space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="font-bold text-sm text-slate-900">{job.title}</h4>
                            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                              job.status === 'Approved' 
                                ? 'bg-emerald-100 text-emerald-800' 
                                : job.status === 'Done Reported' 
                                ? 'bg-blue-100 text-blue-800' 
                                : job.status === 'In Progress' 
                                ? 'bg-amber-100 text-amber-800' 
                                : 'bg-slate-200 text-slate-700'
                            }`}>
                              {job.status}
                            </span>
                          </div>
                          <p className="text-xs text-slate-600 mt-1">{job.description}</p>
                        </div>

                        <span className="text-xs font-mono font-bold bg-white px-2.5 py-1 rounded border border-slate-200 text-slate-800 shrink-0">
                          {job.claimants.length} / {job.peopleNeeded} Claimed
                        </span>
                      </div>

                      {/* Claimants */}
                      <div className="flex items-center gap-2 text-xs pt-1">
                        <span className="text-[10px] text-slate-400 font-mono uppercase">Claimants:</span>
                        {job.claimants.length === 0 ? (
                          <span className="text-slate-400 italic">No volunteers yet</span>
                        ) : (
                          job.claimants.map(c => (
                            <span key={c.memberId} className="bg-white border border-slate-200 text-slate-800 font-semibold px-2 py-0.5 rounded text-xs">
                              {c.memberName}
                            </span>
                          ))
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-200/60">
                        <div className="flex items-center gap-2">
                          {!isClaimedByMe && !isFull && job.status !== 'Approved' && (
                            <button
                              onClick={() => {
                                if (currentMember) {
                                  onClaimInitiativeJob(selectedInit.id, job.id, currentMember.id, currentMember.name);
                                }
                              }}
                              className="text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer"
                            >
                              Claim Task
                            </button>
                          )}

                          {isClaimedByMe && job.status !== 'Approved' && (
                            <button
                              onClick={() => {
                                if (currentMember) {
                                  onUnclaimInitiativeJob(selectedInit.id, job.id, currentMember.id);
                                }
                              }}
                              className="text-xs font-semibold px-3 py-1.5 rounded-lg border bg-red-50 text-red-700 border-red-200 hover:bg-red-100 cursor-pointer"
                            >
                              Unclaim
                            </button>
                          )}

                          {isClaimedByMe && job.status === 'In Progress' && (
                            <button
                              onClick={() => onReportInitiativeJobDone(selectedInit.id, job.id, currentMemberName)}
                              className="text-xs bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer"
                            >
                              Report Task Completed
                            </button>
                          )}
                        </div>

                        {/* Chair Sign-off */}
                        {isLeadChair && job.status === 'Done Reported' && (
                          <button
                            onClick={() => onApproveInitiativeJob(selectedInit.id, job.id, currentMemberName)}
                            className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Chair Sign-Off
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        ) : (
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-400">
            No initiative selected.
          </div>
        )}
      </div>

      {/* MODAL: Create Initiative */}
      {showCreateModal && (
        <Modal maxWidth="max-w-lg">
            <div className="flex justify-between items-center mb-4 border-b border-slate-100 pb-3">
              <h3 className="font-display font-extrabold text-base text-slate-900 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-gold" />
                Launch Chair-Led Initiative
              </h3>
              <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-600 font-bold">✕</button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Initiative Title</label>
                <input
                  type="text"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="e.g. Chapter Room Renovation & Soundproofing"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Project Scope & Description</label>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Explain goals, key deliverables, and expectations..."
                  rows={3}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Category</label>
                  <select
                    value={category}
                    onChange={e => setCategory(e.target.value as any)}
                    className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    <option value="Philanthropy">Philanthropy</option>
                    <option value="Social">Social</option>
                    <option value="Housing">Housing</option>
                    <option value="Scholarship">Scholarship</option>
                    <option value="Alumni Relations">Alumni Relations</option>
                    <option value="Rush">Rush</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Lead Chair (Creator)</label>
                  <input
                    type="text"
                    value={leadChairs.join(', ')}
                    disabled
                    className="w-full text-sm border border-slate-200 rounded-lg p-2.5 bg-slate-50 text-slate-700"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Start Date</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={e => setStartDate(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Target Completion</label>
                  <input
                    type="date"
                    value={targetDate}
                    onChange={e => setTargetDate(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 rounded-lg text-xs uppercase tracking-wider transition-all mt-3 cursor-pointer"
              >
                Create Initiative & Publish Tasks
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Add Job to Initiative */}
      {showAddJobModal && selectedInit && (
        <Modal>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <Plus className="w-5 h-5 text-gold" />
                Add Task to Initiative
              </h3>
              <button onClick={() => setShowAddJobModal(false)} className="text-slate-400 hover:text-slate-600 font-bold">✕</button>
            </div>

            <form onSubmit={handleAddJobSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Task Title</label>
                <input
                  type="text"
                  value={jobTitle}
                  onChange={e => setJobTitle(e.target.value)}
                  placeholder="e.g. Procure acoustic panels"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Description</label>
                <textarea
                  value={jobDesc}
                  onChange={e => setJobDesc(e.target.value)}
                  placeholder="Details for brothers taking this on..."
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Brothers Needed</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={jobPeopleNeeded}
                  onChange={e => setJobPeopleNeeded(Number(e.target.value))}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full bg-gold hover:bg-[#c5a02b] text-navy font-bold py-3 rounded-lg text-xs uppercase tracking-wider transition-all cursor-pointer"
              >
                Add Task
              </button>
            </form>
        </Modal>
      )}
    </div>
  );
}
