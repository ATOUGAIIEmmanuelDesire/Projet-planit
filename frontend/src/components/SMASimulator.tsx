import React, { useState, useEffect, useRef } from 'react';
import { Play, RotateCcw, AlertTriangle, Terminal, Filter } from 'lucide-react';
import { FIPAACLMessage, Performative } from '../types';

interface SMASimulatorProps {
  messages: FIPAACLMessage[];
  onRunSimulation: () => void;
  onInjectConflict: () => void;
  onClearLogs: () => void;
  isSimulating: boolean;
  roomsCount?: number;
  teachersCount?: number;
}

export const SMASimulator: React.FC<SMASimulatorProps> = ({
  messages,
  onRunSimulation,
  onInjectConflict,
  onClearLogs,
  isSimulating,
  roomsCount = 0,
  teachersCount = 0
}) => {
  const [filter, setFilter] = useState<string>('ALL');
  const terminalContainerRef = useRef<HTMLDivElement>(null);

  const filteredMessages = messages.filter((m) => {
    if (filter === 'ALL') return true;
    return m.performative === filter;
  });

  // Défilement automatique du terminal à chaque nouveau message FIPA-ACL reçu
  useEffect(() => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [filteredMessages.length]);

  return (
    <div className="space-y-6">
      {/* Contrôles du Simulateur SMA */}
      <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-ucac-navy">Moteur SMA — Protocole Contract Net (FIPA-ACL)</h2>
          <p className="text-sm text-slate-500">
            Négociation autonome asynchrone entre agents Coordinateur, Salles et Enseignants
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={onRunSimulation}
            disabled={isSimulating}
            className="flex items-center space-x-2 bg-ucac-orange hover:bg-ucac-orangeHover text-white px-4 py-2 rounded-lg font-medium shadow transition-all disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-white" />
            <span>{isSimulating ? 'Négociation en cours...' : 'Lancer Négociation SMA'}</span>
          </button>

          <button
            onClick={onInjectConflict}
            className="flex items-center space-x-2 bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg font-medium shadow transition-all"
          >
            <AlertTriangle className="w-4 h-4" />
            <span>Injecter Conflit</span>
          </button>

          <button
            onClick={onClearLogs}
            className="p-2 text-slate-500 hover:text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-all"
            title="Réinitialiser la console"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Cartes d'état des Agents Autonomes */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-ucac-navy text-sm">Agent Coordinateur</span>
            <span className="px-2 py-0.5 text-xs bg-emerald-100 text-emerald-800 rounded-full font-medium">Actif</span>
          </div>
          <p className="text-xs text-slate-500">Supervise le découpage des cours et l'arbitrage Pareto Green IT.</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-ucac-navy text-sm">Agents Salles ({roomsCount || 'Excel'})</span>
            <span className="px-2 py-0.5 text-xs bg-emerald-100 text-emerald-800 rounded-full font-medium">Écoute...</span>
          </div>
          <p className="text-xs text-slate-500">Calculent l'efficience énergétique HVAC et la capacité disponible.</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-ucac-navy text-sm">Agents Enseignants ({teachersCount || 'Excel'})</span>
            <span className="px-2 py-0.5 text-xs bg-emerald-100 text-emerald-800 rounded-full font-medium">Écoute...</span>
          </div>
          <p className="text-xs text-slate-500">Défendent les compétences disciplinaires et refusent les chevauchements.</p>
        </div>
      </div>

      {/* Terminal WebSocket des logs FIPA-ACL */}
      <div className="bg-slate-900 rounded-xl shadow-2xl border border-slate-800 overflow-hidden font-mono text-xs">
        {/* En-tête Terminal & Filtres */}
        <div className="bg-slate-950 px-4 py-3 flex flex-wrap items-center justify-between border-b border-slate-800 gap-2">
          <div className="flex items-center space-x-2 text-slate-300">
            <Terminal className="w-4 h-4 text-ucac-orange" />
            <span className="font-semibold">Terminal de Négociation Inter-Agents (WebSocket Live)</span>
            <span className="text-[11px] text-slate-500">({filteredMessages.length} trames)</span>
          </div>

          <div className="flex items-center space-x-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-slate-900 text-slate-300 text-xs rounded border border-slate-700 px-2 py-1 focus:outline-none"
            >
              <option value="ALL">Tous les Performatifs</option>
              <option value={Performative.CFP}>CFP (Call For Proposal)</option>
              <option value={Performative.BID}>BID (Offres)</option>
              <option value={Performative.ACCEPT_PROPOSAL}>ACCEPT (Contrats)</option>
              <option value={Performative.REJECT_PROPOSAL}>REJECT (Rejets)</option>
            </select>
          </div>
        </div>

        {/* Corps de la Console */}
        <div ref={terminalContainerRef} className="p-4 h-96 overflow-y-auto space-y-2 custom-scrollbar">
          {filteredMessages.length === 0 ? (
            <div className="text-slate-500 italic text-center py-12">
              Aucun message FIPA-ACL échangé pour le moment. Cliquez sur "Lancer Négociation SMA".
            </div>
          ) : (
            filteredMessages.map((msg, idx) => {
              let badgeColor = 'bg-blue-500/20 text-blue-400 border-blue-500/30';
              if (msg.performative === Performative.CFP) badgeColor = 'bg-amber-500/20 text-amber-400 border-amber-500/30';
              if (msg.performative === Performative.BID) badgeColor = 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
              if (msg.performative === Performative.ACCEPT_PROPOSAL) badgeColor = 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
              if (msg.performative === Performative.REJECT_PROPOSAL) badgeColor = 'bg-rose-500/20 text-rose-400 border-rose-500/30';

              const timeDisplay = msg.timestamp ? String(msg.timestamp).substring(11, 19) : '--:--:--';

              return (
                <div key={idx} className="flex flex-col sm:flex-row sm:items-center justify-between bg-slate-950/60 p-2.5 rounded border border-slate-800/80 hover:border-slate-700 transition-all gap-2">
                  <div className="flex items-center space-x-2 flex-wrap">
                    <span className="text-slate-500">{timeDisplay}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${badgeColor}`}>
                      {msg.performative}
                    </span>
                    <span className="text-slate-300 font-semibold">{msg.sender}</span>
                    <span className="text-slate-500">➔</span>
                    <span className="text-slate-300 font-semibold">{msg.receiver}</span>
                  </div>
                  <div className="text-slate-400 text-[11px] truncate max-w-md">
                    {JSON.stringify(msg.content)}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};