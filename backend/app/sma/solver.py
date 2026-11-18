import re
import unicodedata
from ortools.sat.python import cp_model
from typing import List, Dict
from app.models.schemas import CourseSessionSchema, RoomSchema, TeacherSchema, AssignmentResult
from app.core.config import settings

NON_TEACHER_KEYWORDS = [
    "messe", "diversite", "aercr", "aer", "autonomie",
    "stage", "vie asso", "vie associative", "cctl", "epreuve",
    "bilan", "briefing", "debriefing", "finalisation", "projet",
    "soutenance", "jury", "travail de groupe", "restitution"
]


def _strip_accents(text: str) -> str:
    nfd = unicodedata.normalize("NFD", str(text or ""))
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn").lower()


def _is_teacherless_workroom_course(course: CourseSessionSchema) -> bool:
    name_norm = _strip_accents(getattr(course, "name", "") or getattr(course, "id", ""))
    t_id = str(getattr(course, "teacher_id", "") or "").strip()
    if t_id in ("", "Sans enseignant"):
        return True
    if any(kw in name_norm for kw in NON_TEACHER_KEYWORDS):
        return True
    return bool(re.search(r"\bproj\.?(?:\s|$)", name_norm))


def _bimester_from_timeslot(timeslot: str) -> int:
    m = re.search(r"s(\d{1,2})_", str(timeslot or "").lower())
    if m:
        return (int(m.group(1)) - 1) // 8
    return 0


class PlanItCPSolver:
    """Solveur combinatoire sous contraintes (Google OR-Tools CP-SAT)."""

    @staticmethod
    def solve_full_schedule(
        courses: List[CourseSessionSchema],
        rooms: List[RoomSchema],
        teachers: List[TeacherSchema],
        timeslots: List[str]
    ) -> List[AssignmentResult]:

        model = cp_model.CpModel()

        # Variables de décision : x[c, r, t] = 1 si la séance c est affectée à la salle r au créneau t
        x = {}
        for c_idx, c in enumerate(courses):
            for r_idx, r in enumerate(rooms):
                for t_idx, t in enumerate(timeslots):
                    x[c_idx, r_idx, t_idx] = model.NewBoolVar(f"x_{c_idx}_{r_idx}_{t_idx}")

        # Contrainte 1 : Chaque séance est planifiée exactement une fois
        for c_idx in range(len(courses)):
            model.Add(sum(x[c_idx, r_idx, t_idx] for r_idx in range(len(rooms)) for t_idx in range(len(timeslots))) == 1)

        # Contrainte 2 : Pas de chevauchement de deux séances dans la même salle au même créneau
        for r_idx in range(len(rooms)):
            for t_idx in range(len(timeslots)):
                model.Add(sum(x[c_idx, r_idx, t_idx] for c_idx in range(len(courses))) <= 1)

        # Contrainte 3 : Pas de chevauchement enseignant (uniquement pour les cours encadrés)
        teacher_map = {t.id: t for t in teachers}
        for t_idx in range(len(timeslots)):
            timeslot_name = timeslots[t_idx]
            for teacher in teachers:
                teacher_courses = [
                    c_idx for c_idx, c in enumerate(courses)
                    if not _is_teacherless_workroom_course(c) and c.teacher_id == teacher.id
                ]
                if teacher_courses:
                    model.Add(sum(x[c_idx, r_idx, t_idx] for c_idx in teacher_courses for r_idx in range(len(rooms))) <= 1)

                if timeslot_name in teacher.unavailabilities:
                    for c_idx in teacher_courses:
                        for r_idx in range(len(rooms)):
                            model.Add(x[c_idx, r_idx, t_idx] == 0)

        # Contrainte 4 : Pas de chevauchement pour une même promotion
        groups = list({c.group_id for c in courses})
        for g_id in groups:
            group_courses = [c_idx for c_idx, c in enumerate(courses) if c.group_id == g_id]
            for t_idx in range(len(timeslots)):
                model.Add(sum(x[c_idx, r_idx, t_idx] for c_idx in group_courses for r_idx in range(len(rooms))) <= 1)

        # Contrainte 5 : Une et une seule salle par promotion sur une période de 02 mois (bimestre)
        promo_bimester_courses: Dict[tuple, List[int]] = {}
        for c_idx, c in enumerate(courses):
            b_idx = _bimester_from_timeslot(getattr(c, "preferred_timeslot", "") or "")
            promo_bimester_courses.setdefault((c.group_id, b_idx), []).append(c_idx)

        for (g_id, b_idx), c_indices in promo_bimester_courses.items():
            if len(c_indices) > 1:
                first_c = c_indices[0]
                for other_c in c_indices[1:]:
                    for r_idx in range(len(rooms)):
                        model.Add(
                            sum(x[first_c, r_idx, t_idx] for t_idx in range(len(timeslots))) ==
                            sum(x[other_c, r_idx, t_idx] for t_idx in range(len(timeslots)))
                        )

        # Contraintes dures : Capacité, Laboratoire, et Salle de travail pour activités sans enseignant
        has_workrooms = any("amphi" not in r.name.lower() for r in rooms)
        for c_idx, c in enumerate(courses):
            teacherless = _is_teacherless_workroom_course(c)
            for r_idx, r in enumerate(rooms):
                is_amphi = "amphi" in r.name.lower()
                if r.capacity < c.student_count or (c.requires_lab and not r.is_lab):
                    for t_idx in range(len(timeslots)):
                        model.Add(x[c_idx, r_idx, t_idx] == 0)
                elif teacherless and has_workrooms and is_amphi and c.student_count <= max(
                    (rm.capacity for rm in rooms if "amphi" not in rm.name.lower()),
                    default=0
                ):
                    for t_idx in range(len(timeslots)):
                        model.Add(x[c_idx, r_idx, t_idx] == 0)

        # Fonction Objectif : Efficience énergétique + Préférences enseignants
        objective_terms = []
        for c_idx, c in enumerate(courses):
            teacherless = _is_teacherless_workroom_course(c)
            t_obj = None if teacherless else teacher_map.get(c.teacher_id)
            for r_idx, r in enumerate(rooms):
                hvac_score = 100 if r.has_hvac_sensor else 45
                for t_idx, t in enumerate(timeslots):
                    pref_bonus = 50 if (t_obj and t in t_obj.preferred_timeslots) else 0
                    score_weight = int(hvac_score + pref_bonus)
                    objective_terms.append(x[c_idx, r_idx, t_idx] * score_weight)

        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = settings.OR_TOOLS_TIMEOUT_SECONDS
        status = solver.Solve(model)

        results = []
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            for c_idx, c in enumerate(courses):
                teacherless = _is_teacherless_workroom_course(c)
                for r_idx, r in enumerate(rooms):
                    for t_idx, t in enumerate(timeslots):
                        if solver.Value(x[c_idx, r_idx, t_idx]) == 1:
                            hvac_kwh = settings.HVAC_KWH_SMART_SENSOR if r.has_hvac_sensor else settings.HVAC_KWH_STANDARD
                            hvac_saved = max(0.0, settings.HVAC_KWH_STANDARD - hvac_kwh)
                            results.append(AssignmentResult(
                                course_id=c.id,
                                timeslot=t,
                                assigned_room=r.name,
                                teacher_id="Sans enseignant" if teacherless else c.teacher_id,
                                group_id=c.group_id,
                                score=95.0 if r.has_hvac_sensor else 75.0,
                                hvac_kwh=hvac_kwh,
                                hvac_saved_kwh=hvac_saved,
                                resolution_method="OR_TOOLS_CP_SAT"
                            ))
        return results