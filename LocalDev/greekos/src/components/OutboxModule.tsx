import React, { useState } from 'react';
import { 
  Send, 
  Smartphone, 
  Bell, 
  Mail, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  RotateCw, 
  Filter,
  Search,
  MessageSquare
} from 'lucide-react';
import { OutboxNotification } from '../types';
import Card from './ui/Card';

interface OutboxModuleProps {
  notifications: OutboxNotification[];
  isOfficer: boolean;
  onRetryNotification: (notifId: string) => void;
  onClearDelivered: () => void;
}

export default function OutboxModule({
  notifications,
  isOfficer,
  onRetryNotification,
  onClearDelivered
}: OutboxModuleProps) {
  const safeNotifications = notifications || [];
  const [filterChannel, setFilterChannel] = useState<string>('ALL');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredNotifs = safeNotifications.filter(n => {
    if (filterChannel !== 'ALL' && n.channel !== filterChannel) return false;
    if (filterStatus !== 'ALL' && n.status !== filterStatus) return false;
    if (searchTerm && !(n.recipient || '').toLowerCase().includes(searchTerm.toLowerCase()) && !(n.message || '').toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  const getChannelIcon = (channel: string) => {
    switch (channel) {
      case 'SMS':
        return <Smartphone className="w-3.5 h-3.5 text-emerald-600" />;
      case 'Push':
        return <Bell className="w-3.5 h-3.5 text-blue-600" />;
      case 'Email':
        return <Mail className="w-3.5 h-3.5 text-purple-600" />;
      default:
        return <MessageSquare className="w-3.5 h-3.5 text-slate-600" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Delivered':
        return <span className="bg-emerald-100 text-emerald-800 text-xs font-bold px-2 py-0.5 rounded flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Delivered</span>;
      case 'Sent':
        return <span className="bg-blue-100 text-blue-800 text-xs font-bold px-2 py-0.5 rounded flex items-center gap-1"><Send className="w-3 h-3" /> Sent</span>;
      case 'Queued':
        return <span className="bg-amber-100 text-amber-800 text-xs font-bold px-2 py-0.5 rounded flex items-center gap-1"><Clock className="w-3 h-3" /> Queued</span>;
      case 'Failed':
        return <span className="bg-red-100 text-red-800 text-xs font-bold px-2 py-0.5 rounded flex items-center gap-1"><AlertCircle className="w-3 h-3" /> Failed</span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Send className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Message outbox
            </h2>
            <span className="text-xs font-bold bg-navy text-gold px-2 py-0.5 rounded-full">
              Real-time Queue
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Real-time delivery log for broadcast announcements, fine citations, job rejection feedback, and security shift swap invitations.
          </p>
        </div>

        {isOfficer && (
          <button
            onClick={onClearDelivered}
            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-3 py-2 rounded-lg transition-all cursor-pointer"
          >
            Clear Delivered ({notifications.filter(n => n.status === 'Delivered').length})
          </button>
        )}
      </div>

      {/* Stats ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-4 space-y-1">
          <span className="text-xs text-slate-500 font-bold">Total Dispatched</span>
          <div className="text-xl font-display font-black text-slate-900">{notifications.length}</div>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-xs text-emerald-700 font-bold">Delivered</span>
          <div className="text-xl font-display font-black text-emerald-600">
            {notifications.filter(n => n.status === 'Delivered').length}
          </div>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-xs text-blue-700 font-bold">In Flight / Sent</span>
          <div className="text-xl font-display font-black text-blue-600">
            {notifications.filter(n => n.status === 'Sent' || n.status === 'Queued').length}
          </div>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-xs text-red-700 font-bold">Delivery Failures</span>
          <div className="text-xl font-display font-black text-red-600">
            {notifications.filter(n => n.status === 'Failed').length}
          </div>
        </Card>
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-500 text-xs font-bold">Channel:</span>
          {['ALL', 'SMS', 'Push', 'Email'].map(ch => (
            <button
              key={ch}
              onClick={() => setFilterChannel(ch)}
              className={`px-2.5 py-1 rounded-md font-semibold cursor-pointer transition-all ${
                filterChannel === ch ? 'bg-navy text-gold' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {ch}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            aria-label="Search messages"
            placeholder="Search recipient or message..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-gold"
          />
        </div>
      </Card>

      {/* Outbox Table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 text-xs">
              <tr>
                <th className="py-3 px-4">Channel & Time</th>
                <th className="py-3 px-4">Recipient</th>
                <th className="py-3 px-4">Message Content</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredNotifs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-500 italic">
                    Outbox is clear. No notification messages match filter.
                  </td>
                </tr>
              ) : (
                filteredNotifs.map(n => (
                  <tr key={n.id} className="hover:bg-slate-50/60">
                    <td className="py-3 px-4 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 font-bold text-slate-800">
                        {getChannelIcon(n.channel)}
                        <span>{n.channel}</span>
                      </div>
                      <div className="text-xs text-slate-500">{n.timestamp || n.createdAt}</div>
                    </td>

                    <td className="py-3 px-4 font-bold text-slate-900 whitespace-nowrap">
                      {n.recipient}
                    </td>

                    <td className="py-3 px-4 max-w-md">
                      <p className="text-slate-700 leading-relaxed font-sans">{n.message}</p>
                    </td>

                    <td className="py-3 px-4 whitespace-nowrap">
                      {getStatusBadge(n.status)}
                    </td>

                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      {n.status === 'Failed' && (
                        <button
                          onClick={() => onRetryNotification(n.id)}
                          className="text-xs bg-red-50 hover:bg-red-100 text-red-700 font-bold px-2 py-1 rounded transition-all cursor-pointer flex items-center gap-1 ml-auto"
                        >
                          <RotateCw className="w-3 h-3" /> Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
