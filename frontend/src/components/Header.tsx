import React from 'react';
import { Cpu, Zap, ShieldCheck, Clock, MapPin, LogOut, UserCheck } from 'lucide-react';
import { UserProfile } from '../types';

interface HeaderProps {
  campus: string;
  setCampus: (c: string) => void;
  occupancyRate: number;
  unresolvedConflicts: number;
  lastExecTimeMs: number;
  totalSavedKwh: number;
  wsConnected: boolean;
  currentUser?: UserProfile | null;
  onLogout?: () => void;
}

const ROLE_LABELS: Record<string, string> = {
  administrateur: 'Administrateur',
  enseignant: 'Enseignant',
  responsable_pedagogique: 'Resp. Pédagogique',
  etudiant: 'Étudiant',
};

export const Header: React.FC<HeaderProps> = ({
  campus,
  setCampus,
  occupancyRate,
  unresolvedConflicts,
  lastExecTimeMs,
  totalSavedKwh,
  wsConnected,
  currentUser,
  onLogout,
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
              <h1 className="text-xl font-bold tracking-tight">
                PlanIt <span className="text-ucac-orange">Ucac-Icam</span>
              </h1>
              <span className="text-xs bg-ucac-navyDark border border-slate-600 px-2 py-0.5 rounded text-slate-300 font-mono">
                v1.0 SMA Engine
              </span>
            </div>
            <p className="text-xs text-slate-300 italic hidden sm:block">
              Former des hommes et des femmes techniquement compétents et humainement responsables
            </p>
          </div>
        </div>

        {/* Sélecteur de Campus, Statut WebSocket & Profil Connecté */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center space-x-2 bg-ucac-navyDark px-3 py-1.5 rounded-lg border border-slate-700 text-sm">
            <MapPin className="w-4 h-4 text-ucac-orange" />
            <select
              value={campus}
              onChange={(e) => setCampus(e.target.value)}
              className="bg-transparent text-white font-medium focus:outline-none cursor-pointer"
            >
              <option value="Douala - Yansoki" className="bg-ucac-navy text-white">
                Douala - Yansoki
              </option>
              <option value="Pointe-Noire" className="bg-ucac-navy text-white">
                Pointe-Noire
              </option>
            </select>
          </div>

          <div
            title="État de la connexion WebSocket avec le moteur multi-agents"
            className="flex items-center space-x-2 text-xs bg-slate-800/80 px-2.5 py-1.5 rounded-full border border-slate-700"
          >
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
              }`}
            />
            <span className="text-slate-300 font-mono">
              {wsConnected ? 'SMA Live WS' : 'WS Hors ligne'}
            </span>
          </div>

          {currentUser && (
            <div className="flex items-center gap-2.5 bg-ucac-navyDark pl-3 pr-2 py-1 rounded-lg border border-slate-700 text-xs">
              <UserCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <div className="text-left leading-tight">
                <div className="font-semibold text-white">
                  {currentUser.prenom} {currentUser.nom}
                </div>
                <div className="text-[11px] text-emerald-400">
                  {ROLE_LABELS[currentUser.role] || currentUser.role}
                </div>
              </div>

              {onLogout && (
                <button
                  type="button"
                  onClick={onLogout}
                  title="Se déconnecter"
                  className="ml-1 inline-flex items-center gap-1 rounded-md bg-rose-500/15 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 px-2 py-1 font-medium transition-colors cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Déconnexion</span>
                </button>
              )}
            </div>
          )}
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