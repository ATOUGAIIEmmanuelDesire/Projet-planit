import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Cpu,
  Zap,
  ShieldCheck,
  Clock,
  MapPin,
  LogOut,
  UserCheck,
  Users,
  Check,
  RefreshCw,
  X,
  Mail,
  Building2,
} from 'lucide-react';
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

interface PendingUser {
  id: string;
  nom: string;
  prenom: string;
  email: string;
  campus: string;
  role: string;
  is_active: boolean;
}

const ROLE_LABELS: Record<string, string> = {
  administrateur: 'Administrateur',
  enseignant: 'Enseignant',
  responsable_pedagogique: 'Resp. Pédagogique',
  etudiant: 'Étudiant',
};

const API_BASE_URL =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_URL ||
  `http://${window.location.hostname || 'localhost'}:8000/api/v1`;

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
  const isAdmin = currentUser?.role === 'administrateur';

  const [isValidationOpen, setIsValidationOpen] = useState(false);
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [isLoadingPending, setIsLoadingPending] = useState(false);
  const [validatingId, setValidatingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const dropdownRef = useRef<HTMLDivElement | null>(null);

  const getAuthHeaders = (): HeadersInit => {
    const token = localStorage.getItem('planit_token') || sessionStorage.getItem('planit_token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  };

  const fetchPendingUsers = useCallback(async () => {
    if (!isAdmin) return;
    setIsLoadingPending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/pending`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error('Impossible de récupérer les demandes en attente.');
      }
      const data: PendingUser[] = await response.json();
      setPendingUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Erreur chargement comptes en attente :', err);
    } finally {
      setIsLoadingPending(false);
    }
  }, [isAdmin]);

  // Charger les comptes en attente dès la connexion d'un administrateur
  useEffect(() => {
    if (isAdmin) {
      fetchPendingUsers();
    } else {
      setPendingUsers([]);
      setIsValidationOpen(false);
    }
  }, [isAdmin, fetchPendingUsers]);

  // Fermer le menu au clic à l'extérieur
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsValidationOpen(false);
      }
    };
    if (isValidationOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isValidationOpen]);

  const handleTogglePanel = () => {
    const nextState = !isValidationOpen;
    setIsValidationOpen(nextState);
    setFeedback(null);
    if (nextState) {
      fetchPendingUsers();
    }
  };

  const handleValidateUser = async (user: PendingUser) => {
    setValidatingId(user.id);
    setFeedback(null);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/validate/${user.id}`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Échec de la validation du compte.');
      }

      setPendingUsers((prev) => prev.filter((item) => item.id !== user.id));
      setFeedback({
        type: 'success',
        text: `Compte de ${user.prenom} ${user.nom} activé avec succès.`,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? `${err.message} (Vérifiez que le backend FastAPI tourne sur le port 8000)`
          : 'Erreur lors de la validation.';
      setFeedback({ type: 'error', text: message });
    } finally {
      setValidatingId(null);
    }
  };

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

        {/* Sélecteur de Campus, Statut WebSocket, Validation Admin & Profil Connecté */}
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

          {/* Bouton & Panneau de validation des comptes (Administrateur uniquement) */}
          {isAdmin && (
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={handleTogglePanel}
                title="Valider les demandes de création de compte"
                className="flex items-center gap-2 bg-ucac-navyDark hover:bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 hover:border-ucac-orange/60 text-xs font-medium text-white transition-colors cursor-pointer"
              >
                <Users className="w-4 h-4 text-ucac-orange" />
                <span className="hidden md:inline">Validations</span>
                <span
                  className={`px-1.5 py-0.5 rounded-full text-[11px] font-bold ${
                    pendingUsers.length > 0
                      ? 'bg-ucac-orange text-white animate-pulse'
                      : 'bg-slate-700 text-slate-300'
                  }`}
                >
                  {pendingUsers.length}
                </span>
              </button>

              {isValidationOpen && (
                <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-slate-900 text-white rounded-xl shadow-2xl border border-slate-700 z-50 overflow-hidden">
                  {/* En-tête du menu déroulant */}
                  <div className="px-4 py-3 bg-ucac-navyDark border-b border-slate-800 flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-white">Validation des comptes</h3>
                      <p className="text-[11px] text-slate-400">
                        {pendingUsers.length} demande(s) en attente d&apos;activation
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={fetchPendingUsers}
                        disabled={isLoadingPending}
                        title="Actualiser la liste"
                        className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <RefreshCw
                          className={`w-4 h-4 ${isLoadingPending ? 'animate-spin text-ucac-orange' : ''}`}
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => setIsValidationOpen(false)}
                        title="Fermer"
                        className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Message de confirmation ou d'erreur */}
                  {feedback && (
                    <div
                      className={`px-4 py-2 text-xs border-b ${
                        feedback.type === 'success'
                          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                      }`}
                    >
                      {feedback.text}
                    </div>
                  )}

                  {/* Liste des comptes en attente */}
                  <div className="max-h-80 overflow-y-auto divide-y divide-slate-800">
                    {isLoadingPending && pendingUsers.length === 0 ? (
                      <div className="p-6 text-center text-xs text-slate-400">
                        Chargement des demandes...
                      </div>
                    ) : pendingUsers.length === 0 ? (
                      <div className="p-6 text-center text-xs text-slate-400">
                        Aucun compte en attente de validation.
                      </div>
                    ) : (
                      pendingUsers.map((user) => (
                        <div
                          key={user.id}
                          className="p-3.5 hover:bg-slate-800/50 transition-colors flex items-start justify-between gap-3"
                        >
                          <div className="min-w-0 flex-1 space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-semibold text-white truncate">
                                {user.prenom} {user.nom}
                              </span>
                              <span className="text-[10px] px-2 py-0.5 rounded-full bg-ucac-orange/20 text-ucac-orange border border-ucac-orange/30 font-medium">
                                {ROLE_LABELS[user.role] || user.role}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 text-[11px] text-slate-300 truncate">
                              <Mail className="w-3 h-3 text-slate-400 shrink-0" />
                              <span className="truncate">{user.email}</span>
                            </div>
                            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                              <Building2 className="w-3 h-3 shrink-0" />
                              <span>{user.campus}</span>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleValidateUser(user)}
                            disabled={validatingId === user.id}
                            className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-800 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>{validatingId === user.id ? '...' : 'Valider'}</span>
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

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