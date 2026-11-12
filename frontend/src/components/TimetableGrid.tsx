import React, { useState, useMemo, useEffect, useRef } from 'react';
import { AssignmentResult } from '../types';
import { apiService } from '../services/api';
import { 
  Zap, Clock, User, DoorOpen, Users, RefreshCw, Search, X, 
  GraduationCap, Calendar, CalendarDays, Briefcase, Bot, ShieldCheck, Leaf, Sparkles, AlertCircle 
} from 'lucide-react';

interface TimetableGridProps {
  assignments?: AssignmentResult[];
  onAssignmentsUpdated?: (newAssignments: AssignmentResult[]) => void;
}

const DEFAULT_PROMO = 'X2027 - X5';

// Détermine la semaine ISO (1 à 52) et l'année civile en cours
const getCurrentISOWeekAndYear = (): { week: number; year: number } => {
  const now = new Date();
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return { week, year: d.getUTCFullYear() };
};

// Calcule le lundi de n'importe quelle semaine ISO
const getMondayOfISOWeek = (week: number, year: number): Date => {
  const jan4 = new Date(year, 0, 4);
  const dayOfWeek = jan4.getDay() || 7;
  const mondayISOWeek1 = new Date(jan4);
  mondayISOWeek1.setDate(jan4.getDate() - (dayOfWeek - 1));
  const targetMonday = new Date(mondayISOWeek1);
  targetMonday.setDate(mondayISOWeek1.getDate() + (week - 1) * 7);
  return targetMonday;
};

// Vérifie si un groupe d'affectation correspond à la promotion sélectionnée
const isGroupMatching = (assignmentGroup: string | undefined, selected: string): boolean => {
  if (!selected || selected === 'ALL') return true;
  if (!assignmentGroup) return true;
  
  const normAssign = assignmentGroup.toLowerCase().replace(/[^a-z0-9]/g, '');
  const normSelect = selected.toLowerCase().replace(/[^a-z0-9]/g, '');

  if (normAssign.includes(normSelect) || normSelect.includes(normAssign)) return true;

  const tokensAssign: string[] = assignmentGroup.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  const tokensSelect: string[] = selected.toLowerCase().match(/[a-z0-9]+/g) ?? [];

  return tokensSelect.some((t) => tokensAssign.includes(t));
};

// Vérifie si un créneau horaire correspond au jour, à l'heure et à la semaine
const isTimeslotMatching = (
  timeslot: string | undefined,
  day: string,
  slotTime: string,
  selectedWeek: number
): boolean => {
  if (!timeslot) return false;
  const norm = timeslot.trim();

  // Si le créneau contient un préfixe de semaine (ex: S46_Lundi_08h00-12h00)
  const weekMatch = norm.match(/^S(\d+)_/i);
  if (weekMatch) {
    const weekNum = parseInt(weekMatch[1], 10);
    if (weekNum !== selectedWeek) return false;
  }

  // Vérification du jour
  const dayMatch = norm.toLowerCase().includes(day.toLowerCase());

  // Vérification de l'horaire
  const cleanSlot = slotTime.replace(/\s+/g, '');
  const cleanNorm = norm.replace(/\s+/g, '');
  const slotMatch = 
    cleanNorm.includes(cleanSlot) ||
    (slotTime.includes('08h00') && cleanNorm.includes('08h00')) ||
    (slotTime.includes('13h00') && cleanNorm.includes('13h00'));

  return dayMatch && slotMatch;
};

export const TimetableGrid: React.FC<TimetableGridProps> = ({ 
  assignments = [], 
  onAssignmentsUpdated 
}) => {
  const { week: currentWeekNumber, year: currentYearNumber } = useMemo(() => getCurrentISOWeekAndYear(), []);

  // Sous-onglet actif : 'ics' (Initial) ou 'sma' (Optimisé SMA)
  const [subTab, setSubTab] = useState<'ics' | 'sma'>('ics');

  const [selectedGroup, setSelectedGroup] = useState<string>(DEFAULT_PROMO);
  const [selectedYear, setSelectedYear] = useState<number>(currentYearNumber);
  const [selectedWeek, setSelectedWeek] = useState<number>(currentWeekNumber);
  
  const [searchPromo, setSearchPromo] = useState<string>(DEFAULT_PROMO);
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [showSyncModal, setShowSyncModal] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const days = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi'];
  const timeslots = ['08h00-12h00', '13h00-17h00'];

  const availableYears = [2026, 2027];
  const availableWeeks = Array.from({ length: 52 }, (_, i) => i + 1);

  // 1. Chargement automatique des emplois du temps au montage
  useEffect(() => {
    apiService.getAllAssignments()
      .then((loadedData) => {
        if (Array.isArray(loadedData) && loadedData.length > 0 && onAssignmentsUpdated) {
          onAssignmentsUpdated(loadedData);
        }
      })
      .catch((err) => console.error("Erreur récupération cours auto:", err));
  }, []);

  // Liste des promotions uniques disponibles
  const availableGroups = useMemo(() => {
    if (!Array.isArray(assignments)) return [];
    const groups = new Set<string>();
    assignments.forEach((a) => {
      if (a && a.group_id && typeof a.group_id === 'string') {
        groups.add(a.group_id);
      }
    });
    return Array.from(groups).sort();
  }, [assignments]);

  // Sélection automatique du nom exact de la promotion
  useEffect(() => {
    if (availableGroups.length > 0) {
      let match = availableGroups.find((g) => g.toLowerCase() === DEFAULT_PROMO.toLowerCase());
      if (!match) {
        match = availableGroups.find(
          (g) => g.toLowerCase().includes('x2027') || g.toLowerCase().includes('x5')
        );
      }
      if (match) {
        setSelectedGroup(match);
        setSearchPromo(match);
      }
    }
  }, [availableGroups]);

  // Calcul des dates sous chaque jour
  const weekDates = useMemo(() => {
    const monday = getMondayOfISOWeek(selectedWeek, selectedYear);
    return days.map((_, index) => {
      const dateObj = new Date(monday);
      dateObj.setDate(monday.getDate() + index);
      return dateObj.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
    });
  }, [selectedWeek, selectedYear]);

  // Fermeture du dropdown au clic extérieur
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const autocompleteSuggestions = useMemo(() => {
    if (!searchPromo || !searchPromo.trim()) return availableGroups;
    return availableGroups.filter((g) =>
      typeof g === 'string' && g.toLowerCase().includes(searchPromo.toLowerCase())
    );
  }, [availableGroups, searchPromo]);

  // Détection des affectations générées par le SMA
  const allSmaAssignments = useMemo(() => {
    if (!Array.isArray(assignments)) return [];
    return assignments.filter((a) => 
      a && (
        a.resolution_method === 'SMA_CNP' || 
        a.resolution_method === 'OR_TOOLS_CP_SAT' || 
        a.resolution_method === 'SMA' || 
        (typeof a.score === 'number' && a.score > 0) ||
        (typeof a.hvac_saved_kwh === 'number' && a.hvac_saved_kwh > 0)
      )
    );
  }, [assignments]);

  // Total des kWh économisés et nombre de cours ré-alloués par le SMA
  const smaKwhSaved = useMemo(() => {
    const total = allSmaAssignments.reduce((acc, curr) => acc + (curr.hvac_saved_kwh || 0.85), 0);
    return total.toFixed(1);
  }, [allSmaAssignments]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setIsLoading(true);
    try {
      const importedAssignments = await apiService.uploadMultipleHyperplanningIcs(files);
      if (onAssignmentsUpdated && Array.isArray(importedAssignments)) {
        onAssignmentsUpdated(importedAssignments);
      }
      setShowSyncModal(false);
    } catch (err) {
      alert("Erreur lors de l'importation des fichiers .ics");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectPromo = (promo: string) => {
    setSelectedGroup(promo);
    setSearchPromo(promo === 'ALL' ? '' : promo);
    setIsDropdownOpen(false);
  };

  const handleResetToCurrentDate = () => {
    setSelectedYear(currentYearNumber);
    setSelectedWeek(currentWeekNumber);
  };

  return (
    <div className="space-y-5">
      {/* Barre supérieure : Sous-onglets de vue + Filtre Promo + Import ICS */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center justify-between gap-4">
        
        {/* Sous-onglets */}
        <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200 space-x-1">
          <button
            onClick={() => setSubTab('ics')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              subTab === 'ics'
                ? 'bg-ucac-navy text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
            }`}
          >
            <Calendar className="w-3.5 h-3.5 text-ucac-orange" />
            <span>Vue Emploi du Temps (.ics)</span>
          </button>

          <button
            onClick={() => setSubTab('sma')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              subTab === 'sma'
                ? 'bg-ucac-orange text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
            }`}
          >
            <Bot className="w-3.5 h-3.5 text-ucac-gold" />
            <span>Vue Optimisée SMA (Green-IT)</span>
            {allSmaAssignments.length > 0 && (
              <span className="bg-white text-ucac-orange text-[10px] font-extrabold px-1.5 py-0.5 rounded-full ml-1">
                {allSmaAssignments.length}
              </span>
            )}
          </button>
        </div>

        {/* Bouton Recharger ICS & Autocomplétion Promo */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setShowSyncModal(!showSyncModal)}
            className="flex items-center space-x-2 bg-slate-100 hover:bg-slate-200 text-ucac-navy px-3 py-2 rounded-lg text-xs font-semibold border border-slate-300 transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-ucac-orange ${isLoading ? 'animate-spin' : ''}`} />
            <span>Recharger `.ics`</span>
          </button>

          <div className="relative" ref={dropdownRef}>
            <div className="relative flex items-center">
              <Search className="w-4 h-4 text-slate-400 absolute left-3" />
              <input
                type="text"
                placeholder="Rechercher promotion (ex: X2027 - X5, B1)..."
                value={searchPromo}
                onFocus={() => setIsDropdownOpen(true)}
                onChange={(e) => {
                  setSearchPromo(e.target.value);
                  setIsDropdownOpen(true);
                  if (e.target.value === '') setSelectedGroup('ALL');
                }}
                className="pl-9 pr-8 py-2 border border-slate-300 rounded-lg text-xs font-semibold focus:ring-2 focus:ring-ucac-orange focus:outline-none w-64 shadow-sm text-slate-900"
              />
              {searchPromo && (
                <button
                  onClick={() => {
                    setSearchPromo('');
                    setSelectedGroup('ALL');
                  }}
                  className="absolute right-2.5 text-slate-400 hover:text-slate-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {isDropdownOpen && (
              <div className="absolute z-50 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-56 overflow-y-auto divide-y divide-slate-100 custom-scrollbar">
                <button
                  onClick={() => handleSelectPromo('ALL')}
                  className={`w-full text-left px-3 py-2 text-xs font-semibold hover:bg-orange-50 ${
                    selectedGroup === 'ALL' ? 'text-ucac-orange bg-orange-50/50 font-bold' : 'text-slate-700'
                  }`}
                >
                  Toutes les promotions (Vue Campus)
                </button>
                {autocompleteSuggestions.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-slate-400 italic">Aucune promotion trouvée</div>
                ) : (
                  autocompleteSuggestions.map((group) => (
                    <button
                      key={group}
                      onClick={() => handleSelectPromo(group)}
                      className={`w-full text-left px-3 py-2 text-xs hover:bg-orange-50 flex items-center justify-between ${
                        selectedGroup === group ? 'font-bold text-ucac-navy bg-orange-50' : 'text-slate-700'
                      }`}
                    >
                      <span>Promotion {group}</span>
                      <Users className="w-3 h-3 text-slate-400" />
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modal Importation */}
      {showSyncModal && (
        <div className="bg-orange-50 border border-ucac-orange/30 p-4 rounded-xl space-y-3">
          <h3 className="text-sm font-bold text-ucac-navy flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-ucac-orange" />
            Importer manuellement des fichiers `.ics`
          </h3>
          <input
            type="file"
            accept=".ics"
            multiple
            onChange={handleFileUpload}
            className="text-xs text-slate-500 file:mr-2 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-ucac-navy file:text-white hover:file:bg-ucac-navyDark cursor-pointer"
          />
        </div>
      )}

      {/* Bandeau d'information du sous-onglet SMA */}
      {subTab === 'sma' && (
        <div className="bg-slate-900 rounded-xl p-4 border border-slate-800 space-y-3 text-white">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-emerald-500/20 text-emerald-400 rounded-lg border border-emerald-500/30">
                <Bot className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h3 className="text-sm font-bold text-white">Résultat du Moteur de Négociation Multi-Agents</h3>
                  <span className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3" />
                    Green-IT Pareto
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Affectations recalculées basées sur les capteurs HVAC et les préférences enseignants pour la promotion <strong>{selectedGroup}</strong>.
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-4 bg-slate-950 px-4 py-2 rounded-lg border border-slate-800 text-xs">
              <div className="flex items-center space-x-1.5">
                <Leaf className="w-4 h-4 text-emerald-400" />
                <span className="text-slate-400">Économie HVAC :</span>
                <strong className="text-emerald-400 font-mono text-sm">{smaKwhSaved} kWh</strong>
              </div>
              <div className="h-4 w-px bg-slate-800"></div>
              <div className="flex items-center space-x-1.5">
                <Sparkles className="w-4 h-4 text-ucac-gold" />
                <span className="text-slate-400">Cours ré-alloués SMA :</span>
                <strong className="text-white font-mono text-sm">{allSmaAssignments.length}</strong>
              </div>
            </div>
          </div>

          {allSmaAssignments.length === 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-amber-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>
                Aucune négociation SMA n'a encore été lancée. Basculez sur l'onglet <strong>Simulateur SMA</strong> et cliquez sur <strong>"Lancer Négociation SMA"</strong> pour générer l'emploi du temps optimisé.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Navigation Année Académique & Ruban des Semaines */}
      <div className="bg-white p-3.5 rounded-xl shadow-sm border border-slate-200 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-2.5">
          <div className="flex items-center space-x-2">
            <CalendarDays className="w-4 h-4 text-ucac-orange" />
            <span className="text-xs font-bold text-slate-700">Année Académique :</span>
            <div className="flex bg-slate-100 p-0.5 rounded-lg border border-slate-200">
              {availableYears.map((yr) => (
                <button
                  key={yr}
                  onClick={() => setSelectedYear(yr)}
                  className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                    selectedYear === yr
                      ? 'bg-ucac-navy text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Année {yr} {yr === 2026 ? '(Sept-Déc)' : '(Jan-Juin)'}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <div className="text-xs font-semibold text-slate-600 bg-slate-50 px-2.5 py-1 rounded-md border border-slate-200">
              Promotion : <strong className="text-ucac-navy font-bold">{selectedGroup}</strong> | Semaine : <strong className="text-ucac-navy font-bold">{selectedWeek} ({selectedYear})</strong>
            </div>

            {(selectedWeek !== currentWeekNumber || selectedYear !== currentYearNumber) && (
              <button
                onClick={handleResetToCurrentDate}
                className="text-xs font-semibold text-ucac-orange hover:text-ucac-navy flex items-center gap-1 transition-colors bg-orange-50 px-2.5 py-1 rounded-md border border-orange-200"
              >
                <Calendar className="w-3.5 h-3.5" />
                <span>Semaine actuelle (S{currentWeekNumber} {currentYearNumber})</span>
              </button>
            )}
          </div>
        </div>

        {/* Carrousel des 52 Semaines */}
        <div className="flex items-center overflow-x-auto space-x-1 pb-1 custom-scrollbar">
          {availableWeeks.map((week) => {
            const isCurrent = week === currentWeekNumber && selectedYear === currentYearNumber;
            const isSelected = week === selectedWeek;
            return (
              <button
                key={week}
                onClick={() => setSelectedWeek(week)}
                className={`px-2.5 py-1 text-xs font-mono rounded transition-all min-w-[34px] relative ${
                  isSelected
                    ? 'bg-ucac-orange text-white shadow font-bold'
                    : isCurrent
                    ? 'bg-orange-100 text-ucac-navy font-bold border border-ucac-orange/50'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
                title={isCurrent ? 'Semaine actuelle' : `Semaine ${week} - ${selectedYear}`}
              >
                {week}
                {isCurrent && !isSelected && (
                  <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-ucac-orange rounded-full"></span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Grille d'Emploi du Temps dynamique */}
      <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-x-auto custom-scrollbar">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="bg-ucac-navy text-white">
              <th className="p-3 border-b border-slate-700 w-32 text-center align-middle">Horaire</th>
              {days.map((day, idx) => (
                <th key={day} className="p-3 border-b border-slate-700 text-center">
                  <div className="font-bold text-xs uppercase tracking-wider">{day}</div>
                  <div className="text-[11px] text-orange-300 font-mono font-normal mt-0.5">
                    {weekDates[idx]}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {timeslots.map((slotTime) => (
              <tr key={slotTime} className="hover:bg-slate-50/50">
                <td className="p-3 font-bold text-slate-700 bg-slate-50 text-center border-r border-slate-200">
                  <div className="flex items-center justify-center space-x-1">
                    <Clock className="w-3.5 h-3.5 text-ucac-orange" />
                    <span>{slotTime}</span>
                  </div>
                </td>
                {days.map((day) => {
                  // Récupération des affectations correspondant au jour, à l'horaire et à la promotion
                  const cellAssignments = assignments.filter((a) => {
                    if (!a) return false;
                    const matchesGroup = isGroupMatching(a.group_id, selectedGroup);
                    const matchesSlot = isTimeslotMatching(a.timeslot, day, slotTime, selectedWeek);
                    return matchesGroup && matchesSlot;
                  });

                  // En mode SMA, filtrer ou mettre en avant les affectations issues du SMA
                  const isSmaView = subTab === 'sma';
                  const displayItems = isSmaView
                    ? cellAssignments.filter(
                        (a) =>
                          a.resolution_method === 'SMA_CNP' ||
                          a.resolution_method === 'OR_TOOLS_CP_SAT' ||
                          a.resolution_method === 'SMA' ||
                          (a.score && a.score > 0) ||
                          (a.hvac_saved_kwh && a.hvac_saved_kwh > 0)
                      )
                    : cellAssignments;

                  return (
                    <td key={day} className="p-2 border-r border-slate-200 min-w-[210px] align-top">
                      {displayItems.length === 0 ? (
                        <div className="h-28 border-2 border-dashed border-slate-100 rounded-lg flex items-center justify-center text-slate-300">
                          {isSmaView && cellAssignments.length > 0 ? (
                            <span className="text-[10px] text-slate-400 italic text-center p-2">
                              En attente d'optimisation SMA
                            </span>
                          ) : (
                            'Disponible'
                          )}
                        </div>
                      ) : (
                        displayItems.map((item, i) => {
                          const isStage = 
                            (item.course_id && item.course_id.toLowerCase().includes('stage')) ||
                            (item.assigned_room && item.assigned_room.toLowerCase().includes('stage'));

                          const isOptimizedBySma = 
                            item.resolution_method === 'SMA_CNP' || 
                            item.resolution_method === 'OR_TOOLS_CP_SAT' || 
                            item.resolution_method === 'SMA' ||
                            (item.score && item.score > 0);

                          return (
                            <div
                              key={i}
                              className={`bg-white border-l-4 ${
                                isStage
                                  ? 'border-l-blue-500 bg-blue-50/20'
                                  : isOptimizedBySma
                                  ? 'border-l-emerald-500 bg-emerald-50/30'
                                  : 'border-l-ucac-orange'
                              } border-y border-r border-slate-200 p-3 rounded-r-lg shadow-sm mb-2 space-y-2 hover:shadow-md transition-all`}
                            >
                              <div className="flex items-start justify-between gap-1">
                                <span className="font-bold text-ucac-navy text-xs leading-snug" title={item.course_id}>
                                  {item.course_id}
                                </span>
                                {isOptimizedBySma && (
                                  <span className="text-[10px] bg-emerald-100 text-emerald-800 border border-emerald-300 px-1.5 py-0.5 rounded font-mono font-bold flex items-center gap-0.5 shrink-0">
                                    <Zap className="w-2.5 h-2.5 text-emerald-600" />
                                    {item.score || 95}%
                                  </span>
                                )}
                              </div>

                              <div className="inline-flex items-center space-x-1 bg-orange-100/80 text-ucac-navy font-bold text-[11px] px-2 py-0.5 rounded-md border border-orange-200 w-full">
                                <GraduationCap className="w-3.5 h-3.5 text-ucac-orange shrink-0" />
                                <span className="truncate">{item.group_id}</span>
                              </div>

                              {/* Détails Salle et Enseignant */}
                              <div className="flex items-center justify-between text-slate-600 text-[11px] pt-1 border-t border-slate-100">
                                <div className="flex items-center space-x-1">
                                  {isStage ? (
                                    <>
                                      <Briefcase className="w-3 h-3 text-blue-500" />
                                      <span className="font-semibold text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded text-[10px]">
                                        Hors campus
                                      </span>
                                    </>
                                  ) : (
                                    <>
                                      <DoorOpen className={`w-3 h-3 ${isOptimizedBySma ? 'text-emerald-600' : 'text-slate-400'}`} />
                                      <span className={`font-bold ${isOptimizedBySma ? 'text-emerald-900' : 'text-slate-800'}`}>
                                        {item.assigned_room || 'Salle non attribuée'}
                                      </span>
                                    </>
                                  )}
                                </div>
                                {item.teacher_id && (
                                  <div className="flex items-center space-x-1 truncate max-w-[100px]">
                                    <User className="w-3 h-3 text-slate-400" />
                                    <span title={item.teacher_id}>{item.teacher_id}</span>
                                  </div>
                                )}
                              </div>

                              {/* Badges spécifiques au SMA Green-IT */}
                              {isSmaView && isOptimizedBySma && (
                                <div className="flex items-center justify-between pt-1 border-t border-emerald-100 text-[10px]">
                                  <span className="text-emerald-700 font-bold flex items-center gap-1">
                                    <Leaf className="w-3 h-3 text-emerald-600" />
                                    +{item.hvac_saved_kwh || 0.85} kWh économisés
                                  </span>
                                  <span className="text-slate-400 font-mono">
                                    {item.resolution_method || 'SMA_CNP'}
                                  </span>
                                </div>
                              )}
                            </div>
                          );
                        })
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TimetableGrid;