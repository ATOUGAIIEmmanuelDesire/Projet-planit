from ortools.sat.python import cp_model
from typing import List, Dict, Any, Optional
from app.models.schemas import CourseSessionSchema, RoomSchema, TeacherSchema, AssignmentResult
from app.core.config import settings

class PlanItCPSolver:
    """Solveur de secours combinatoire sous contraintes (Google OR-Tools CP-SAT)."""
    
    @staticmethod
    def solve_full_schedule(
        courses: List[CourseSessionSchema],
        rooms: List[RoomSchema],
        teachers: List[TeacherSchema],
        timeslots: List[str]
    ) -> List[AssignmentResult]:
        
        model = cp_model.CpModel()
        
        # Variables de décision: x[c, r, t] = 1 si le cours c est affecté à la salle r au créneau t
        x = {}
        for c_idx, c in enumerate(courses):
            for r_idx, r in enumerate(rooms):
                for t_idx, t in enumerate(timeslots):
                    x[c_idx, r_idx, t_idx] = model.NewBoolVar(f"x_{c_idx}_{r_idx}_{t_idx}")

        # Contrainte 1 : Chaque cours doit être planifié au plus une fois
        for c_idx in range(len(courses)):
            model.Add(sum(x[c_idx, r_idx, t_idx] for r_idx in range(len(rooms)) for t_idx in range(len(timeslots))) == 1)

        # Contrainte 2 : Pas de chevauchement de deux cours dans la même salle au même créneau
        for r_idx in range(len(rooms)):
            for t_idx in range(len(timeslots)):
                model.Add(sum(x[c_idx, r_idx, t_idx] for c_idx in range(len(courses))) <= 1)

        # Contrainte 3 : Pas de chevauchement pour le même enseignant au même créneau
        teacher_map = {t.id: t for t in teachers}
        for t_idx in range(len(timeslots)):
            timeslot_name = timeslots[t_idx]
            for teacher in teachers:
                teacher_courses = [c_idx for c_idx, c in enumerate(courses) if c.teacher_id == teacher.id]
                if teacher_courses:
                    model.Add(sum(x[c_idx, r_idx, t_idx] for c_idx in teacher_courses for r_idx in range(len(rooms))) <= 1)
                
                # Prise en compte de l'indisponibilité de l'enseignant
                if timeslot_name in teacher.unavailabilities:
                    for c_idx in teacher_courses:
                        for r_idx in range(len(rooms)):
                            model.Add(x[c_idx, r_idx, t_idx] == 0)

        # Contrainte 4 : Pas de chevauchement pour le même groupe d'étudiants
        groups = list({c.group_id for c in courses})
        for g_id in groups:
            group_courses = [c_idx for c_idx, c in enumerate(courses) if c.group_id == g_id]
            for t_idx in range(len(timeslots)):
                model.Add(sum(x[c_idx, r_idx, t_idx] for c_idx in group_courses for r_idx in range(len(rooms))) <= 1)

        # Contraintes dures de capacité et de type de salle (Labo)
        for c_idx, c in enumerate(courses):
            for r_idx, r in enumerate(rooms):
                if r.capacity < c.student_count or (c.requires_lab and not r.is_lab):
                    for t_idx in range(len(timeslots)):
                        model.Add(x[c_idx, r_idx, t_idx] == 0)

        # Fonction Objectif : Maximiser l'efficience énergétique + Préférences enseignants
        objective_terms = []
        for c_idx, c in enumerate(courses):
            t_obj = teacher_map.get(c.teacher_id)
            for r_idx, r in enumerate(rooms):
                hvac_score = 100 if r.has_hvac_sensor else 40
                for t_idx, t in enumerate(timeslots):
                    pref_bonus = 50 if (t_obj and t in t_obj.preferred_timeslots) else 0
                    score_weight = int(hvac_score + pref_bonus)
                    objective_terms.append(x[c_idx, r_idx, t_idx] * score_weight)

        model.Maximize(sum(objective_terms))

        # Résolution via le moteur CP-SAT
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = settings.OR_TOOLS_TIMEOUT_SECONDS
        status = solver.Solve(model)

        results = []
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            for c_idx, c in enumerate(courses):
                for r_idx, r in enumerate(rooms):
                    for t_idx, t in enumerate(timeslots):
                        if solver.Value(x[c_idx, r_idx, t_idx]) == 1:
                            hvac_kwh = settings.HVAC_KWH_SMART_SENSOR if r.has_hvac_sensor else settings.HVAC_KWH_STANDARD
                            hvac_saved = max(0.0, settings.HVAC_KWH_STANDARD - hvac_kwh)
                            results.append(AssignmentResult(
                                course_id=c.id,
                                timeslot=t,
                                assigned_room=r.name,
                                teacher_id=c.teacher_id,
                                group_id=c.group_id,
                                score=95.0 if r.has_hvac_sensor else 70.0,
                                hvac_kwh=hvac_kwh,
                                hvac_saved_kwh=hvac_saved,
                                resolution_method="OR_TOOLS_CP_SAT"
                            ))
        return results