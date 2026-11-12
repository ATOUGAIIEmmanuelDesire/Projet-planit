import React from 'react';
import { Cpu, Zap, ShieldCheck, Clock, MapPin } from 'lucide-react';

interface HeaderProps {
  campus: string;
  setCampus: (c: string) => void;
  occupancyRate: number;
  unresolvedConflicts: number;
  lastExecTimeMs: number;
  totalSavedKwh: number;
  wsConnected: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  campus,
  setCampus,
  occupancyRate,
  unresolvedConflicts,
  lastExecTimeMs,
  totalSavedKwh,
  wsConnected,
}) => {
  return (
    <header className="bg-ucac-navy text-white shadow-xl border-b border-slate-700">
      {/* Top Banner Branding */}
      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          {/* Logo Ucac-Icam SVG Dynamic */}
          <div className="w-10 h-10 bg-ucac-orange rounded-lg flex items-center justify-center font-bold text-xl shadow-md text-white">
            U
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight">PlanIt <span className="text-ucac-orange">Ucac-Icam</span></h1>
              <span className="text-xs bg-ucac-navyDark border border-slate-600 px-2 py-0.5 rounded text-slate-300 font-mono">
                v1.0 SMA Engine
              </span>
            </div>
            <p className="text-xs text-slate-300 italic hidden sm:block">
              Former des hommes et des femmes techniquement compétents et humainement responsables
            </p>
          </div>
        </div>

        {/* Sélecteur de Campus & Statut WebSocket */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 bg-ucac-navyDark px-3 py-1.5 rounded-lg border border-slate-700 text-sm">
            <MapPin className="w-4 h-4 text-ucac-orange" />
            <select
              value={campus}
              onChange={(e) => setCampus(e.target.value)}
              className="bg-transparent text-white font-medium focus:outline-none cursor-pointer"
            >
              <option value="Douala - Yansoki" className="bg-ucac-navy text-white">Douala - Yansoki</option>
              <option value="Pointe-Noire" className="bg-ucac-navy text-white">Pointe-Noire</option>
            </select>
          </div>

          <div className="flex items-center space-x-2 text-xs bg-slate-800/80 px-2.5 py-1 rounded-full border border-slate-700">
            <span className={`w-2.5 h-2.5 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
            <span className="text-slate-300 font-mono">{wsConnected ? 'SMA Live WS' : 'Déconnecté'}</span>
          </div>
        </div>
      </div>

      {/* Bandeau KPI Live de Performance & Green IT */}
      <div className="bg-ucac-navyDark border-t border-slate-800 py-2.5">
        <div className="max-w-7xl mx-auto px-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
          <div className="flex items-center justify-center space-x-2 border-r border-slate-800">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <div className="text-left">
              <div className="text-xs text-slate-400">Taux d'Occupation</div>
              <div className="text-base font-bold text-emerald-400">{occupancyRate}%</div>
            </div>
          </div>

          <div className="flex items-center justify-center space-x-2 border-r border-slate-800">
            <Cpu className="w-5 h-5 text-ucac-orange" />
            <div className="text-left">
              <div className="text-xs text-slate-400">Conflits Non Résolus</div>
              <div className="text-base font-bold text-white">{unresolvedConflicts}</div>
            </div>
          </div>

          <div className="flex items-center justify-center space-x-2 border-r border-slate-800">
            <Clock className="w-5 h-5 text-ucac-gold" />
            <div className="text-left">
              <div className="text-xs text-slate-400">Vitesse Négociation</div>
              <div className="text-base font-bold text-ucac-gold">{lastExecTimeMs} ms</div>
            </div>
          </div>

          <div className="flex items-center justify-center space-x-2">
            <Zap className="w-5 h-5 text-emerald-400" />
            <div className="text-left">
              <div className="text-xs text-slate-400">Énergie Économisée</div>
              <div className="text-base font-bold text-emerald-400">{totalSavedKwh} kWh</div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};