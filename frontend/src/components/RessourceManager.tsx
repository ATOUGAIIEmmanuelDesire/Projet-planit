import React, { useState, useEffect, useMemo } from 'react';
import { 
  DoorOpen, User, GraduationCap, Search, Building2, 
  Plug, FileSpreadsheet, RefreshCw, Plus, Pencil, Trash2, X, Save, CheckCircle2, Loader2
} from 'lucide-react';

export interface ExcelSalle {
  "Bâtiment": string;
  "Étage": string;
  "Code / Salle": string;
  "Type de Salle": string;
  "Capacité": number;
  "Prises Elec.": number;
  "Affichage (TV / Projecteur)": string;
  "Climatisation": string;
  "Capteur HVAC Smart": string;
  "Équipements complémentaires": string;
}

export interface ExcelEnseignant {
  "Nom et Prénom": string;
  "Domaine ": string;
  "Domaine"?: string;
  "Expertises / Technologies": string;
  preferred_timeslots?: string[];
}

export interface ExcelPromotion {
  "Promotion & Intitulé": string;
  "Niveau / Cycle": string;
  "Code promotion": string;
  "Effectif Etudiants": number;
}

interface ResourceManagerProps {
  rooms?: any[];
  teachers?: any[];
  groups?: any[];
  onResourcesUpdated?: () => void;
}

const EMPTY_SALLE: ExcelSalle = {
  "Bâtiment": "Bâtiment A",
  "Étage": "RDC",
  "Code / Salle": "",
  "Type de Salle": "Salle de cours",
  "Capacité": 40,
  "Prises Elec.": 15,
  "Affichage (TV / Projecteur)": "Projecteur",
  "Climatisation": "Oui",
  "Capteur HVAC Smart": "Oui",
  "Équipements complémentaires": ""
};

const EMPTY_ENSEIGNANT: ExcelEnseignant = {
  "Nom et Prénom": "",
  "Domaine ": "",
  "Expertises / Technologies": ""
};

const EMPTY_PROMOTION: ExcelPromotion = {
  "Promotion & Intitulé": "",
  "Niveau / Cycle": "Ingénieur",
  "Code promotion": "",
  "Effectif Etudiants": 35
};

export const ResourceManager: React.FC<ResourceManagerProps> = ({ onResourcesUpdated }) => {
  const [activeTab, setActiveTab] = useState<'salles' | 'enseignants' | 'promotions'>('salles');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [sallesData, setSallesData] = useState<ExcelSalle[]>([]);
  const [enseignantsData, setEnseignantsData] = useState<ExcelEnseignant[]>([]);
  const [promotionsData, setPromotionsData] = useState<ExcelPromotion[]>([]);

  // États Modale CRUD
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [formSalle, setFormSalle] = useState<ExcelSalle>(EMPTY_SALLE);
  const [formEnseignant, setFormEnseignant] = useState<ExcelEnseignant>(EMPTY_ENSEIGNANT);
  const [formPromotion, setFormPromotion] = useState<ExcelPromotion>(EMPTY_PROMOTION);

  const timeslotsList = [
    ['Lundi_08h00-12h00', 'Mardi_13h00-17h00'],
    ['Mercredi_08h00-12h00', 'Jeudi_13h00-17h00'],
    ['Lundi_13h00-17h00', 'Vendredi_08h00-12h00'],
    ['Mardi_08h00-12h00', 'Jeudi_08h00-12h00'],
    ['Mercredi_13h00-17h00', 'Vendredi_13h00-17h00']
  ];

  const applyExcelPayload = (data: any) => {
    setSallesData(data.salles || []);
    const enrichedTeachers = (data.enseignants || []).map((t: ExcelEnseignant, idx: number) => ({
      ...t,
      preferred_timeslots: timeslotsList[idx % timeslotsList.length]
    }));
    setEnseignantsData(enrichedTeachers);
    setPromotionsData(data.promotions || []);
  };

  const loadResourcesFromBackend = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/resources');
      if (!response.ok) throw new Error("Impossible de contacter l'API des ressources");
      
      const result = await response.json();
      if (result.success && result.data) {
        applyExcelPayload(result.data);
      }
    } catch (err: any) {
      setError("Erreur de chargement du fichier resources.xlsx depuis le backend : " + err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResourcesFromBackend();
  }, []);

  // Filtrage conservant l'index réel dans le tableau Excel
  const filteredSalles = useMemo(() => {
    const q = searchTerm.toLowerCase();
    return sallesData
      .map((item, realIdx) => ({ item, realIdx }))
      .filter(({ item: s }) => {
        if (!q) return true;
        return (
          (s["Code / Salle"] && String(s["Code / Salle"]).toLowerCase().includes(q)) ||
          (s["Bâtiment"] && String(s["Bâtiment"]).toLowerCase().includes(q)) ||
          (s["Type de Salle"] && String(s["Type de Salle"]).toLowerCase().includes(q)) ||
          (s["Équipements complémentaires"] && String(s["Équipements complémentaires"]).toLowerCase().includes(q))
        );
      });
  }, [sallesData, searchTerm]);

  const filteredEnseignants = useMemo(() => {
    const q = searchTerm.toLowerCase();
    return enseignantsData
      .map((item, realIdx) => ({ item, realIdx }))
      .filter(({ item: e }) => {
        if (!q) return true;
        const domaine = e["Domaine "] || e["Domaine"] || "";
        return (
          (e["Nom et Prénom"] && String(e["Nom et Prénom"]).toLowerCase().includes(q)) ||
          String(domaine).toLowerCase().includes(q) ||
          (e["Expertises / Technologies"] && String(e["Expertises / Technologies"]).toLowerCase().includes(q))
        );
      });
  }, [enseignantsData, searchTerm]);

  const filteredPromotions = useMemo(() => {
    const q = searchTerm.toLowerCase();
    return promotionsData
      .map((item, realIdx) => ({ item, realIdx }))
      .filter(({ item: p }) => {
        if (!q) return true;
        return (
          (p["Promotion & Intitulé"] && String(p["Promotion & Intitulé"]).toLowerCase().includes(q)) ||
          (p["Code promotion"] && String(p["Code promotion"]).toLowerCase().includes(q)) ||
          (p["Niveau / Cycle"] && String(p["Niveau / Cycle"]).toLowerCase().includes(q))
        );
      });
  }, [promotionsData, searchTerm]);

  // Ouverture modale Ajout
  const handleOpenAddModal = () => {
    setEditingIndex(null);
    setError(null);
    if (activeTab === 'salles') setFormSalle({ ...EMPTY_SALLE });
    if (activeTab === 'enseignants') setFormEnseignant({ ...EMPTY_ENSEIGNANT });
    if (activeTab === 'promotions') setFormPromotion({ ...EMPTY_PROMOTION });
    setIsModalOpen(true);
  };

  // Ouverture modale Édition
  const handleOpenEditModal = (realIdx: number) => {
    setEditingIndex(realIdx);
    setError(null);
    if (activeTab === 'salles') setFormSalle({ ...sallesData[realIdx] });
    if (activeTab === 'enseignants') {
      const t = enseignantsData[realIdx];
      setFormEnseignant({
        "Nom et Prénom": t["Nom et Prénom"] || "",
        "Domaine ": t["Domaine "] || t["Domaine"] || "",
        "Expertises / Technologies": t["Expertises / Technologies"] || ""
      });
    }
    if (activeTab === 'promotions') setFormPromotion({ ...promotionsData[realIdx] });
    setIsModalOpen(true);
  };

  // Sauvegarde (POST ou PUT) directement dans Excel via FastAPI
  const handleSaveCrud = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccessMsg(null);

    const payload =
      activeTab === 'salles'
        ? formSalle
        : activeTab === 'enseignants'
        ? formEnseignant
        : formPromotion;

    const url =
      editingIndex !== null
        ? `/api/resources/${activeTab}/${editingIndex}`
        : `/api/resources/${activeTab}`;
    const method = editingIndex !== null ? 'PUT' : 'POST';

    try {
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "Erreur lors de la sauvegarde dans Excel");
      }

      if (result.data) {
        applyExcelPayload(result.data);
      }
      setIsModalOpen(false);
      setSuccessMsg(result.message || "Modification enregistrée directement dans le fichier Excel !");
      if (onResourcesUpdated) onResourcesUpdated();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Suppression (DELETE) directement dans Excel
  const handleDeleteRow = async (realIdx: number, label: string) => {
    if (!window.confirm(`Supprimer définitivement « ${label} » du fichier Excel ?`)) return;

    setSaving(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const response = await fetch(`/api/resources/${activeTab}/${realIdx}`, {
        method: 'DELETE'
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "Erreur lors de la suppression dans Excel");
      }

      if (result.data) {
        applyExcelPayload(result.data);
      }
      setSuccessMsg(result.message || "Ligne supprimée et fichier Excel mis à jour.");
      if (onResourcesUpdated) onResourcesUpdated();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Statistiques globales
  const totalCapacity = useMemo(() => sallesData.reduce((acc, s) => acc + (Number(s["Capacité"]) || 0), 0), [sallesData]);
  const totalPrises = useMemo(() => sallesData.reduce((acc, s) => acc + (Number(s["Prises Elec."]) || 0), 0), [sallesData]);
  const totalStudents = useMemo(() => promotionsData.reduce((acc, p) => acc + (Number(p["Effectif Etudiants"]) || 0), 0), [promotionsData]);

  return (
    <div className="space-y-6 font-sans">
      {/* En-tête */}
      <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <FileSpreadsheet className="w-6 h-6 text-emerald-600" />
            <h2 className="text-xl font-bold text-ucac-navy">Données Centralisées : resources.xlsx</h2>
            <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-emerald-300">
              CRUD Synchronisé Excel
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Ajoutez, modifiez ou supprimez des ressources : chaque action met à jour directement le fichier Excel dans <code>backend/data/ressources/</code>.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleOpenAddModal}
            className="flex items-center space-x-1.5 px-4 py-2 bg-ucac-orange hover:bg-ucac-orangeHover text-white rounded-lg text-xs font-bold shadow-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>
              {activeTab === 'salles'
                ? 'Ajouter une Salle'
                : activeTab === 'enseignants'
                ? 'Ajouter un Enseignant'
                : 'Ajouter une Promotion'}
            </span>
          </button>

          <button
            onClick={loadResourcesFromBackend}
            className="flex items-center space-x-2 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-ucac-orange ${loading ? 'animate-spin' : ''}`} />
            <span>Recharger</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs font-medium p-3 rounded-lg">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold p-3 rounded-lg flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Navigation Onglets */}
      <div className="flex items-center justify-between bg-white p-2 rounded-xl border border-slate-200 shadow-sm flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveTab('salles')}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2 ${
              activeTab === 'salles' ? 'bg-ucac-navy text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            <DoorOpen className="w-4 h-4 text-ucac-orange" />
            Feuille Salles ({sallesData.length})
          </button>

          <button
            onClick={() => setActiveTab('enseignants')}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2 ${
              activeTab === 'enseignants' ? 'bg-ucac-navy text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            <User className="w-4 h-4 text-blue-400" />
            Feuille Enseignants ({enseignantsData.length})
          </button>

          <button
            onClick={() => setActiveTab('promotions')}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2 ${
              activeTab === 'promotions' ? 'bg-ucac-navy text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            <GraduationCap className="w-4 h-4 text-emerald-500" />
            Feuille Promotions ({promotionsData.length})
          </button>
        </div>

        {/* Filtre Recherche */}
        <div className="relative min-w-[240px]">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Rechercher dans la feuille..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 border border-slate-300 rounded-lg text-xs font-medium focus:ring-2 focus:ring-ucac-orange focus:outline-none text-slate-900"
          />
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* FEUILLE 1 : SALLES                                                  */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === 'salles' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-white p-3.5 rounded-xl border border-slate-200 flex items-center space-x-3">
              <Building2 className="w-5 h-5 text-ucac-navy" />
              <div>
                <div className="text-xs text-slate-500">Salles Répertoriées</div>
                <div className="text-sm font-bold text-ucac-navy">{sallesData.length} salles</div>
              </div>
            </div>
            <div className="bg-white p-3.5 rounded-xl border border-slate-200 flex items-center space-x-3">
              <DoorOpen className="w-5 h-5 text-ucac-orange" />
              <div>
                <div className="text-xs text-slate-500">Capacité Assise Globale</div>
                <div className="text-sm font-bold text-slate-800">{totalCapacity} places</div>
              </div>
            </div>
            <div className="bg-white p-3.5 rounded-xl border border-slate-200 flex items-center space-x-3">
              <Plug className="w-5 h-5 text-amber-600" />
              <div>
                <div className="text-xs text-slate-500">Prises Électriques</div>
                <div className="text-sm font-bold text-slate-800">{totalPrises} prises</div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-x-auto custom-scrollbar">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-ucac-navy text-white font-semibold">
                  <th className="p-3 border-b border-slate-700">Bâtiment</th>
                  <th className="p-3 border-b border-slate-700">Étage</th>
                  <th className="p-3 border-b border-slate-700">Code / Salle</th>
                  <th className="p-3 border-b border-slate-700">Type de Salle</th>
                  <th className="p-3 border-b border-slate-700 text-center">Capacité</th>
                  <th className="p-3 border-b border-slate-700 text-center">Prises Elec.</th>
                  <th className="p-3 border-b border-slate-700">Affichage</th>
                  <th className="p-3 border-b border-slate-700 text-center">Climatisation</th>
                  <th className="p-3 border-b border-slate-700 text-center">HVAC Smart</th>
                  <th className="p-3 border-b border-slate-700">Équipements</th>
                  <th className="p-3 border-b border-slate-700 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredSalles.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="p-4 text-center text-slate-400 italic">Chargement ou aucune salle trouvée.</td>
                  </tr>
                ) : (
                  filteredSalles.map(({ item: s, realIdx }) => (
                    <tr key={realIdx} className="hover:bg-slate-50">
                      <td className="p-3 font-semibold text-slate-800">{s["Bâtiment"]}</td>
                      <td className="p-3 text-slate-600">{s["Étage"]}</td>
                      <td className="p-3 font-bold text-ucac-navy">{s["Code / Salle"]}</td>
                      <td className="p-3">{s["Type de Salle"]}</td>
                      <td className="p-3 text-center font-bold font-mono">{s["Capacité"]} places</td>
                      <td className="p-3 text-center font-bold text-amber-700 font-mono">{s["Prises Elec."]}</td>
                      <td className="p-3">{s["Affichage (TV / Projecteur)"]}</td>
                      <td className="p-3 text-center">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${s["Climatisation"] === 'Oui' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}`}>
                          {s["Climatisation"]}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${String(s["Capteur HVAC Smart"]).includes('Oui') ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}`}>
                          {s["Capteur HVAC Smart"]}
                        </span>
                      </td>
                      <td className="p-3 text-slate-600">{s["Équipements complémentaires"]}</td>
                      <td className="p-3 text-right whitespace-nowrap">
                        <div className="inline-flex items-center space-x-1">
                          <button
                            onClick={() => handleOpenEditModal(realIdx)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                            title="Modifier"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteRow(realIdx, s["Code / Salle"])}
                            className="p-1.5 text-rose-600 hover:bg-rose-50 rounded transition-colors"
                            title="Supprimer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* FEUILLE 2 : ENSEIGNANTS                                             */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === 'enseignants' && (
        <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-x-auto custom-scrollbar">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-ucac-navy text-white font-semibold">
                <th className="p-3 border-b border-slate-700">Nom et Prénom</th>
                <th className="p-3 border-b border-slate-700">Domaine</th>
                <th className="p-3 border-b border-slate-700">Expertises / Technologies</th>
                <th className="p-3 border-b border-slate-700">Créneaux Préférés (SMA)</th>
                <th className="p-3 border-b border-slate-700 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredEnseignants.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-4 text-center text-slate-400 italic">Chargement ou aucun enseignant trouvé.</td>
                </tr>
              ) : (
                filteredEnseignants.map(({ item: e, realIdx }) => {
                  const domaine = e["Domaine "] || e["Domaine"] || "";
                  return (
                    <tr key={realIdx} className="hover:bg-slate-50">
                      <td className="p-3 font-bold text-ucac-navy flex items-center gap-2">
                        <User className="w-4 h-4 text-blue-500 shrink-0" />
                        <span>{e["Nom et Prénom"]}</span>
                      </td>
                      <td className="p-3">
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                          {domaine}
                        </span>
                      </td>
                      <td className="p-3 text-slate-600">{e["Expertises / Technologies"]}</td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1">
                          {e.preferred_timeslots?.map((slot, sIdx) => (
                            <span key={sIdx} className="px-2 py-0.5 rounded text-[10px] font-mono bg-orange-50 text-ucac-orange border border-orange-200 font-bold">
                              {slot}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="p-3 text-right whitespace-nowrap">
                        <div className="inline-flex items-center space-x-1">
                          <button
                            onClick={() => handleOpenEditModal(realIdx)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                            title="Modifier"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteRow(realIdx, e["Nom et Prénom"])}
                            className="p-1.5 text-rose-600 hover:bg-rose-50 rounded transition-colors"
                            title="Supprimer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* FEUILLE 3 : PROMOTIONS                                              */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === 'promotions' && (
        <div className="space-y-4">
          <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200 text-xs flex justify-between items-center">
            <span className="font-semibold text-slate-700">Effectif Étudiants Cumulé : <strong className="text-ucac-navy">{totalStudents} étudiants</strong></span>
            <span className="text-emerald-700 font-bold">{promotionsData.length} Promotions extraites d'Excel</span>
          </div>

          <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-x-auto custom-scrollbar">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-ucac-navy text-white font-semibold">
                  <th className="p-3 border-b border-slate-700">Promotion & Intitulé</th>
                  <th className="p-3 border-b border-slate-700">Niveau / Cycle</th>
                  <th className="p-3 border-b border-slate-700">Code Promotion</th>
                  <th className="p-3 border-b border-slate-700 text-right">Effectif Étudiants</th>
                  <th className="p-3 border-b border-slate-700 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredPromotions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-4 text-center text-slate-400 italic">Chargement ou aucune promotion trouvée.</td>
                  </tr>
                ) : (
                  filteredPromotions.map(({ item: p, realIdx }) => (
                    <tr key={realIdx} className="hover:bg-slate-50">
                      <td className="p-3 font-bold text-ucac-navy flex items-center gap-2">
                        <GraduationCap className="w-4 h-4 text-emerald-600 shrink-0" />
                        <span>{p["Promotion & Intitulé"]}</span>
                      </td>
                      <td className="p-3">
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                          {p["Niveau / Cycle"]}
                        </span>
                      </td>
                      <td className="p-3 text-slate-500 font-mono font-bold">{p["Code promotion"]}</td>
                      <td className="p-3 text-right font-bold text-slate-900 font-mono">{p["Effectif Etudiants"]} étudiants</td>
                      <td className="p-3 text-right whitespace-nowrap">
                        <div className="inline-flex items-center space-x-1">
                          <button
                            onClick={() => handleOpenEditModal(realIdx)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                            title="Modifier"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteRow(realIdx, p["Code promotion"] || p["Promotion & Intitulé"])}
                            className="p-1.5 text-rose-600 hover:bg-rose-50 rounded transition-colors"
                            title="Supprimer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* MODALE CRUD (CRÉATION / ÉDITION DIRECTE DANS EXCEL)                 */}
      {/* ------------------------------------------------------------------- */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden">
            <div className="bg-ucac-navy text-white px-5 py-4 flex items-center justify-between">
              <h3 className="text-sm font-bold">
                {editingIndex !== null ? 'Modifier' : 'Ajouter'}{' '}
                {activeTab === 'salles'
                  ? 'une Salle'
                  : activeTab === 'enseignants'
                  ? 'un Enseignant'
                  : 'une Promotion'}
              </h3>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-300 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveCrud} className="p-5 space-y-4 text-xs">
              {activeTab === 'salles' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Code / Salle *</label>
                    <input
                      type="text"
                      required
                      value={formSalle["Code / Salle"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Code / Salle": e.target.value })}
                      placeholder="Ex: B104"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Bâtiment *</label>
                    <input
                      type="text"
                      required
                      value={formSalle["Bâtiment"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Bâtiment": e.target.value })}
                      placeholder="Ex: Bâtiment B"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Étage</label>
                    <input
                      type="text"
                      value={formSalle["Étage"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Étage": e.target.value })}
                      placeholder="Ex: 1er Étage"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Type de Salle</label>
                    <input
                      type="text"
                      value={formSalle["Type de Salle"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Type de Salle": e.target.value })}
                      placeholder="Ex: Salle de cours, Labo, Amphi"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Capacité (places) *</label>
                    <input
                      type="number"
                      min={1}
                      required
                      value={formSalle["Capacité"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Capacité": Number(e.target.value) })}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Prises Électriques</label>
                    <input
                      type="number"
                      min={0}
                      value={formSalle["Prises Elec."]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Prises Elec.": Number(e.target.value) })}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Climatisation</label>
                    <select
                      value={formSalle["Climatisation"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Climatisation": e.target.value })}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    >
                      <option value="Oui">Oui</option>
                      <option value="Non">Non</option>
                    </select>
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Capteur HVAC Smart</label>
                    <select
                      value={formSalle["Capteur HVAC Smart"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Capteur HVAC Smart": e.target.value })}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    >
                      <option value="Oui">Oui</option>
                      <option value="Non">Non</option>
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block font-bold text-slate-700 mb-1">Affichage (TV / Projecteur)</label>
                    <input
                      type="text"
                      value={formSalle["Affichage (TV / Projecteur)"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Affichage (TV / Projecteur)": e.target.value })}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block font-bold text-slate-700 mb-1">Équipements complémentaires</label>
                    <input
                      type="text"
                      value={formSalle["Équipements complémentaires"]}
                      onChange={(e) => setFormSalle({ ...formSalle, "Équipements complémentaires": e.target.value })}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                </div>
              )}

              {activeTab === 'enseignants' && (
                <div className="space-y-3">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Nom et Prénom *</label>
                    <input
                      type="text"
                      required
                      value={formEnseignant["Nom et Prénom"]}
                      onChange={(e) => setFormEnseignant({ ...formEnseignant, "Nom et Prénom": e.target.value })}
                      placeholder="Ex: Dr. Paul Biya / M. Jean Dupont"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Domaine *</label>
                    <input
                      type="text"
                      required
                      value={formEnseignant["Domaine "]}
                      onChange={(e) => setFormEnseignant({ ...formEnseignant, "Domaine ": e.target.value })}
                      placeholder="Ex: Génie Logiciel, Finance, Mathématiques, Réseaux..."
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Expertises / Technologies *</label>
                    <textarea
                      rows={3}
                      required
                      value={formEnseignant["Expertises / Technologies"]}
                      onChange={(e) => setFormEnseignant({ ...formEnseignant, "Expertises / Technologies": e.target.value })}
                      placeholder="Ex: Python, IA, Bases de données SQL, Algorithmique..."
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                </div>
              )}

              {activeTab === 'promotions' && (
                <div className="space-y-3">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Promotion & Intitulé *</label>
                    <input
                      type="text"
                      required
                      value={formPromotion["Promotion & Intitulé"]}
                      onChange={(e) => setFormPromotion({ ...formPromotion, "Promotion & Intitulé": e.target.value })}
                      placeholder="Ex: Ingénieur Informatique 3ème année"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Code Promotion *</label>
                      <input
                        type="text"
                        required
                        value={formPromotion["Code promotion"]}
                        onChange={(e) => setFormPromotion({ ...formPromotion, "Code promotion": e.target.value })}
                        placeholder="Ex: X2027_INFO"
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Effectif Étudiants *</label>
                      <input
                        type="number"
                        min={1}
                        required
                        value={formPromotion["Effectif Etudiants"]}
                        onChange={(e) => setFormPromotion({ ...formPromotion, "Effectif Etudiants": Number(e.target.value) })}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Niveau / Cycle</label>
                    <input
                      type="text"
                      value={formPromotion["Niveau / Cycle"]}
                      onChange={(e) => setFormPromotion({ ...formPromotion, "Niveau / Cycle": e.target.value })}
                      placeholder="Ex: Cycle Ingénieur / Bachelor"
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-ucac-orange focus:outline-none"
                    />
                  </div>
                </div>
              )}

              <div className="pt-3 border-t border-slate-100 flex justify-end space-x-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-ucac-navy hover:bg-ucac-navyDark text-white rounded-lg font-bold flex items-center space-x-1.5 disabled:opacity-50"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4 text-ucac-orange" />}
                  <span>{saving ? 'Enregistrement...' : 'Sauvegarder dans Excel'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ResourceManager;