import { useState } from 'react';
import { PNM } from '../types';
import { api } from '../api';
import { adaptRecruits } from '../adapters';
import { ShowToast } from './useToast';
import { EnqueueOutbox } from './useOutbox';
import { SyncApi } from './useBackend';

interface Deps {
  syncApi: SyncApi;
  showToast: ShowToast;
  enqueueOutbox: EnqueueOutbox;
}

/** Rush pipeline: prospects, votes and bids. */
export function useRecruitment({ syncApi, showToast, enqueueOutbox }: Deps) {
  const [pnms, setPnms] = useState<PNM[]>([]);

  const refetchPnms = async () => setPnms(adaptRecruits(await api.getRecruits()));

  const handleAddPNM = (newPnm: Omit<PNM, 'id' | 'votesFor' | 'votesAgainst' | 'status'>) => {
    const p: PNM = {
      ...newPnm,
      id: 'pnm_' + Math.random().toString(36).substring(2, 9),
      votesFor: 0,
      votesAgainst: 0,
      status: 'Prospect'
    };
    setPnms(prev => [p, ...prev]);
    syncApi(
      () =>
        api.createRecruit({
          name: p.name,
          email: p.email || null,
          phone: p.phone || null,
          notes: p.notes || null
        }),
      refetchPnms
    );
    showToast(`Logged prospect "${p.name}" into rush database.`);
  };

  const handleVotePNM = (pnmId: string, type: 'up' | 'down') => {
    setPnms(prev => prev.map(p => {
      if (p.id === pnmId) {
        return {
          ...p,
          votesFor: type === 'up' ? p.votesFor + 1 : p.votesFor,
          votesAgainst: type === 'down' ? p.votesAgainst + 1 : p.votesAgainst
        };
      }
      return p;
    }));
  };

  const handleExtendBid = (pnmId: string) => {
    const pnm = pnms.find(p => p.id === pnmId);
    setPnms(prev => prev.map(p => p.id === pnmId ? { ...p, status: 'Bid Extended' } : p));
    syncApi(() => api.setRecruitStage(pnmId, 'bid_extended'), refetchPnms);
    if (pnm) {
      enqueueOutbox({
        type: 'BID_INVITATION',
        recipient: pnm.name,
        message: `[GreekOS Bid Alert] Congratulations ${pnm.name}! The Brotherhood has extended you an official Bid for Membership.`,
        channel: 'SMS'
      });
    }
    showToast(`Extended chapter membership bid to ${pnm?.name}.`);
  };

  return { pnms, setPnms, handleAddPNM, handleVotePNM, handleExtendBid };
}
