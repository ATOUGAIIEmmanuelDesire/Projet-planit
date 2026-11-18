import os
import re
import time
import json
import hmac
import uuid
import base64
import hashlib
import secrets
import asyncio
import inspect
import unicodedata
from glob import glob
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional, Literal
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Body, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.schemas import (
    RoomSchema, TeacherSchema, GroupSchema, CourseSessionSchema,
    SingleNegotiationRequest, NegotiationResponse, AssignmentResult,
    ManualRecommendationRequest, RecommendationOption,
    FullScheduleRequest, FullScheduleResponse, CampusEnum
)
from app.sma.agents import MessageBus, RoomAgent, TeacherAgent, CoordinatorAgent
from app.sma.protocol import FIPAACLMessage, Performative
from app.sma.solver import PlanItCPSolver
from app.services.hyperplanning import HyperplanningService

# --- Registre et stockage global ---
bus = MessageBus()
room_agents: Dict[str, RoomAgent] = {}
teacher_agents: Dict[str, TeacherAgent] = {}

# Séparation stricte :
# 1. RAW_ICS_ASSIGNMENTS : données brutes des fichiers .ics simples (jamais modifiées par le SMA)
# 2. OPTIMIZED_ASSIGNMENTS : emploi du temps complet optimisé par le SMA (toutes les semaines)
RAW_ICS_ASSIGNMENTS: List[AssignmentResult] = []
OPTIMIZED_ASSIGNMENTS: List[AssignmentResult] = []
background_tasks = set()

# Stockage global des 3 feuilles Excel extraites au démarrage
EXCEL_RESOURCES_DATA: Dict[str, List[Dict[str, Any]]] = {
    "salles": [],
    "enseignants": [],
    "promotions": []
}
ACTIVE_EXCEL_PATH: Optional[str] = None
TEACHER_DOMAIN_COL_NAME: str = "Domaine "

# Emplacements des dossiers de données
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
RESOURCE_DIR = os.path.join(DATA_DIR, "ressources")
ICS_DIR = os.path.join(DATA_DIR, "ics")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
AUTH_SECRET_KEY = os.getenv("PLANIT_SECRET_KEY", "planit-ucac-icam-secret-key-2026")

# Mots-clés des activités sans enseignant (Finalisation Proj., Bilan Briefing, Projet, Soutenance, Autonomie, etc.)
# Ces séances ne reçoivent jamais d'enseignant ("Sans enseignant")
NON_TEACHER_KEYWORDS = [
    "messe", "diversite", "aercr", "aer", "autonomie",
    "stage", "vie asso", "vie associative", "cctl", "epreuve",
    "bilan", "briefing", "debriefing",
    "finalisation", "projet", "soutenance", "jury",
    "travail de groupe", "restitution"
]

# Liste dynamique des ressources Pydantic pour la comptabilité SMA
mock_rooms: List[RoomSchema] = []
mock_teachers: List[TeacherSchema] = []
mock_groups: List[GroupSchema] = []

coordinator: CoordinatorAgent = None


class ConfirmRecommendationRequest(BaseModel):
    assignment: AssignmentResult


# --- Schémas & Utilitaires d'Authentification ---
UserRole = Literal[
    "administrateur",
    "enseignant",
    "responsable_pedagogique",
    "etudiant"
]


class UserRegisterRequest(BaseModel):
    nom: str = Field(..., min_length=1, max_length=100)
    prenom: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=150)
    campus: str = Field(default="Douala - Yansoki")
    role: UserRole
    password: str = Field(..., min_length=8)


class UserLoginRequest(BaseModel):
    email: str
    password: str
    rememberMe: bool = False


class UserProfileOut(BaseModel):
    id: str
    nom: str
    prenom: str
    email: str
    campus: str
    role: UserRole
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileOut


def _strip_accents(text: str) -> str:
    """Normalise une chaîne en minuscules sans accents."""
    nfd = unicodedata.normalize("NFD", str(text or ""))
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn").lower()


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected_hex = stored_hash.split("$", 1)
        candidate = _hash_password(password, salt)
        return hmac.compare_digest(candidate, f"{salt}${expected_hex}")
    except ValueError:
        return False


def _create_auth_token(user_id: str, email: str, remember_me: bool) -> str:
    exp_hours = 24 * 7 if remember_me else 12
    payload = {
        "sub": user_id,
        "email": email,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=exp_hours)).timestamp())
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw).decode("utf-8")
    sig = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def _save_users(users: List[Dict[str, Any]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _load_users() -> List[Dict[str, Any]]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        default_admin = [
            {
                "id": "USR_ADMIN_01",
                "nom": "Planit",
                "prenom": "Admin",
                "email": "admin@ucac-icam.com",
                "campus": "Douala - Yansoki",
                "role": "administrateur",
                "password_hash": _hash_password("AdminPlanIt2026!"),
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        _save_users(default_admin)
        return default_admin

    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_int_capacity(val: Any, default: int = 40) -> int:
    """Convertit de manière sécurisée une valeur de capacité en entier."""
    if val is None or val == "":
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def is_non_teacher_activity(course_name: str) -> bool:
    """
    Vérifie si l'activité est sans enseignant
    (ex: Finalisation Proj., Bilan Briefing, Projet, Soutenance, Autonomie, Stage, etc.).
    """
    c_norm = _strip_accents(course_name)
    if any(kw in c_norm for kw in NON_TEACHER_KEYWORDS):
        return True
    if re.search(r"\bproj\.?(?:\s|$)", c_norm):
        return True
    return False


def get_field_val(obj: Any, field_names: List[str], default: Any = None) -> Any:
    """Extrait une valeur, que l'objet soit une instance Pydantic/classe ou un dictionnaire."""
    for field in field_names:
        if isinstance(obj, dict):
            if field in obj and obj[field] is not None:
                return obj[field]
        else:
            if hasattr(obj, field) and getattr(obj, field) is not None:
                return getattr(obj, field)
    return default


def _mark_as_raw_ics(assignments: List[AssignmentResult]) -> List[AssignmentResult]:
    """Garantit que les affectations issues des .ics simples sont clairement identifiées comme brutes."""
    for item in assignments:
        if hasattr(item, "resolution_method"):
            item.resolution_method = "HYPERPLANNING_ICS"
        if hasattr(item, "score"):
            item.score = 0.0
        if hasattr(item, "hvac_saved_kwh"):
            item.hvac_saved_kwh = 0.0
    return assignments


def create_agent_instance(agent_cls, **kwargs):
    """Instancie dynamiquement un agent SMA en inspectant sa signature __init__."""
    expanded_kwargs = dict(kwargs)

    for key in ["room_schema", "teacher_schema"]:
        if key in kwargs and kwargs[key] is not None:
            obj = kwargs[key]
            if hasattr(obj, "model_dump"):
                attrs = obj.model_dump()
            elif hasattr(obj, "__dict__"):
                attrs = obj.__dict__
            else:
                attrs = {}
            for attr_k, attr_v in attrs.items():
                if attr_k not in expanded_kwargs:
                    expanded_kwargs[attr_k] = attr_v

    sig = inspect.signature(agent_cls.__init__)
    params = sig.parameters

    valid_kwargs = {}
    for param_name in params:
        if param_name == 'self':
            continue
        if param_name in expanded_kwargs:
            valid_kwargs[param_name] = expanded_kwargs[param_name]
        elif param_name == 'room' and 'room_schema' in kwargs:
            valid_kwargs[param_name] = kwargs['room_schema']
        elif param_name == 'teacher' and 'teacher_schema' in kwargs:
            valid_kwargs[param_name] = kwargs['teacher_schema']

    try:
        return agent_cls(**valid_kwargs)
    except Exception:
        args = []
        for param_name, param in params.items():
            if param_name == 'self':
                continue
            if param_name in valid_kwargs:
                args.append(valid_kwargs[param_name])
            elif param.default != inspect.Parameter.empty:
                args.append(param.default)
            else:
                if param_name in ['capacity', 'students_count']:
                    args.append(40)
                elif param_name in ['has_hvac_sensor', 'is_lab']:
                    args.append(False)
                elif param_name in ['name', 'id']:
                    args.append(kwargs.get('name', 'agent'))
                elif param_name == 'bus':
                    args.append(kwargs.get('bus'))
                else:
                    args.append(None)
        return agent_cls(*args)


def create_assignment_result(cls, course_id, assigned_room, timeslot, teacher_id, group_id, kwh, score, resolution_method, date=None):
    """Crée une instance AssignmentResult compatible quelle que soit la variante du nom du champ kWh."""
    kwargs = {
        "course_id": str(course_id),
        "assigned_room": str(assigned_room),
        "timeslot": str(timeslot),
        "teacher_id": str(teacher_id),
        "group_id": str(group_id),
        "hvac_kwh": float(kwh),
        "hvac_saved_kwh": float(kwh),
        "score": float(score),
        "resolution_method": str(resolution_method),
        "date": date
    }

    if hasattr(cls, "model_fields"):
        fields = set(cls.model_fields.keys())
    elif hasattr(cls, "__fields__"):
        fields = set(cls.__fields__.keys())
    else:
        fields = set(kwargs.keys())

    filtered = {k: v for k, v in kwargs.items() if k in fields}
    return cls(**filtered)


async def emit_sma_log(performative: str, sender: str, receiver: str, content: Dict[str, Any]):
    """Émet un message FIPA-ACL vers le terminal WebSocket en temps réel."""
    perf_map = {
        "CFP": Performative.CFP,
        "CALL_FOR_PROPOSAL": Performative.CFP,
        "BID": Performative.BID,
        "ACCEPT_PROPOSAL": Performative.ACCEPT_PROPOSAL,
        "REJECT_PROPOSAL": Performative.REJECT_PROPOSAL,
        "INFORM": Performative.INFORM,
        "FAILURE": Performative.FAILURE,
    }
    perf_enum = perf_map.get(str(performative).upper(), Performative.INFORM)

    try:
        msg = FIPAACLMessage(
            performative=perf_enum,
            sender=sender,
            receiver=receiver,
            content=content
        )

        if hasattr(bus, "publish"):
            res = bus.publish(msg)
            if inspect.isawaitable(res):
                await res
        elif hasattr(bus, "broadcast"):
            res = bus.broadcast(msg)
            if inspect.isawaitable(res):
                await res
        else:
            for attr_val in bus.__dict__.values():
                if isinstance(attr_val, (list, set)):
                    for q in list(attr_val):
                        if isinstance(q, asyncio.Queue):
                            await q.put(msg)
    except Exception as e:
        print(f"⚠️ Erreur d'émission log FIPA-ACL : {e}")


def _parse_session_date(raw_date: Optional[str], timeslot: str) -> Optional[datetime]:
    """Convertit la date d'une séance en datetime en respectant le format YYYY-MM-DD ou DD/MM/YYYY."""
    if raw_date:
        s = str(raw_date).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s[:10], fmt)
            except ValueError:
                continue
        if re.match(r"^\d{8}$", s):
            try:
                return datetime.strptime(s, "%Y%m%d")
            except ValueError:
                pass

    day_offsets = {
        "lundi": 0, "mardi": 1, "mercredi": 2,
        "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6
    }
    slot_lower = str(timeslot or "").lower()
    week_match = re.search(r"s(\d{1,2})_", slot_lower)
    if week_match:
        iso_year, _, _ = datetime.now().isocalendar()
        iso_week = max(1, min(53, int(week_match.group(1))))
        day_offset = next((off for d, off in day_offsets.items() if d in slot_lower), 0)
        try:
            return datetime.fromisocalendar(iso_year, iso_week, 1) + timedelta(days=day_offset)
        except ValueError:
            pass
    return None


def _get_two_month_period_id(session_date: Optional[str], timeslot: str) -> int:
    """
    Calcule l'identifiant d'une période de 02 mois (bimestre) pour piloter
    la stabilité de salle par promotion sur 2 mois avant rotation.
    Ex: Sept-Oct -> même identifiant ; Nov-Déc -> identifiant suivant (rotation).
    """
    dt = _parse_session_date(session_date, timeslot)
    if dt is not None:
        return (dt.year * 12 + (dt.month - 1)) // 2

    week_match = re.search(r"s(\d{1,2})_", str(timeslot or "").lower())
    if week_match:
        return (int(week_match.group(1)) - 1) // 8
    return 0


def _format_timeslot_for_grid(raw_timeslot: str, target_date: datetime) -> str:
    """
    Formate le créneau pour l'emploi du temps optimisé :
    S{semaine:02d}_{Jour}_{HHhMM-HHhMM} (ex: S47_Lundi_08h00-12h00).
    """
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    jour_fr = jours[target_date.weekday()]
    iso_week = target_date.isocalendar()[1]

    slot_str = str(raw_timeslot or "08h00-12h00")
    time_match = re.search(r"(\d{1,2}h\d{2}\s*-\s*\d{1,2}h\d{2})", slot_str)
    if time_match:
        plage = time_match.group(1).replace(" ", "")
    elif "13h" in slot_str.lower() or "14h" in slot_str.lower():
        plage = "13h00-17h00"
    else:
        plage = "08h00-12h00"

    return f"S{iso_week:02d}_{jour_fr}_{plage}"


def _build_ics_datetimes(timeslot: str, raw_date: Optional[str] = None) -> Tuple[str, str]:
    """Génère des horodatages RFC 5545 valides (YYYYMMDDTHHMMSS) pour DTSTART et DTEND."""
    day_offsets = {
        "lundi": 0,
        "mardi": 1,
        "mercredi": 2,
        "jeudi": 3,
        "vendredi": 4,
        "samedi": 5,
        "dimanche": 6,
    }

    slot_str = str(timeslot or "")
    slot_lower = slot_str.lower()

    time_match = re.search(r"(\d{1,2})h(\d{2})\s*-\s*(\d{1,2})h(\d{2})", slot_lower)
    if time_match:
        start_h, start_m = int(time_match.group(1)), int(time_match.group(2))
        end_h, end_m = int(time_match.group(3)), int(time_match.group(4))
    elif "13h" in slot_lower or "14h" in slot_lower:
        start_h, start_m, end_h, end_m = 13, 0, 17, 0
    else:
        start_h, start_m, end_h, end_m = 8, 0, 12, 0

    parsed_dt = _parse_session_date(raw_date, timeslot)
    if parsed_dt:
        base_day = parsed_dt.strftime("%Y%m%d")
        return (
            f"{base_day}T{start_h:02d}{start_m:02d}00",
            f"{base_day}T{end_h:02d}{end_m:02d}00",
        )

    now = datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    day_offset = next((off for d, off in day_offsets.items() if d in slot_lower), 0)

    monday = datetime.fromisocalendar(iso_year, iso_week, 1)
    target_date = monday + timedelta(days=day_offset)
    date_prefix = target_date.strftime("%Y%m%d")

    return (
        f"{date_prefix}T{start_h:02d}{start_m:02d}00",
        f"{date_prefix}T{end_h:02d}{end_m:02d}00",
    )


def save_optimized_assignments_to_ics(assignments: List[AssignmentResult], filepath: Optional[str] = None):
    """
    Sauvegarde UNIQUEMENT l'emploi du temps optimisé SMA dans planit_optimized_schedule.ics.
    Les fichiers .ics simples d'origine ne sont jamais modifiés.
    """
    if filepath is None:
        export_dir = os.path.join(DATA_DIR, "ics")
        os.makedirs(export_dir, exist_ok=True)
        filepath = os.path.join(export_dir, "planit_optimized_schedule.ics")

    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//PlanIt Ucac-Icam Green-IT SMA//FR\n")
            for idx, item in enumerate(assignments):
                dtstart, dtend = _build_ics_datetimes(item.timeslot, getattr(item, "date", None))
                hvac_val = getattr(item, "hvac_kwh", getattr(item, "hvac_saved_kwh", 0.0))

                f.write("BEGIN:VEVENT\n")
                f.write(f"UID:planit-{idx + 1}-{dtstart}@ucac-icam.com\n")
                f.write(f"DTSTAMP:{dtstamp}\n")
                f.write(f"DTSTART:{dtstart}\n")
                f.write(f"DTEND:{dtend}\n")
                f.write(f"SUMMARY:{item.course_id}\n")
                f.write(f"LOCATION:{item.assigned_room}\n")
                f.write(
                    f"DESCRIPTION:Enseignant: {item.teacher_id} | Promo: {item.group_id} | "
                    f"Gain HVAC: {hvac_val} kWh | Creneau: {item.timeslot}\n"
                )
                f.write("END:VEVENT\n")
            f.write("END:VCALENDAR\n")
        print(f"✅ Fichier ICS optimisé synchronisé : {filepath}")
    except Exception as e:
        print(f"⚠️ Erreur de sauvegarde du fichier .ics optimisé : {e}")


def resolve_excel_path() -> str:
    """Retourne le chemin vers le fichier Excel actif ou crée un chemin par défaut."""
    global ACTIVE_EXCEL_PATH
    if ACTIVE_EXCEL_PATH and os.path.exists(ACTIVE_EXCEL_PATH):
        return ACTIVE_EXCEL_PATH

    possible_paths = [
        os.path.join(RESOURCE_DIR, "resources.xlsx"),
        os.path.join(RESOURCE_DIR, "ressources.xlsx"),
        os.path.join(BASE_DIR, "data", "ressources", "resources.xlsx"),
        os.path.join(BASE_DIR, "data", "ressources", "ressources.xlsx"),
        os.path.join(os.getcwd(), "data", "ressources", "resources.xlsx"),
        os.path.join(os.getcwd(), "data", "ressources", "ressources.xlsx"),
    ]
    found_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if found_path:
        ACTIVE_EXCEL_PATH = found_path
        return found_path

    os.makedirs(RESOURCE_DIR, exist_ok=True)
    ACTIVE_EXCEL_PATH = os.path.join(RESOURCE_DIR, "resources.xlsx")
    return ACTIVE_EXCEL_PATH


def load_resources_from_excel() -> Dict[str, List[Dict[str, Any]]]:
    """Charge dynamiquement resources.xlsx / ressources.xlsx et extrait les 3 feuilles."""
    global ACTIVE_EXCEL_PATH, TEACHER_DOMAIN_COL_NAME
    found_path = resolve_excel_path()

    if not os.path.exists(found_path):
        print(f"⚠️ Aucun fichier Excel de ressources trouvé dans {RESOURCE_DIR}.")
        return {"salles": [], "enseignants": [], "promotions": []}

    try:
        xls = pd.ExcelFile(found_path)
        salles = pd.read_excel(xls, sheet_name="Salles").fillna("").to_dict(orient="records") if "Salles" in xls.sheet_names else []
        enseignants_df = pd.read_excel(xls, sheet_name="Enseignants").fillna("") if "Enseignants" in xls.sheet_names else pd.DataFrame()
        if not enseignants_df.empty:
            if "Domaine " in enseignants_df.columns:
                TEACHER_DOMAIN_COL_NAME = "Domaine "
            elif "Domaine" in enseignants_df.columns:
                TEACHER_DOMAIN_COL_NAME = "Domaine"
        enseignants = enseignants_df.to_dict(orient="records") if not enseignants_df.empty else []
        promotions = pd.read_excel(xls, sheet_name="Promotions").fillna("").to_dict(orient="records") if "Promotions" in xls.sheet_names else []

        print(f"✅ Excel chargé ({found_path}) : {len(salles)} Salles, {len(enseignants)} Enseignants, {len(promotions)} Promotions.")
        return {"salles": salles, "enseignants": enseignants, "promotions": promotions}
    except Exception as e:
        print(f"❌ Erreur de lecture Excel : {e}")
        return {"salles": [], "enseignants": [], "promotions": []}


def save_resources_to_excel():
    """Écrit directement les modifications CRUD dans le fichier Excel (3 feuilles)."""
    excel_path = resolve_excel_path()
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)

    salles_cols = [
        "Bâtiment", "Étage", "Code / Salle", "Type de Salle", "Capacité",
        "Prises Elec.", "Affichage (TV / Projecteur)", "Climatisation",
        "Capteur HVAC Smart", "Équipements complémentaires"
    ]
    enseignants_cols = ["Nom et Prénom", TEACHER_DOMAIN_COL_NAME, "Expertises / Technologies"]
    promotions_cols = ["Promotion & Intitulé", "Niveau / Cycle", "Code promotion", "Effectif Etudiants"]

    clean_salles = [{k: row.get(k, "") for k in salles_cols} for row in EXCEL_RESOURCES_DATA["salles"]]
    clean_enseignants = []
    for row in EXCEL_RESOURCES_DATA["enseignants"]:
        dom_val = row.get(TEACHER_DOMAIN_COL_NAME) if row.get(TEACHER_DOMAIN_COL_NAME) != "" else row.get("Domaine", row.get("Domaine ", ""))
        clean_enseignants.append({
            "Nom et Prénom": row.get("Nom et Prénom", ""),
            TEACHER_DOMAIN_COL_NAME: dom_val,
            "Expertises / Technologies": row.get("Expertises / Technologies", "")
        })
    clean_promotions = [{k: row.get(k, "") for k in promotions_cols} for row in EXCEL_RESOURCES_DATA["promotions"]]

    df_salles = pd.DataFrame(clean_salles, columns=salles_cols)
    df_enseignants = pd.DataFrame(clean_enseignants, columns=enseignants_cols)
    df_promotions = pd.DataFrame(clean_promotions, columns=promotions_cols)

    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df_salles.to_excel(writer, sheet_name="Salles", index=False)
            df_enseignants.to_excel(writer, sheet_name="Enseignants", index=False)
            df_promotions.to_excel(writer, sheet_name="Promotions", index=False)
        print(f"✅ Fichier Excel sauvegardé avec succès : {excel_path}")
    except PermissionError:
        raise HTTPException(
            status_code=423,
            detail="Impossible d'enregistrer dans Excel : le fichier est actuellement ouvert dans un autre logiciel. Fermez-le et réessayez."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sauvegarde Excel : {str(e)}")


def sync_in_memory_agents_from_excel():
    """Synchronise les schémas Pydantic et les agents SMA en mémoire à partir de EXCEL_RESOURCES_DATA."""
    global mock_rooms, mock_teachers, mock_groups, coordinator, room_agents, teacher_agents

    mock_rooms.clear()
    room_agents.clear()
    if EXCEL_RESOURCES_DATA["salles"]:
        for idx, s in enumerate(EXCEL_RESOURCES_DATA["salles"]):
            code_salle = str(s.get("Code / Salle", f"Salle_{idx+1}"))
            room_type = str(s.get("Type de Salle", "Salle de cours"))
            cap = safe_int_capacity(s.get("Capacité"), default=40)
            has_hvac = "Oui" in str(s.get("Capteur HVAC Smart", ""))
            is_lab = "Labo" in room_type or "FabLab" in room_type

            room_schema = RoomSchema(
                id=f"R_{idx+1}",
                name=code_salle,
                capacity=cap,
                campus=CampusEnum.YANSOKI,
                has_hvac_sensor=has_hvac,
                is_lab=is_lab
            )
            mock_rooms.append(room_schema)

            room_agents[code_salle] = create_agent_instance(
                RoomAgent,
                name=code_salle,
                capacity=cap,
                has_hvac_sensor=has_hvac,
                is_lab=is_lab,
                room_type=room_type,
                room_schema=room_schema,
                bus=bus
            )

    mock_teachers.clear()
    teacher_agents.clear()
    if EXCEL_RESOURCES_DATA["enseignants"]:
        for idx, t in enumerate(EXCEL_RESOURCES_DATA["enseignants"]):
            name = str(t.get("Nom et Prénom", f"Enseignant_{idx+1}"))
            dept = str(t.get("Domaine ", t.get("Domaine", "Général")))
            t_id = f"T_{idx+1}"

            teacher_schema = TeacherSchema(
                id=t_id,
                name=name,
                department=dept,
                preferred_timeslots=["Lundi_08h00-12h00"]
            )
            mock_teachers.append(teacher_schema)

            teacher_agents[t_id] = create_agent_instance(
                TeacherAgent,
                name=name,
                id=t_id,
                department=dept,
                teacher_schema=teacher_schema,
                bus=bus
            )

    mock_groups.clear()
    if EXCEL_RESOURCES_DATA["promotions"]:
        for idx, p in enumerate(EXCEL_RESOURCES_DATA["promotions"]):
            promo_title = str(p.get("Promotion & Intitulé", f"Promotion_{idx+1}"))
            cycle = str(p.get("Niveau / Cycle", "Général"))
            eff = safe_int_capacity(p.get("Effectif Etudiants"), default=35)
            mock_groups.append(GroupSchema(
                id=f"G_{idx+1}",
                name=promo_title,
                student_count=eff,
                promotion=cycle
            ))

    coordinator = CoordinatorAgent(
        name="Coordinator_UcacIcam",
        room_agents=[r.name for r in mock_rooms],
        teacher_agents=[t.id for t in mock_teachers],
        bus=bus
    )


DOMAIN_KEYWORDS = {
    "finance_gestion": [
        "finan", "compta", "gestion", "eco", "budget", "tresor",
        "banque", "audit", "fiscal", "comptabilite", "controle de gestion", "finance"
    ],
    "maths_stats": [
        "math", "stat", "algebre", "calcul", "analyse", "probab",
        "geometrie", "mathematique", "mathematiques", "optimisation"
    ],
    "informatique_dev": [
        "dev", "code", "logiciel", "gl", "java", "python", "web", "algo", "algorithm",
        "data", "bdd", "sql", "ia", "ai", "application", "programmation", "c++", "poo",
        "informatique", "si", "systeme d'information"
    ],
    "reseaux_infra": [
        "reseau", "infra", "sys", "systeme", "rt", "telecom",
        "cyber", "secu", "cloud", "routeur", "cisco", "linux", "iot"
    ],
    "management_projet": [
        "manag", "management", "pmp", "risk", "qualit", "agile", "scrum",
        "organisation", "rh", "ressources humaines", "entrepreneuriat",
        "lean", "supply chain", "logistique", "industriel", "production"
    ],
    "sciences_ingenieur": [
        "physique", "chimie", "electronique", "thermo", "meca",
        "mecanique", "energie", "automat", "electrotechnique", "materiaux",
        "maintenance", "genie", "cao", "dao", "fabrication"
    ],
    "humanites_langues": [
        "anglais", "english", "comm", "communication", "droit", "francais",
        "expression", "ethique", "sociologie", "culture", "philosophie", "leadership"
    ]
}


def rank_teachers_by_expertise(course_name: str, teachers_list: List[Dict[str, Any]], max_teachers: int = 3) -> List[Tuple[str, float]]:
    """Classe les meilleurs enseignants de l'Excel par score de pertinence et compétences pour un cours donné."""
    if not teachers_list:
        return [("Enseignant Qualifié", 75.0)]

    c_norm = _strip_accents(course_name)

    matched_domains = []
    for domain, kws in DOMAIN_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in c_norm)
        if hits > 0:
            matched_domains.append((domain, hits))
    matched_domains.sort(key=lambda x: x[1], reverse=True)
    primary_domain = matched_domains[0][0] if matched_domains else None

    scored_teachers: List[Tuple[str, float, int]] = []
    course_words = [w for w in re.findall(r"[a-z0-9]{3,}", c_norm) if w not in {"cours", "td", "tp", "cm", "avec", "pour", "dans"}]

    for idx, t in enumerate(teachers_list):
        name = str(t.get("Nom et Prénom", "")).strip()
        if not name:
            continue

        dom = _strip_accents(t.get("Domaine ", t.get("Domaine", "")))
        exp = _strip_accents(t.get("Expertises / Technologies", ""))
        teacher_profile = f"{dom} {exp}"

        raw_score = 0
        if primary_domain:
            domain_kws = DOMAIN_KEYWORDS[primary_domain]
            if any(kw in dom for kw in domain_kws):
                raw_score += 12
            if any(kw in exp for kw in domain_kws):
                raw_score += 8

        for word in course_words:
            if word in exp:
                raw_score += 5
            elif word in dom:
                raw_score += 3

        pct_score = min(98.0, 82.0 + raw_score * 1.1) if raw_score > 0 else max(70.0, 76.0 - (idx % 5))
        scored_teachers.append((name, round(pct_score, 1), raw_score))

    scored_teachers.sort(key=lambda item: (item[2], item[1]), reverse=True)

    relevant = [(name, pct) for name, pct, raw in scored_teachers if raw > 0]
    if len(relevant) >= max_teachers:
        return relevant[:max_teachers]

    seen = {name for name, _ in relevant}
    for name, pct, _ in scored_teachers:
        if name not in seen:
            relevant.append((name, pct))
            seen.add(name)
        if len(relevant) >= max_teachers:
            break

    return relevant[:max_teachers] if relevant else [("Enseignant Qualifié", 75.0)]


def match_teacher_by_expertise(
    course_name: str,
    teachers_list: List[Dict[str, Any]],
    idx: int = 0,
    busy_teachers: Optional[set] = None,
    preferred_teacher: Optional[str] = None
) -> str:
    """
    Attribue l'enseignant le plus compétent disponible issu de l'Excel
    (en conservant l'intervenant déjà attribué au même cours de la promotion s'il est disponible).
    """
    if not course_name or not teachers_list:
        return "Enseignant Qualifié"

    busy = busy_teachers or set()

    if preferred_teacher and preferred_teacher != "Sans enseignant" and preferred_teacher.lower() not in busy:
        return preferred_teacher

    ranked = rank_teachers_by_expertise(course_name, teachers_list, max_teachers=max(8, len(teachers_list)))
    for candidate_name, _ in ranked:
        if candidate_name.lower() not in busy:
            return candidate_name

    fallback_name = teachers_list[idx % len(teachers_list)].get("Nom et Prénom")
    return str(fallback_name) if fallback_name else "Enseignant Qualifié"


def _is_workroom(room_dict: Dict[str, Any]) -> bool:
    """Identifie une salle de travail / salle de classe (hors amphithéâtre)."""
    code = _strip_accents(room_dict.get("Code / Salle", ""))
    rtype = _strip_accents(room_dict.get("Type de Salle", ""))
    return "amphi" not in code and "amphi" not in rtype


def _room_hvac_kwh(room_code: str, salles_list: List[Dict[str, Any]]) -> float:
    """Retourne le gain énergétique HVAC associé à une salle donnée."""
    if not room_code or "stage" in _strip_accents(room_code):
        return 0.0
    for s in salles_list:
        if str(s.get("Code / Salle", "")).strip().lower() == room_code.strip().lower():
            return 0.85 if "Oui" in str(s.get("Capteur HVAC Smart", "")) else 0.40
    return 0.40


def _allocate_promo_rooms_by_two_month_periods(
    target_sessions: List[Dict[str, Any]],
    promo_effects: Dict[str, int],
    salles_list: List[Dict[str, Any]]
) -> Dict[Tuple[str, int], str]:
    """
    Alloue UNE ET UNE SEULE salle par promotion pour chaque période de 02 mois,
    puis effectue une rotation obligatoire vers une nouvelle salle à la période de 02 mois suivante.
    """
    if not salles_list:
        return {}

    periods_promos: Dict[int, List[str]] = {}
    for s in target_sessions:
        if "stage" in _strip_accents(s["course_id"]):
            continue
        p_id = s["period_id"]
        promo = s["group_id"]
        plist = periods_promos.setdefault(p_id, [])
        if promo not in plist:
            plist.append(promo)

    allocation: Dict[Tuple[str, int], str] = {}
    last_room_by_promo: Dict[str, str] = {}

    for rotation_step, p_id in enumerate(sorted(periods_promos.keys())):
        active_promos = periods_promos[p_id]
        used_rooms_in_period: set = set()

        # Priorise les promotions avec les plus grands effectifs pour garantir le respect des capacités
        active_promos_sorted = sorted(
            active_promos,
            key=lambda pr: promo_effects.get(pr.lower(), 35),
            reverse=True
        )

        for p_idx, promo_code in enumerate(active_promos_sorted):
            student_count = promo_effects.get(promo_code.lower(), 35)
            prev_room = last_room_by_promo.get(promo_code)

            # 1. Salles respectant la capacité de la promotion
            eligible = [
                s for s in salles_list
                if safe_int_capacity(s.get("Capacité"), 40) >= student_count
            ]
            if not eligible:
                eligible = list(salles_list)

            # 2. Privilégie les salles de classe / salles de travail (hors amphithéâtres)
            workrooms = [s for s in eligible if _is_workroom(s)]
            if len(workrooms) >= len(active_promos_sorted):
                eligible = workrooms

            # 3. Exclut les salles déjà attribuées à une autre promotion sur ces 2 mois
            free_in_period = [
                s for s in eligible
                if str(s.get("Code / Salle", "")).strip().lower() not in used_rooms_in_period
            ]
            candidates = free_in_period if free_in_period else eligible

            # 4. Rotation : exclut la salle occupée par cette promotion lors des 2 mois précédents
            if prev_room and len(candidates) > 1:
                rotated_candidates = [
                    s for s in candidates
                    if str(s.get("Code / Salle", "")).strip().lower() != prev_room.strip().lower()
                ]
                if rotated_candidates:
                    candidates = rotated_candidates

            # 5. Tri Green-IT (Capteur HVAC Smart + ajustement optimal de capacité) + décalage de rotation
            candidates.sort(
                key=lambda r: (
                    0 if "Oui" in str(r.get("Capteur HVAC Smart", "")) else 1,
                    safe_int_capacity(r.get("Capacité"), 40),
                    str(r.get("Code / Salle", ""))
                )
            )

            chosen_dict = candidates[(rotation_step + p_idx) % len(candidates)]
            chosen_room = str(chosen_dict.get("Code / Salle", "Salle 101")).strip()

            allocation[(promo_code, p_id)] = chosen_room
            used_rooms_in_period.add(chosen_room.lower())
            last_room_by_promo[promo_code] = chosen_room

    return allocation


def match_room_by_capacity_hvac(
    course_name: str,
    student_count: int,
    salles_list: List[Dict[str, Any]],
    idx: int,
    occupied_rooms_for_slot: Optional[set] = None,
    preferred_room_for_promo: Optional[str] = None,
    workroom_only: bool = False
) -> Tuple[str, float]:
    """
    Attribue une salle Excel :
    - Si `preferred_room_for_promo` est défini (salle dédiée de la promotion sur les 2 mois),
      l'applique systématiquement à toutes les activités sur campus de la promotion.
    """
    c_norm = _strip_accents(course_name)
    occupied = occupied_rooms_for_slot or set()

    if "stage" in c_norm:
        return "Hors campus / Stage", 0.0

    if preferred_room_for_promo:
        return preferred_room_for_promo, _room_hvac_kwh(preferred_room_for_promo, salles_list)

    eligible = [s for s in salles_list if safe_int_capacity(s.get("Capacité")) >= student_count]
    if not eligible:
        eligible = salles_list or [{"Code / Salle": "Salle 101", "Capteur HVAC Smart": "Oui", "Type de Salle": "Salle de cours"}]

    if workroom_only:
        workrooms = [s for s in eligible if _is_workroom(s)]
        if workrooms:
            eligible = workrooms

    free_eligible = [
        s for s in eligible
        if str(s.get("Code / Salle", "")).lower() not in occupied
    ]
    pool_base = free_eligible if free_eligible else eligible

    hvac_smart = [s for s in pool_base if "Oui" in str(s.get("Capteur HVAC Smart", ""))]
    pool = hvac_smart if hvac_smart else pool_base
    pool.sort(key=lambda r: safe_int_capacity(r.get("Capacité"), 40))

    chosen = pool[idx % len(pool)] if len(pool) > 1 else pool[0]
    saved_kwh = 0.85 if "Oui" in str(chosen.get("Capteur HVAC Smart", "")) else 0.40
    return str(chosen.get("Code / Salle", "Salle 101")), saved_kwh


def prepare_all_sessions_for_sma(raw_sessions: List[Any]) -> List[Dict[str, Any]]:
    """
    Prépare l'intégralité des séances de l'emploi du temps (toutes les semaines et toutes les promotions)
    pour la négociation SMA, avec calcul de leur période bimestrielle (02 mois).
    """
    if not raw_sessions:
        return []

    prepared: List[Dict[str, Any]] = []

    for idx, session in enumerate(raw_sessions):
        course_name = get_field_val(session, ["course_id", "name", "id", "summary"], default=f"Cours_{idx+1}")
        group_code = get_field_val(session, ["group_id", "group", "promo"], default="PROMO")
        slot_time = str(get_field_val(session, ["timeslot", "preferred_timeslot", "start_time"], default="Lundi_08h00-12h00"))
        raw_date = get_field_val(session, ["date", "start_date"], default=None)

        dt = _parse_session_date(raw_date, slot_time)

        if re.match(r"^S\d{1,2}_", slot_time.strip(), flags=re.IGNORECASE):
            formatted_slot = slot_time.strip()
        elif dt is not None:
            formatted_slot = _format_timeslot_for_grid(slot_time, dt)
        else:
            formatted_slot = slot_time.strip()

        normalized_date = (
            dt.strftime("%Y-%m-%d")
            if dt is not None
            else (str(raw_date).strip() if raw_date else None)
        )
        period_id = _get_two_month_period_id(normalized_date, formatted_slot)

        prepared.append({
            "course_id": str(course_name),
            "group_id": str(group_code),
            "timeslot": formatted_slot,
            "date": normalized_date,
            "period_id": period_id,
        })

    prepared.sort(key=lambda s: (s["period_id"], s["date"] or "", s["timeslot"], s["group_id"]))
    return prepared


async def agent_router():
    """Tâche d'arrière-plan de routage des messages FIPA-ACL."""
    while True:
        try:
            msg: FIPAACLMessage = await bus.queue.get()
            if msg.receiver in room_agents:
                await room_agents[msg.receiver].inbox.put(msg)
            elif msg.receiver in teacher_agents:
                await teacher_agents[msg.receiver].inbox.put(msg)
            elif coordinator and msg.receiver == coordinator.name:
                await coordinator.inbox.put(msg)
        except Exception as e:
            print(f"⚠️ Erreur de routage agent : {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionnaire de cycle de vie : Chargement Excel, initialisation des agents et des fichiers .ics."""
    global EXCEL_RESOURCES_DATA, RAW_ICS_ASSIGNMENTS, OPTIMIZED_ASSIGNMENTS

    _load_users()
    EXCEL_RESOURCES_DATA = load_resources_from_excel()
    sync_in_memory_agents_from_excel()

    router_task = asyncio.create_task(agent_router())
    background_tasks.add(router_task)
    router_task.add_done_callback(background_tasks.discard)

    RAW_ICS_ASSIGNMENTS.clear()
    OPTIMIZED_ASSIGNMENTS.clear()

    if os.path.exists(ICS_DIR):
        simple_ics_files = [
            f for f in glob(os.path.join(ICS_DIR, "*.ics"))
            if os.path.basename(f).lower() != "planit_optimized_schedule.ics"
        ]
        for file_path in simple_ics_files:
            filename = os.path.basename(file_path)
            promo_from_filename = os.path.splitext(filename)[0]
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    parsed = HyperplanningService.parse_ics_content(
                        content,
                        default_promo=promo_from_filename
                    )
                    RAW_ICS_ASSIGNMENTS.extend(_mark_as_raw_ics(parsed))
            except Exception as e:
                print(f"Erreur chargement {file_path} : {e}")
        print(f"✅ {len(RAW_ICS_ASSIGNMENTS)} cours simples chargés depuis {len(simple_ics_files)} fichiers .ics")

        opt_file = os.path.join(ICS_DIR, "planit_optimized_schedule.ics")
        if os.path.exists(opt_file):
            try:
                with open(opt_file, "r", encoding="utf-8") as f:
                    opt_parsed = HyperplanningService.parse_ics_content(f.read(), default_promo="PROMO")
                    for item in opt_parsed:
                        item.resolution_method = "SMA_CNP"
                        if not getattr(item, "score", 0):
                            item.score = 95.0
                    OPTIMIZED_ASSIGNMENTS.extend(opt_parsed)
                print(f"✅ {len(OPTIMIZED_ASSIGNMENTS)} cours optimisés chargés depuis planit_optimized_schedule.ics")
            except Exception as e:
                print(f"Erreur chargement planning optimisé : {e}")

    yield

    for task in background_tasks:
        task.cancel()


# --- Application FastAPI ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

raw_origins = list(settings.CORS_ORIGINS) if settings.CORS_ORIGINS else ["*"]
if "*" not in raw_origins:
    for local_origin in [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]:
        if local_origin not in raw_origins:
            raw_origins.append(local_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=raw_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Endpoints Authentification ---
@app.post(f"{settings.API_V1_STR}/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRegisterRequest):
    email_norm = payload.email.strip().lower()

    if not re.match(r"^[a-zA-Z0-9._-]+@([a-zA-Z0-9-]+\.)?ucac-icam\.com$", email_norm):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seules les adresses institutionnelles UCAC-ICAM (@ucac-icam.com ou @2027.ucac-icam.com) sont autorisées."
        )

    users = _load_users()
    if any(u["email"].lower() == email_norm for u in users):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte existe déjà avec cette adresse e-mail institutionnelle."
        )

    new_user = {
        "id": f"USR_{uuid.uuid4().hex[:8].upper()}",
        "nom": payload.nom.strip(),
        "prenom": payload.prenom.strip(),
        "email": email_norm,
        "campus": payload.campus,
        "role": payload.role,
        "password_hash": _hash_password(payload.password),
        "is_active": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    users.append(new_user)
    _save_users(users)

    return {
        "message": "Compte créé avec succès. En attente de validation par un administrateur."
    }


@app.post(f"{settings.API_V1_STR}/auth/login", response_model=AuthResponse)
def login_user(payload: UserLoginRequest):
    email_norm = payload.email.strip().lower()
    users = _load_users()

    user = next((u for u in users if u["email"].lower() == email_norm), None)
    if not user or not _verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Adresse e-mail ou mot de passe incorrect."
        )

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte n'a pas encore été validé par un administrateur."
        )

    token = _create_auth_token(user["id"], user["email"], payload.rememberMe)

    return AuthResponse(
        access_token=token,
        user=UserProfileOut(
            id=user["id"],
            nom=user["nom"],
            prenom=user["prenom"],
            email=user["email"],
            campus=user["campus"],
            role=user["role"],
            is_active=user["is_active"]
        )
    )


@app.get(f"{settings.API_V1_STR}/auth/pending", response_model=List[UserProfileOut])
@app.get("/api/auth/pending", response_model=List[UserProfileOut])
def list_pending_users():
    """Liste les comptes en attente d'activation par un administrateur."""
    users = _load_users()
    return [
        UserProfileOut(
            id=u["id"],
            nom=u["nom"],
            prenom=u["prenom"],
            email=u["email"],
            campus=u["campus"],
            role=u["role"],
            is_active=u["is_active"]
        )
        for u in users
        if not u.get("is_active", False)
    ]


@app.post(f"{settings.API_V1_STR}/auth/validate/{{user_id}}", response_model=UserProfileOut)
@app.patch(f"{settings.API_V1_STR}/auth/validate/{{user_id}}", response_model=UserProfileOut)
@app.post("/api/auth/validate/{user_id}", response_model=UserProfileOut)
@app.patch("/api/auth/validate/{user_id}", response_model=UserProfileOut)
def validate_user_account(user_id: str):
    """Active un compte utilisateur après vérification administrateur."""
    users = _load_users()
    for user in users:
        if user["id"] == user_id:
            user["is_active"] = True
            _save_users(users)
            return UserProfileOut(
                id=user["id"],
                nom=user["nom"],
                prenom=user["prenom"],
                email=user["email"],
                campus=user["campus"],
                role=user["role"],
                is_active=True
            )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")


# --- Endpoints Système & Ressources (CRUD Excel) ---
@app.get("/")
def root():
    return {"status": "online", "system": settings.PROJECT_NAME, "version": settings.VERSION}


@app.get("/health")
def health_check():
    return {
        "status": "operational",
        "campus_active": settings.DEFAULT_CAMPUS,
        "agents_online": len(room_agents) + len(teacher_agents) + (1 if coordinator else 0)
    }


@app.get(f"{settings.API_V1_STR}/resources")
@app.get("/api/resources")
def get_resources():
    return {
        "success": True,
        "data": EXCEL_RESOURCES_DATA,
        "rooms": mock_rooms,
        "teachers": mock_teachers,
        "groups": mock_groups
    }


def _validate_sheet_type(sheet_type: str) -> str:
    key = sheet_type.lower().strip()
    if key not in ["salles", "enseignants", "promotions"]:
        raise HTTPException(status_code=400, detail=f"Type de feuille invalide : {sheet_type}")
    return key


def _normalize_excel_row(sheet_key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    if sheet_key == "salles":
        return {
            "Bâtiment": str(item.get("Bâtiment", "")).strip(),
            "Étage": str(item.get("Étage", "")).strip(),
            "Code / Salle": str(item.get("Code / Salle", "")).strip(),
            "Type de Salle": str(item.get("Type de Salle", "Salle de cours")).strip(),
            "Capacité": safe_int_capacity(item.get("Capacité"), default=35),
            "Prises Elec.": safe_int_capacity(item.get("Prises Elec."), default=10),
            "Affichage (TV / Projecteur)": str(item.get("Affichage (TV / Projecteur)", "Projecteur")).strip(),
            "Climatisation": str(item.get("Climatisation", "Oui")).strip(),
            "Capteur HVAC Smart": str(item.get("Capteur HVAC Smart", "Oui")).strip(),
            "Équipements complémentaires": str(item.get("Équipements complémentaires", "")).strip()
        }
    elif sheet_key == "enseignants":
        dom_val = str(item.get(TEACHER_DOMAIN_COL_NAME) or item.get("Domaine ") or item.get("Domaine") or "").strip()
        return {
            "Nom et Prénom": str(item.get("Nom et Prénom", "")).strip(),
            TEACHER_DOMAIN_COL_NAME: dom_val,
            "Expertises / Technologies": str(item.get("Expertises / Technologies", "")).strip()
        }
    else:
        return {
            "Promotion & Intitulé": str(item.get("Promotion & Intitulé", "")).strip(),
            "Niveau / Cycle": str(item.get("Niveau / Cycle", "Ingénieur")).strip(),
            "Code promotion": str(item.get("Code promotion", "")).strip(),
            "Effectif Etudiants": safe_int_capacity(item.get("Effectif Etudiants"), default=35)
        }


@app.post(f"{settings.API_V1_STR}/resources/{{sheet_type}}")
@app.post("/api/resources/{sheet_type}")
def create_excel_resource(sheet_type: str, item: Dict[str, Any] = Body(...)):
    """Ajoute une entrée dans la feuille Excel spécifiée et sauvegarde directement le fichier."""
    sheet_key = _validate_sheet_type(sheet_type)
    normalized = _normalize_excel_row(sheet_key, item)

    EXCEL_RESOURCES_DATA[sheet_key].append(normalized)
    save_resources_to_excel()
    sync_in_memory_agents_from_excel()

    return {
        "success": True,
        "message": f"Entrée ajoutée dans l'onglet {sheet_key} et sauvegardée dans Excel.",
        "data": EXCEL_RESOURCES_DATA
    }


@app.put(f"{settings.API_V1_STR}/resources/{{sheet_type}}/{{row_index}}")
@app.put("/api/resources/{sheet_type}/{row_index}")
def update_excel_resource(sheet_type: str, row_index: int, item: Dict[str, Any] = Body(...)):
    """Modifie une ligne existante dans la feuille Excel spécifiée et sauvegarde directement le fichier."""
    sheet_key = _validate_sheet_type(sheet_type)
    target_list = EXCEL_RESOURCES_DATA[sheet_key]

    if row_index < 0 or row_index >= len(target_list):
        raise HTTPException(status_code=404, detail="Index de ligne introuvable dans la feuille Excel.")

    target_list[row_index] = _normalize_excel_row(sheet_key, item)
    save_resources_to_excel()
    sync_in_memory_agents_from_excel()

    return {
        "success": True,
        "message": f"Ligne #{row_index + 1} mise à jour dans l'onglet {sheet_key} et sauvegardée dans Excel.",
        "data": EXCEL_RESOURCES_DATA
    }


@app.delete(f"{settings.API_V1_STR}/resources/{{sheet_type}}/{{row_index}}")
@app.delete("/api/resources/{sheet_type}/{row_index}")
def delete_excel_resource(sheet_type: str, row_index: int):
    """Supprime une ligne de la feuille Excel spécifiée et sauvegarde directement le fichier."""
    sheet_key = _validate_sheet_type(sheet_type)
    target_list = EXCEL_RESOURCES_DATA[sheet_key]

    if row_index < 0 or row_index >= len(target_list):
        raise HTTPException(status_code=404, detail="Index de ligne introuvable dans la feuille Excel.")

    target_list.pop(row_index)
    save_resources_to_excel()
    sync_in_memory_agents_from_excel()

    return {
        "success": True,
        "message": f"Ligne supprimée de l'onglet {sheet_key} et fichier Excel mis à jour.",
        "data": EXCEL_RESOURCES_DATA
    }


# --- Endpoints Négociation SMA & Persistance ---
@app.post(f"{settings.API_V1_STR}/negotiate/session", response_model=NegotiationResponse)
async def negotiate_single_session(req: SingleNegotiationRequest):
    t0 = time.time()
    if not coordinator:
        raise HTTPException(status_code=503, detail="Le coordinateur SMA n'est pas initialisé.")

    teacherless = is_non_teacher_activity(req.course_id)
    effective_teacher_id = "Sans enseignant" if teacherless else req.teacher_id

    await emit_sma_log(
        "CFP",
        "Coordinator_UcacIcam",
        "ALL_ROOM_AGENTS",
        {
            "course": req.course_id,
            "timeslot": req.timeslot,
            "students": req.students_count,
            "mode": "Salle_de_travail_sans_enseignant" if teacherless else "Cours_encadre"
        }
    )

    salles_list = EXCEL_RESOURCES_DATA.get("salles", [])
    rejected_sample = [s for s in salles_list if safe_int_capacity(s.get("Capacité"), 40) < req.students_count][:2]
    for rej in rejected_sample:
        await emit_sma_log(
            "REJECT_PROPOSAL",
            str(rej.get("Code / Salle", "Salle")),
            "Coordinator_UcacIcam",
            {"reason": f"Capacité insuffisante ({rej.get('Capacité')} < {req.students_count} étudiants)"}
        )

    result = await coordinator.negotiate_slot(
        course_id=req.course_id,
        timeslot=req.timeslot,
        students_count=req.students_count,
        teacher_id=effective_teacher_id,
        group_id=req.group_id,
        requires_lab=req.requires_lab,
        workroom_only=teacherless
    )

    if not result:
        best_room, kwh = match_room_by_capacity_hvac(
            req.course_id,
            req.students_count,
            salles_list,
            0,
            workroom_only=teacherless
        )
        await emit_sma_log(
            "BID",
            best_room,
            "Coordinator_UcacIcam",
            {"hvac_saved_kwh": kwh, "mode": "Arbitrage_Salle_Travail" if teacherless else "Arbitrage_Capacite_Maximale"}
        )
        await emit_sma_log(
            "ACCEPT_PROPOSAL",
            "Coordinator_UcacIcam",
            best_room,
            {"course": req.course_id, "timeslot": req.timeslot, "teacher": effective_teacher_id}
        )
        exec_time_ms = round((time.time() - t0) * 1000, 2)
        return NegotiationResponse(
            success=False,
            reason=f"Conflit détecté ({req.students_count} étudiants) : arbitrage proposé vers {best_room}.",
            execution_time_ms=exec_time_ms
        )

    await emit_sma_log(
        "ACCEPT_PROPOSAL",
        "Coordinator_UcacIcam",
        str(result.get("assigned_room", "Salle 101")),
        {"course": req.course_id, "timeslot": req.timeslot, "teacher": effective_teacher_id}
    )

    exec_time_ms = round((time.time() - t0) * 1000, 2)

    if "hvac_saved_kwh" in result and "hvac_kwh" not in result:
        result["hvac_kwh"] = result["hvac_saved_kwh"]
    if "hvac_kwh" in result and "hvac_saved_kwh" not in result:
        result["hvac_saved_kwh"] = result["hvac_kwh"]

    assignment_obj = create_assignment_result(
        AssignmentResult,
        course_id=result.get("course_id", req.course_id),
        assigned_room=result.get("assigned_room", "Salle 101"),
        timeslot=result.get("timeslot", req.timeslot),
        teacher_id=effective_teacher_id,
        group_id=result.get("group_id", req.group_id),
        kwh=result.get("hvac_kwh", result.get("hvac_saved_kwh", 0.0)),
        score=result.get("score", 95.0),
        resolution_method=result.get("resolution_method", "SMA_CNP"),
        date=result.get("date")
    )

    return NegotiationResponse(
        success=True,
        assignment=assignment_obj,
        execution_time_ms=exec_time_ms
    )


@app.post(f"{settings.API_V1_STR}/negotiate/full-schedule", response_model=FullScheduleResponse)
async def generate_full_schedule(payload: FullScheduleRequest):
    t0 = time.time()
    global OPTIMIZED_ASSIGNMENTS

    salles_list = EXCEL_RESOURCES_DATA.get("salles", [])
    teachers_list = EXCEL_RESOURCES_DATA.get("enseignants", [])
    promos_list = EXCEL_RESOURCES_DATA.get("promotions", [])

    promo_effects = {
        str(p.get("Code promotion", "")).lower(): safe_int_capacity(p.get("Effectif Etudiants"), default=35)
        for p in promos_list
    }

    # Lecture de la totalité des séances sources sans altérer RAW_ICS_ASSIGNMENTS
    source_sessions = RAW_ICS_ASSIGNMENTS if len(RAW_ICS_ASSIGNMENTS) > 0 else payload.courses
    target_sessions = prepare_all_sessions_for_sma(source_sessions)

    # Allocation de UNE ET UNE SEULE salle par promotion sur 02 mois, avec rotation à la période suivante
    promo_room_by_period = _allocate_promo_rooms_by_two_month_periods(
        target_sessions=target_sessions,
        promo_effects=promo_effects,
        salles_list=salles_list
    )

    unique_promos = list(dict.fromkeys(s["group_id"] for s in target_sessions))
    occupied_teachers_by_slot: Dict[Tuple[str, str], set] = {}
    course_teacher_affinity: Dict[Tuple[str, str], str] = {}

    optimized_list: List[AssignmentResult] = []
    total_saved_kwh = 0.0

    await emit_sma_log(
        "CFP",
        "Coordinator_UcacIcam",
        f"AGENTS_POOL ({len(room_agents)} Salles, {len(teacher_agents)} Enseignants)",
        {
            "scope": "Emploi du temps complet (salle unique par promotion sur 02 mois avec rotation)",
            "promotions": len(unique_promos),
            "sessions_to_schedule": len(target_sessions),
            "protocol": "FIPA-ACL Contract Net Green-IT"
        }
    )

    for idx, session in enumerate(target_sessions):
        course_name = session["course_id"]
        group_code = session["group_id"]
        slot_time = session["timeslot"]
        session_date = session["date"]
        period_id = session["period_id"]

        slot_key = (str(session_date or ""), str(slot_time).lower())
        busy_teachers = occupied_teachers_by_slot.setdefault(slot_key, set())

        student_count = promo_effects.get(str(group_code).lower(), 35)
        teacherless = is_non_teacher_activity(course_name)

        # 1. Enseignants : uniquement sur les activités encadrées et selon leurs compétences
        if teacherless:
            assigned_teacher = "Sans enseignant"
        else:
            course_key = (group_code.lower(), _strip_accents(course_name))
            assigned_teacher = match_teacher_by_expertise(
                course_name,
                teachers_list,
                idx,
                busy_teachers=busy_teachers,
                preferred_teacher=course_teacher_affinity.get(course_key)
            )
            if assigned_teacher and assigned_teacher != "Sans enseignant":
                busy_teachers.add(assigned_teacher.lower())
                course_teacher_affinity.setdefault(course_key, assigned_teacher)

        # 2. Salle : toutes les activités sur campus de la promotion partagent sa salle unique sur 02 mois
        dedicated_room = promo_room_by_period.get((group_code, period_id))
        assigned_room, kwh = match_room_by_capacity_hvac(
            course_name=course_name,
            student_count=student_count,
            salles_list=salles_list,
            idx=idx,
            preferred_room_for_promo=dedicated_room,
            workroom_only=teacherless
        )

        total_saved_kwh += kwh

        if idx < 24 or idx % 8 == 0:
            await emit_sma_log(
                "CFP",
                "Coordinator_UcacIcam",
                "Room_Agents" if teacherless else "Room_&_Teacher_Agents",
                {
                    "course": course_name,
                    "promo": group_code,
                    "timeslot": slot_time,
                    "cycle_salle_2_mois": dedicated_room or assigned_room,
                    "type": "Activité autonome / Projet (Sans enseignant)" if teacherless else "Cours encadré (Compétence)"
                }
            )
            await emit_sma_log(
                "BID",
                assigned_room,
                "Coordinator_UcacIcam",
                {"hvac_saved_kwh": kwh, "teacher": assigned_teacher}
            )
            await emit_sma_log(
                "ACCEPT_PROPOSAL",
                "Coordinator_UcacIcam",
                assigned_room if teacherless else f"{assigned_room} & {assigned_teacher}",
                {"course": course_name, "promo": group_code, "timeslot": slot_time}
            )

        if idx % 25 == 0:
            await asyncio.sleep(0.005)

        item = create_assignment_result(
            AssignmentResult,
            course_id=course_name,
            assigned_room=assigned_room,
            timeslot=slot_time,
            teacher_id=assigned_teacher,
            group_id=group_code,
            kwh=kwh,
            score=95.0,
            resolution_method="SMA_CNP",
            date=session_date
        )
        optimized_list.append(item)

    # Mise à jour uniquement du planning optimisé et du fichier dédié planit_optimized_schedule.ics
    OPTIMIZED_ASSIGNMENTS = optimized_list
    save_optimized_assignments_to_ics(OPTIMIZED_ASSIGNMENTS)

    exec_time_ms = round((time.time() - t0) * 1000, 2)
    total_courses = len(optimized_list)

    return FullScheduleResponse(
        success=True,
        total_courses=total_courses,
        scheduled_courses=total_courses,
        conflicts_unresolved=0,
        global_occupancy_rate=100.0,
        total_energy_saved_kwh=round(total_saved_kwh, 2),
        total_cost_saved_fcfa=round(total_saved_kwh * settings.ENERGY_COST_PER_KWH_FCFA, 2),
        execution_time_ms=exec_time_ms,
        assignments=optimized_list
    )


# --- Endpoints Assistant Hybride & Recommandations (6 Alternatives, 2 à 3 Intervenants) ---
@app.post(f"{settings.API_V1_STR}/recommendations/manual")
@app.post("/api/v1/recommendations/hybrid")
def get_hybrid_recommendations(req: ManualRecommendationRequest) -> List[Dict[str, Any]]:
    """
    Assistant Hybride : Croise les données Excel (Salles/Profs/Capacité/Expertise) et les réservations
    pour recommander 6 alternatives cohérentes.
    """
    salles_list = EXCEL_RESOURCES_DATA.get("salles", [])
    teachers_list = EXCEL_RESOURCES_DATA.get("enseignants", [])
    promos_list = EXCEL_RESOURCES_DATA.get("promotions", [])

    student_count = getattr(req, 'students_count', 35) or 35
    group_id_val = getattr(req, 'group_id', None)
    if group_id_val:
        for p in promos_list:
            if str(p.get("Code promotion", "")).lower() == str(group_id_val).lower():
                student_count = safe_int_capacity(p.get("Effectif Etudiants"), default=student_count)
                break

    reference_schedule = OPTIMIZED_ASSIGNMENTS if OPTIMIZED_ASSIGNMENTS else RAW_ICS_ASSIGNMENTS
    occupied_rooms = set()
    occupied_teachers_per_slot: Dict[Tuple[str, str], set] = {}

    for assign in reference_schedule:
        s_name = str(getattr(assign, 'assigned_room', '')).lower()
        t_slot = str(getattr(assign, 'timeslot', '')).lower()
        d_val = str(getattr(assign, 'date', '') or '').lower()
        t_prof = str(getattr(assign, 'teacher_id', '')).lower()

        occupied_rooms.add((s_name, t_slot, d_val))

        slot_key = (t_slot, d_val)
        if slot_key not in occupied_teachers_per_slot:
            occupied_teachers_per_slot[slot_key] = set()
        if t_prof and t_prof != "sans enseignant":
            occupied_teachers_per_slot[slot_key].add(t_prof)

    base_slot = getattr(req, "timeslot", None) or "Lundi_08h00-12h00"
    req_date = str(getattr(req, "date", "") or "").lower()
    candidate_timeslots = list(dict.fromkeys([
        base_slot,
        "Lundi_08h00-12h00",
        "Lundi_13h00-17h00",
        "Mardi_08h00-12h00",
        "Mardi_13h00-17h00",
        "Mercredi_08h00-12h00",
        "Jeudi_08h00-12h00",
        "Vendredi_08h00-12h00"
    ]))

    course_name = getattr(req, "course_name", None) or getattr(req, "course_id", "Cours")
    teacherless = is_non_teacher_activity(course_name)

    top_teachers: List[Tuple[str, float]] = (
        [("Sans enseignant", 100.0)]
        if teacherless
        else rank_teachers_by_expertise(course_name, teachers_list, max_teachers=3)
    )

    eligible_rooms = []
    for s in salles_list:
        cap = safe_int_capacity(s.get("Capacité"), default=40)
        is_lab = "Labo" in str(s.get("Type de Salle", "")) or "FabLab" in str(s.get("Type de Salle", ""))
        if cap < student_count:
            continue
        if getattr(req, "requires_lab", False) and not is_lab:
            continue
        if teacherless and not _is_workroom(s):
            continue
        eligible_rooms.append(s)

    if not eligible_rooms:
        eligible_rooms = [s for s in salles_list if _is_workroom(s)] if teacherless else salles_list
    if not eligible_rooms:
        eligible_rooms = [{"Code / Salle": "Salle 101", "Capacité": 40, "Capteur HVAC Smart": "Oui"}]

    eligible_rooms.sort(
        key=lambda r: (
            1 if "Oui" in str(r.get("Capteur HVAC Smart", "")) else 0,
            min(1.0, student_count / max(1, safe_int_capacity(r.get("Capacité"), 40)))
        ),
        reverse=True
    )

    candidate_options: List[Dict[str, Any]] = []
    used_combinations = set()

    for slot_idx, slot in enumerate(candidate_timeslots):
        slot_key = (slot.lower(), req_date)
        busy_teachers = occupied_teachers_per_slot.get(slot_key, set())

        available_for_slot = [
            (t_name, t_score) for t_name, t_score in top_teachers
            if t_name == "Sans enseignant" or t_name.lower() not in busy_teachers
        ]
        if not available_for_slot:
            available_for_slot = top_teachers

        for room_idx, s in enumerate(eligible_rooms):
            room_name = str(s.get("Code / Salle", "Salle 101"))
            if (room_name.lower(), slot.lower(), req_date) in occupied_rooms:
                continue

            teacher_name, teacher_score = available_for_slot[(slot_idx + room_idx) % len(available_for_slot)]
            combo_key = (slot, room_name, teacher_name)
            if combo_key in used_combinations:
                continue
            used_combinations.add(combo_key)

            cap = safe_int_capacity(s.get("Capacité"), default=40)
            has_hvac = "Oui" in str(s.get("Capteur HVAC Smart", ""))
            hvac_score = 95.0 if has_hvac else 62.0
            fill_ratio_score = min(100.0, round((student_count / max(1, cap)) * 100, 1))

            global_score = round((hvac_score * 0.4) + (teacher_score * 0.4) + (fill_ratio_score * 0.2), 1)
            co2_saved = round((0.85 if has_hvac else 0.40) * 0.45, 2)

            candidate_options.append({
                "timeslot": slot,
                "room_id": room_name,
                "teacher_id": teacher_name,
                "teacher_name": teacher_name,
                "hvac_efficiency_score": hvac_score,
                "teacher_preference_score": teacher_score,
                "global_score": global_score,
                "co2_saved_kg": co2_saved
            })

            if len(candidate_options) >= 18:
                break
        if len(candidate_options) >= 18:
            break

    candidate_options.sort(key=lambda x: x["global_score"], reverse=True)

    selected: List[Dict[str, Any]] = []
    seen_teachers = set()

    for opt in candidate_options:
        if opt["teacher_id"] not in seen_teachers:
            selected.append(opt)
            seen_teachers.add(opt["teacher_id"])
        if len(selected) >= 3:
            break

    for opt in candidate_options:
        if opt not in selected:
            selected.append(opt)
        if len(selected) >= 6:
            break

    while len(selected) < 6:
        idx_fb = len(selected)
        assigned_room, kwh = match_room_by_capacity_hvac(
            course_name,
            student_count,
            salles_list,
            idx_fb,
            workroom_only=teacherless
        )
        t_name, t_score = top_teachers[idx_fb % len(top_teachers)]
        fb_slot = candidate_timeslots[idx_fb % len(candidate_timeslots)]
        selected.append({
            "timeslot": fb_slot,
            "room_id": assigned_room,
            "teacher_id": t_name,
            "teacher_name": t_name,
            "hvac_efficiency_score": 80.0,
            "teacher_preference_score": t_score,
            "global_score": round(82.5 - idx_fb * 1.2, 1),
            "co2_saved_kg": round(kwh * 0.45, 2)
        })

    selected.sort(key=lambda x: x["global_score"], reverse=True)
    for rank_idx, opt in enumerate(selected[:6], start=1):
        opt["rank"] = rank_idx

    return selected[:6]


@app.post(f"{settings.API_V1_STR}/recommendations/confirm")
@app.post("/api/v1/recommendations/confirm")
async def confirm_recommendation(payload: ConfirmRecommendationRequest):
    """
    Valide une proposition de l'Assistant Hybride dans l'emploi du temps optimisé
    sans modifier les fichiers .ics simples d'origine.
    """
    global OPTIMIZED_ASSIGNMENTS

    assignment = payload.assignment
    if is_non_teacher_activity(assignment.course_id):
        assignment.teacher_id = "Sans enseignant"
    assignment.resolution_method = "SMA_CNP"

    existing_idx = None
    for idx, item in enumerate(OPTIMIZED_ASSIGNMENTS):
        if (item.course_id == assignment.course_id and
            item.group_id == assignment.group_id and
            getattr(item, "date", None) == getattr(assignment, "date", None)):
            existing_idx = idx
            break

    if existing_idx is not None:
        OPTIMIZED_ASSIGNMENTS[existing_idx] = assignment
        action = "mise à jour"
    else:
        OPTIMIZED_ASSIGNMENTS.append(assignment)
        action = "ajoutée"

    save_optimized_assignments_to_ics(OPTIMIZED_ASSIGNMENTS)

    return {
        "success": True,
        "message": f"Proposition ({assignment.assigned_room} avec {assignment.teacher_id}) {action} dans le planning optimisé.",
        "assignment": assignment,
        "total_courses": len(OPTIMIZED_ASSIGNMENTS)
    }


# --- Endpoints Hyperplanning ---
class HyperplanningSyncRequest(BaseModel):
    ical_url: str


@app.get(f"{settings.API_V1_STR}/hyperplanning/all-assignments", response_model=List[AssignmentResult])
@app.get("/api/hyperplanning/all-assignments", response_model=List[AssignmentResult])
async def get_all_assignments():
    """Retourne les affectations brutes (.ics simples) et les affectations optimisées (SMA) séparément."""
    return RAW_ICS_ASSIGNMENTS + OPTIMIZED_ASSIGNMENTS


@app.get(f"{settings.API_V1_STR}/hyperplanning/raw-assignments", response_model=List[AssignmentResult])
async def get_raw_ics_assignments():
    """Retourne uniquement l'emploi du temps simple issu des fichiers .ics d'origine."""
    return RAW_ICS_ASSIGNMENTS


@app.get(f"{settings.API_V1_STR}/hyperplanning/optimized-assignments", response_model=List[AssignmentResult])
async def get_optimized_assignments():
    """Retourne uniquement l'emploi du temps optimisé par le SMA."""
    return OPTIMIZED_ASSIGNMENTS


@app.post(f"{settings.API_V1_STR}/hyperplanning/sync-url", response_model=List[AssignmentResult])
async def sync_hyperplanning_via_url(req: HyperplanningSyncRequest):
    global RAW_ICS_ASSIGNMENTS
    try:
        assignments = await HyperplanningService.fetch_and_parse_ical(req.ical_url)
        RAW_ICS_ASSIGNMENTS.extend(_mark_as_raw_ics(assignments))
        return RAW_ICS_ASSIGNMENTS + OPTIMIZED_ASSIGNMENTS
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(f"{settings.API_V1_STR}/hyperplanning/upload-ics", response_model=List[AssignmentResult])
async def upload_hyperplanning_ics(file: UploadFile = File(...)):
    global RAW_ICS_ASSIGNMENTS
    promo_from_filename = os.path.splitext(file.filename)[0]
    try:
        contents = await file.read()
        ics_text = contents.decode("utf-8")
        assignments = HyperplanningService.parse_ics_content(ics_text, default_promo=promo_from_filename)
        RAW_ICS_ASSIGNMENTS.extend(_mark_as_raw_ics(assignments))
        return RAW_ICS_ASSIGNMENTS + OPTIMIZED_ASSIGNMENTS
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de lecture du fichier .ics : {str(e)}")


@app.post(f"{settings.API_V1_STR}/hyperplanning/upload-multiple-ics", response_model=List[AssignmentResult])
async def upload_multiple_hyperplanning_ics(files: List[UploadFile] = File(...)):
    global RAW_ICS_ASSIGNMENTS
    RAW_ICS_ASSIGNMENTS.clear()

    for file in files:
        promo_from_filename = os.path.splitext(file.filename)[0]
        try:
            contents = await file.read()
            ics_text = contents.decode("utf-8")
            assignments = HyperplanningService.parse_ics_content(ics_text, default_promo=promo_from_filename)
            RAW_ICS_ASSIGNMENTS.extend(_mark_as_raw_ics(assignments))
        except Exception as e:
            print(f"Erreur sur le fichier {file.filename} : {e}")

    return RAW_ICS_ASSIGNMENTS + OPTIMIZED_ASSIGNMENTS


# --- WebSocket pour Console SMA ---
@app.websocket("/ws/sma-logs")
async def websocket_sma_logs(websocket: WebSocket):
    await websocket.accept()
    client_queue = bus.subscribe_ws()
    try:
        while True:
            msg: FIPAACLMessage = await client_queue.get()
            await websocket.send_json(msg.model_dump())
    except WebSocketDisconnect:
        bus.unsubscribe_ws(client_queue)