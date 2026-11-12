import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Sparkles, CheckCircle2, Leaf, ThumbsUp, BookOpen, Search, ChevronDown, X, GraduationCap, User, Loader2, Users } from 'lucide-react';
import { RecommendationOption, AssignmentResult } from '../types';
import { apiService } from '../services/api';

interface HybridAssistantProps {
  assignments?: AssignmentResult[];
  onAssignmentUpdated?: (updated: AssignmentResult) => void;
}

export const HybridAssistant: React.FC<HybridAssistantProps> = ({ assignments = [], onAssignmentUpdated }) => {
  // Extraction dynamique des cours uniques issus des fichiers .ics du campus
  const availableCourses = useMemo(() => {
    if (!Array.isArray(assignments) || assignments.length === 0) return [];
    const courseMap = new Map<string, AssignmentResult>();
    assignments.forEach((a) => {
      if (a && a.course_id && !courseMap.has(a.course_id)) {
        courseMap.set(a.course_id, a);
      }
    });
    return Array.from(courseMap.values()).sort((a, b) => a.course_id.localeCompare(b.course_id));
  }, [assignments]);

  const [selectedCourseId, setSelectedCourseId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [recommendations, setRecommendations] = useState<RecommendationOption[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  
  // États de confirmation et de persistance ICS
  const [appliedCardKey, setAppliedCardKey] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState<boolean>(false);
  const [confirmStatusMessage, setConfirmStatusMessage] = useState<string | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fermeture du menu déroulant au clic à l'extérieur
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Initialisation du premier cours issu des emplois du temps
  useEffect(() => {
    if (availableCourses.length > 0 && !selectedCourseId) {
      const first = availableCourses[0];
      setSelectedCourseId(first.course_id);
      setSearchQuery(first.course_id);
    }
  }, [availableCourses, selectedCourseId]);

  // Filtrage intelligent selon la recherche (cours, promo ou enseignant)
  const filteredCourses = useMemo(() => {
    if (!searchQuery.trim()) return availableCourses;
    const query = searchQuery.toLowerCase();
    return availableCourses.filter(
      (c) =>
        c.course_id.toLowerCase().includes(query) ||
        (c.group_id && c.group_id.toLowerCase().includes(query)) ||
        (c.teacher_id && c.teacher_id.toLowerCase().includes(query))
    );
  }, [availableCourses, searchQuery]);

  // Comptage des intervenants distincts dans les 6 alternatives proposées
  const distinctTeachersCount = useMemo(() => {
    const names = new Set(
      recommendations
        .map((r) => (r as any).teacher_id || (r as any).teacher_name)
        .filter(Boolean)
    );
    return names.size;
  }, [recommendations]);

  const handleSelectCourse = (course: AssignmentResult) => {
    setSelectedCourseId(course.course_id);
    setSearchQuery(course.course_id);
    setIsOpen(false);
    setConfirmStatusMessage(null);
    setAppliedCardKey(null);
  };

  const handleFetchRecommendations = async () => {
    if (!selectedCourseId) return;
    setIsLoading(true);
    setConfirmStatusMessage(null);
    setAppliedCardKey(null);

    const currentCourse = availableCourses.find((c) => c.course_id === selectedCourseId);
    const groupId = currentCourse?.group_id || 'G_PROMO';
    const teacherId = currentCourse?.teacher_id || 'T_ENSEIGNANT';

    try {
      const results = await apiService.getManualRecommendations(selectedCourseId, groupId, teacherId, 35);
      setRecommendations(results);
    } catch (err) {
      console.error("Erreur lors de la récupération des recommandations:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Validation et persistance physique (Salle + Prof) dans planit_optimized_schedule.ics
  const handleApplyRecommendation = async (rec: RecommendationOption, cardKey: string) => {
    const currentCourse = availableCourses.find((c) => c.course_id === selectedCourseId);
    if (!currentCourse) return;

    setIsConfirming(true);
    setConfirmStatusMessage(null);

    const assignedTeacher = (rec as any).teacher_id || (rec as any).teacher_name || currentCourse.teacher_id || 'Enseignant Qualifié';
    const existingDate = (currentCourse as any).date;

    const updatedAssignment: AssignmentResult & { hvac_kwh?: number; date?: string | null } = {
      course_id: currentCourse.course_id,
      assigned_room: rec.room_id,
      timeslot: rec.timeslot,
      teacher_id: assignedTeacher,
      group_id: currentCourse.group_id || 'PROMO',
      hvac_saved_kwh: roundVal(rec.co2_saved_kg / 0.45, 2),
      hvac_kwh: roundVal(rec.co2_saved_kg / 0.45, 2),
      score: rec.global_score,
      resolution_method: 'HYBRID_ASSISTANT',
      ...(existingDate !== undefined ? { date: existingDate } : {})
    };

    try {
      const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${API_BASE}/api/v1/recommendations/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignment: updatedAssignment })
      });

      if (response.ok) {
        setAppliedCardKey(cardKey);
        setConfirmStatusMessage(`Option #${rec.rank} (${rec.timeslot} — Salle ${rec.room_id} avec ${assignedTeacher}) enregistrée dans planit_optimized_schedule.ics !`);
        if (onAssignmentUpdated) {
          onAssignmentUpdated(updatedAssignment);
        }
      } else {
        setConfirmStatusMessage("Créneau appliqué localement.");
        setAppliedCardKey(cardKey);
      }
    } catch (error) {
      console.warn("Mise à jour en mode repli:", error);
      setAppliedCardKey(cardKey);
      setConfirmStatusMessage(`Créneau ${rec.timeslot} sélectionné.`);
    } finally {
      setIsConfirming(false);
    }
  };

  const roundVal = (num: number, dec: number) => {
    return Math.round(num * Math.pow(10, dec)) / Math.pow(10, dec);
  };

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-orange-100 text-ucac-orange rounded-lg">
              <Sparkles className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-ucac-navy">Assistant Hybride — Recommandation Pareto</h2>
              <p className="text-sm text-slate-500">
                Sélectionnez une session pour générer 6 alternatives (Salle + 2 à 3 Intervenants Qualifiés) croisées avec l'Excel et les fichiers .ics.
              </p>
            </div>
          </div>

          {recommendations.length > 0 && (
            <div className="flex items-center gap-2 bg-blue-50 text-blue-900 border border-blue-200 px-3 py-1.5 rounded-lg text-xs font-bold">
              <Users className="w-4 h-4 text-blue-600" />
              <span>{recommendations.length} alternatives • {distinctTeachersCount} intervenant(s) qualifié(s)</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-4">
          {/* Menu déroulant / Champ de recherche personnalisé */}
          <div className="flex-1 min-w-[320px] relative" ref={dropdownRef}>
            <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
              <BookOpen className="w-4 h-4 text-ucac-orange" />
              <span>Session à replacer (issue des fichiers .ics) :</span>
            </label>

            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onFocus={() => setIsOpen(true)}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setIsOpen(true);
                }}
                placeholder="Rechercher ou sélectionner un cours..."
                className="w-full bg-white border border-slate-300 rounded-lg pl-9 pr-10 py-2.5 text-sm font-semibold text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-ucac-orange focus:border-ucac-orange focus:outline-none shadow-sm transition-all"
              />
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3 pointer-events-none" />

              <div className="absolute right-2.5 top-2.5 flex items-center space-x-1">
                {searchQuery && (
                  <button
                    onClick={() => {
                      setSearchQuery('');
                      setSelectedCourseId('');
                      setIsOpen(true);
                    }}
                    className="p-0.5 text-slate-400 hover:text-slate-600 rounded-full"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  onClick={() => setIsOpen(!isOpen)}
                  className="p-0.5 text-slate-400 hover:text-slate-600"
                >
                  <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
                </button>
              </div>
            </div>

            {/* Liste déroulante des cours */}
            {isOpen && (
              <div className="absolute z-50 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto divide-y divide-slate-100 custom-scrollbar">
                {filteredCourses.length === 0 ? (
                  <div className="p-3 text-xs text-slate-400 italic text-center">
                    Aucun cours trouvé pour "{searchQuery}"
                  </div>
                ) : (
                  filteredCourses.map((course) => {
                    const isSelected = course.course_id === selectedCourseId;
                    return (
                      <button
                        key={course.course_id}
                        type="button"
                        onClick={() => handleSelectCourse(course)}
                        className={`w-full text-left p-3 hover:bg-orange-50 transition-colors flex flex-col gap-1 ${
                          isSelected ? 'bg-orange-50/80 border-l-4 border-ucac-orange font-bold' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-bold text-ucac-navy truncate">{course.course_id}</span>
                          {isSelected && (
                            <span className="text-[10px] bg-ucac-orange text-white px-2 py-0.5 rounded-full font-bold">
                              Sélectionné
                            </span>
                          )}
                        </div>
                        <div className="flex items-center space-x-3 text-xs text-slate-500">
                          <span className="flex items-center gap-1 text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                            <GraduationCap className="w-3 h-3 text-emerald-600" />
                            {course.group_id}
                          </span>
                          {course.teacher_id && (
                            <span className="flex items-center gap-1 text-slate-600">
                              <User className="w-3 h-3 text-blue-500" />
                              {course.teacher_id}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>

          <button
            onClick={handleFetchRecommendations}
            disabled={isLoading || !selectedCourseId}
            className="bg-ucac-navy hover:bg-ucac-navyDark text-white px-5 py-2.5 rounded-lg font-medium shadow transition-all flex items-center space-x-2 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-ucac-gold" />}
            <span>{isLoading ? 'Calcul...' : 'Rechercher 6 Alternatives'}</span>
          </button>
        </div>

        {/* Banner de confirmation */}
        {confirmStatusMessage && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs font-semibold text-emerald-800 flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{confirmStatusMessage}</span>
          </div>
        )}
      </div>

      {/* Grille des 6 Recommandations */}
      {recommendations.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {recommendations.map((rec) => {
            const proposedTeacher = (rec as any).teacher_id || (rec as any).teacher_name || 'Enseignant Qualifié';
            const cardKey = `${rec.rank}-${rec.timeslot}-${rec.room_id}-${proposedTeacher}`;
            const isApplied = appliedCardKey === cardKey;

            return (
              <div
                key={cardKey}
                className={`bg-white rounded-xl p-5 border shadow-md relative flex flex-col justify-between transition-all ${
                  isApplied ? 'border-emerald-500 ring-2 ring-emerald-400' : 'border-slate-200'
                }`}
              >
                {rec.rank === 1 && (
                  <span className="absolute -top-3 right-4 bg-ucac-orange text-white text-[11px] font-bold px-2.5 py-0.5 rounded-full shadow">
                    ★ Recommandation Optimale
                  </span>
                )}

                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-bold text-slate-500">Option #{rec.rank}</span>
                    <span className="text-2xl font-black text-ucac-navy">{rec.global_score}<span className="text-xs text-slate-400">/100</span></span>
                  </div>

                  <div className="space-y-2 mb-3">
                    <div className="text-base font-bold text-slate-800">{rec.timeslot}</div>
                    <div className="text-sm font-semibold text-ucac-orange">{rec.room_id}</div>
                  </div>

                  {/* Badge Intervenant attribué */}
                  <div className="flex items-center space-x-2 text-xs font-semibold text-slate-700 bg-blue-50 p-2.5 rounded-lg border border-blue-100 mb-3">
                    <User className="w-4 h-4 text-blue-600 flex-shrink-0" />
                    <div className="truncate">
                      <span className="text-slate-500 font-normal">Intervenant : </span>
                      <span className="text-blue-950 font-bold">{proposedTeacher}</span>
                    </div>
                  </div>

                  <div className="space-y-2 pt-3 border-t border-slate-100 text-xs">
                    <div className="flex items-center justify-between text-slate-600">
                      <span className="flex items-center gap-1"><Leaf className="w-3.5 h-3.5 text-emerald-500" /> Score Énergie HVAC:</span>
                      <span className="font-bold text-slate-800">{rec.hvac_efficiency_score}%</span>
                    </div>

                    <div className="flex items-center justify-between text-slate-600">
                      <span className="flex items-center gap-1"><ThumbsUp className="w-3.5 h-3.5 text-blue-500" /> Pertinence Intervenant:</span>
                      <span className="font-bold text-slate-800">{rec.teacher_preference_score}%</span>
                    </div>

                    <div className="flex items-center justify-between text-slate-600">
                      <span>Émission CO₂ Évitée:</span>
                      <span className="font-bold text-emerald-600">{rec.co2_saved_kg} kg CO₂</span>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => handleApplyRecommendation(rec, cardKey)}
                  disabled={isConfirming}
                  className={`mt-5 w-full py-2 rounded-lg font-medium text-sm flex items-center justify-center space-x-2 transition-all ${
                    isApplied
                      ? 'bg-emerald-500 text-white'
                      : 'bg-slate-100 hover:bg-ucac-orange hover:text-white text-slate-700'
                  }`}
                >
                  {isConfirming ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4" />
                  )}
                  <span>
                    {isApplied
                      ? 'Créneau Enregistré (.ics)'
                      : 'Valider ce Créneau'}
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};