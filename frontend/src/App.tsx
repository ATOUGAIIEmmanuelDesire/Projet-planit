import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { TabNavigation } from './components/TabNavigation';
import { SMASimulator } from './components/SMASimulator';
import { TimetableGrid } from './components/TimetableGrid';
import { HybridAssistant } from './components/HybridAssistant';
import { AnalyticsROI } from './components/AnalyticsROI';
import { ResourceManager } from './components/RessourceManager';
import { Login } from './components/Login';
import { Register } from './components/Register';

import {
  Room,
  Teacher,
  Group,
  FIPAACLMessage,
  AssignmentResult,
  FullScheduleRequest,
  CourseSession,
  UserProfile,
} from './types';
import { apiService, SMALogWebSocket } from './services/api';

// Mots-clés des activités hors-cours (ne nécessitant aucun enseignant)
const NON_TEACHER_ACTIVITIES = [
  'messe',
  'diversite',
  'diversité',
  'aercr',
  'aer',
  'autonomie',
  'stage',
  'vie asso',
  'vie associative',
  'cctl',
  'epreuve',
  'épreuve'
];

/**
 * Détermine si une activité nécessite la présence d'un enseignant titulaire.
 */
const requiresTeacher = (courseName: string): boolean => {
  if (!courseName) return true;
  const norm = courseName.toLowerCase();
  return !NON_TEACHER_ACTIVITIES.some((keyword) => norm.includes(keyword));
};

export const App: React.FC = () => {
  // État d'authentification
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(() => {
    const saved = localStorage.getItem('planit_user') || sessionStorage.getItem('planit_user');
    return saved ? (JSON.parse(saved) as UserProfile) : null;
  });
  const [authView, setAuthView] = useState<'login' | 'register'>('login');

  const [activeTab, setActiveTab] = useState<number>(1); // ID 1 = Emploi du temps par défaut
  const [campus, setCampus] = useState<string>('Douala - Yansoki');

  // Ressources et état de la simulation
  const [rooms, setRooms] = useState<Room[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);

  const [messages, setMessages] = useState<FIPAACLMessage[]>([]);
  const [assignments, setAssignments] = useState<AssignmentResult[]>([]);

  const [occupancyRate, setOccupancyRate] = useState<number>(85.4);
  const [unresolvedConflicts, setUnresolvedConflicts] = useState<number>(0);
  const [resolvedConflicts, setResolvedConflicts] = useState<number>(0);
  const [lastExecTimeMs, setLastExecTimeMs] = useState<number>(180);
  const [totalSavedKwh, setTotalSavedKwh] = useState<number>(420.5);

  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  const roundValue = (val: number) => Math.round(val * 10) / 10;

  useEffect(() => {
    if (!currentUser) return undefined;

    // 1. Charger les ressources (Salles, Profs, Groupes)
    apiService.getResources().then((data) => {
      if (data) {
        setRooms(data.rooms || []);
        setTeachers(data.teachers || []);
        setGroups(data.groups || []);
        if (typeof data.conflicts_resolved === 'number') {
          setResolvedConflicts(data.conflicts_resolved);
        }
      }
    }).catch(console.error);

    // 2. Charger automatiquement les emplois du temps (.ics) stockés sur le backend FastAPI
    apiService.getAllAssignments().then((loadedAssignments) => {
      if (Array.isArray(loadedAssignments) && loadedAssignments.length > 0) {
        setAssignments(loadedAssignments);
        const kwh = loadedAssignments.reduce((acc, curr) => acc + (curr.hvac_saved_kwh || 0.85), 0);
        setTotalSavedKwh(roundValue(kwh));
      }
    }).catch(console.error);

    // 3. Connexion WebSocket temps réel pour les journaux FIPA-ACL
    let wsManager: SMALogWebSocket | null = null;
    try {
      wsManager = new SMALogWebSocket();
      wsManager.connect(
        (msg) => {
          setMessages((prev) => [...prev, msg]);
        },
        () => setWsConnected(false)
      );
      setWsConnected(true);
    } catch (err) {
      console.error("Erreur de connexion WebSocket :", err);
      setWsConnected(false);
    }

    return () => {
      wsManager?.disconnect();
    };
  }, [currentUser]);

  const handleLoginSuccess = (user: UserProfile) => {
    setCurrentUser(user);
    if (user.campus) {
      setCampus(user.campus);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('planit_token');
    localStorage.removeItem('planit_user');
    sessionStorage.removeItem('planit_token');
    sessionStorage.removeItem('planit_user');
    setCurrentUser(null);
    setAuthView('login');
  };

  const handleRunSimulation = async () => {
    setIsSimulating(true);

    let coursesToSchedule: CourseSession[] = [];
    let timeslotsToSchedule: string[] = [];

    if (assignments.length > 0) {
      const uniqueCoursesMap = new Map<string, CourseSession>();

      assignments.forEach((a) => {
        if (a.course_id && !uniqueCoursesMap.has(a.course_id)) {
          const needsTeacher = requiresTeacher(a.course_id);
          const isStage = a.course_id.toLowerCase().includes('stage');

          uniqueCoursesMap.set(a.course_id, {
            id: a.course_id,
            name: a.course_id,
            teacher_id: needsTeacher ? (a.teacher_id || 'T_ENSEIGNANT') : 'Sans enseignant',
            group_id: a.group_id || 'PROMO',
            student_count: isStage ? 0 : 35,
            requires_lab: a.course_id.toLowerCase().includes('lab') || a.course_id.toLowerCase().includes('tp'),
            preferred_timeslot: a.timeslot
          });
        }
      });

      coursesToSchedule = Array.from(uniqueCoursesMap.values());
      timeslotsToSchedule = Array.from(new Set(assignments.map((a) => a.timeslot)));
    } else {
      coursesToSchedule = [
        {
          id: "COURSE_DEFAULT",
          name: "Cours de démonstration",
          teacher_id: "T_KIMBA",
          group_id: "B1",
          student_count: 40,
          requires_lab: false,
          preferred_timeslot: "S45_Lundi_08h00-12h00"
        }
      ];
      timeslotsToSchedule = ["S45_Lundi_08h00-12h00", "S45_Lundi_13h00-17h00"];
    }

    const payload: FullScheduleRequest = {
      courses: coursesToSchedule,
      timeslots: timeslotsToSchedule
    };

    try {
      const response = await apiService.generateFullSchedule(payload);
      console.log("Résultat négociation SMA sur cours ICS réels :", response);

      if (response) {
        if (response.assignments && response.assignments.length > 0) {
          handleAssignmentsUpdated(response.assignments);
        }
        if (response.global_occupancy_rate !== undefined) setOccupancyRate(response.global_occupancy_rate);
        if (response.conflicts_unresolved !== undefined) setUnresolvedConflicts(response.conflicts_unresolved);
        if (response.conflicts_resolved !== undefined) setResolvedConflicts(response.conflicts_resolved);
        if (response.execution_time_ms !== undefined) setLastExecTimeMs(response.execution_time_ms);
      }
    } catch (error) {
      console.error("Erreur lors de la négociation SMA :", error);
    } finally {
      setIsSimulating(false);
    }
  };

  const handleInjectConflict = async () => {
    const targetSlot = assignments.length > 0 ? assignments[0].timeslot : 'S45_Lundi_08h00-12h00';
    const targetGroup = assignments.length > 0 ? assignments[0].group_id : 'B1';
    try {
      const response = await apiService.triggerSingleNegotiation('CONFLICT_TEST', targetSlot, 200, 'T_KIMBA', targetGroup);
      if (response) {
        if (typeof response.conflicts_resolved === 'number') {
          setResolvedConflicts(response.conflicts_resolved);
        } else {
          setResolvedConflicts((prev) => prev + 1);
        }
        if (typeof response.execution_time_ms === 'number') {
          setLastExecTimeMs(response.execution_time_ms);
        }
      }
    } catch (error) {
      console.error("Erreur lors de l'injection de conflit :", error);
    }
  };

  const handleClearLogs = () => {
    setMessages([]);
  };

  const handleAssignmentsUpdated = (newAssignments: AssignmentResult[]) => {
    if (Array.isArray(newAssignments)) {
      setAssignments(newAssignments);
      const kwh = newAssignments.reduce((acc, curr) => acc + (curr.hvac_saved_kwh || 0.85), 0);
      setTotalSavedKwh(roundValue(kwh));
    }
  };

  // Affichage des écrans Connexion / Inscription tant que l'utilisateur n'est pas connecté
  if (!currentUser) {
    return authView === 'login' ? (
      <Login
        onSuccess={handleLoginSuccess}
        onSwitchToRegister={() => setAuthView('register')}
      />
    ) : (
      <Register onSwitchToLogin={() => setAuthView('login')} />
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Header
        campus={campus}
        setCampus={setCampus}
        occupancyRate={occupancyRate}
        unresolvedConflicts={unresolvedConflicts}
        resolvedConflicts={resolvedConflicts}
        lastExecTimeMs={lastExecTimeMs}
        totalSavedKwh={totalSavedKwh}
        wsConnected={wsConnected}
        currentUser={currentUser}
        onLogout={handleLogout}
      />

      <TabNavigation activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        {/* Onglet 1 : Emploi du Temps */}
        {activeTab === 1 && (
          <TimetableGrid
            assignments={assignments}
            onAssignmentsUpdated={handleAssignmentsUpdated}
          />
        )}

        {/* Onglet 2 : Simulateur SMA */}
        {activeTab === 2 && (
          <SMASimulator
            messages={messages}
            onRunSimulation={handleRunSimulation}
            onInjectConflict={handleInjectConflict}
            onClearLogs={handleClearLogs}
            isSimulating={isSimulating}
          />
        )}

        {/* Onglet 3 : Assistant Hybride */}
        {activeTab === 3 && <HybridAssistant assignments={assignments} />}

        {/* Onglet 4 : Analytics ROI */}
        {activeTab === 4 && <AnalyticsROI assignments={assignments} rooms={rooms} />}

        {/* Onglet 5 : Gestion Ressources */}
        {activeTab === 5 && <ResourceManager rooms={rooms} teachers={teachers} groups={groups} />}
      </main>
    </div>
  );
};

export default App;