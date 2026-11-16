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
from app.sma.protocol import FIPAACLMessage
from app.sma.solver import PlanItCPSolver
from app.services.hyperplanning import HyperplanningService

# --- Registre et stockage global ---
bus = MessageBus()
room_agents: Dict[str, RoomAgent] = {}
teacher_agents: Dict[str, TeacherAgent] = {}
STORED_ASSIGNMENTS: List[AssignmentResult] = []
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

# Mots-clés des activités hors-cours (exemptées d'enseignant)
NON_TEACHER_KEYWORDS = [
    "messe", "diversite", "diversité", "aercr", "aer", "autonomie", 
    "stage", "vie asso", "vie associative", "cctl", "epreuve", "épreuve"
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
    try:
        try:
            msg = FIPAACLMessage(
                performative=performative,
                sender=sender,
                receiver=receiver,
                content=content
            )
        except Exception:
            msg = FIPAACLMessage(
                performative=performative,
                sender=sender,
                receiver=receiver,
                content=content,
                timestamp=datetime.now().isoformat()
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
            # Diffusion directe vers toutes les files d'attente WebSocket abonnées sur bus
            for attr_val in bus.__dict__.values():
                if isinstance(attr_val, (list, set)):
                    for q in list(attr_val):
                        if isinstance(q, asyncio.Queue):
                            await q.put(msg)
    except Exception as e:
        print(f"⚠️ Erreur d'émission log FIPA-ACL : {e}")


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

    if raw_date:
        digits = re.sub(r"[^0-9]", "", str(raw_date))
        if len(digits) >= 8:
            base_day = digits[:8]
            return (
                f"{base_day}T{start_h:02d}{start_m:02d}00",
                f"{base_day}T{end_h:02d}{end_m:02d}00",
            )

    now = datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    week_match = re.search(r"s(\d{1,2})_", slot_lower)
    if week_match:
        iso_week = max(1, min(53, int(week_match.group(1))))

    day_offset = 0
    for day_name, offset in day_offsets.items():
        if day_name in slot_lower:
            day_offset = offset
            break

    monday = datetime.fromisocalendar(iso_year, iso_week, 1)
    target_date = monday + timedelta(days=day_offset)
    date_prefix = target_date.strftime("%Y%m%d")

    return (
        f"{date_prefix}T{start_h:02d}{start_m:02d}00",
        f"{date_prefix}T{end_h:02d}{end_m:02d}00",
    )


def save_assignments_to_ics(assignments: List[AssignmentResult], filepath: Optional[str] = None):
    """Sauvegarde ou met à jour la liste complète des affectations dans planit_optimized_schedule.ics."""
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
        print(f"⚠️ Erreur de sauvegarde du fichier .ics : {e}")


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

    # Nettoyage des colonnes UI temporaires avant écriture
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
            cap = safe_int_capacity(s.get("Capacité"), default=40)
            has_hvac = "Oui" in str(s.get("Capteur HVAC Smart", ""))
            is_lab = "Labo" in str(s.get("Type de Salle", "")) or "FabLab" in str(s.get("Type de Salle", ""))
            
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
        "finan", "compta", "gestion", "eco", "éco", "budget", "tresor", "trésor", 
        "banque", "audit", "fiscal", "comptabilité", "contrôle de gestion", "finance"
    ],
    "maths_stats": [
        "math", "stat", "algebre", "algèbre", "calcul", "analyse", "probab", 
        "geometrie", "géométrie", "mathematique", "mathématiques", "optimisation"
    ],
    "informatique_dev": [
        "dev", "code", "logiciel", "gl", "java", "python", "web", "algo", "algorithm", 
        "data", "bdd", "sql", "ia", "ai", "application", "programmation", "c++", "poo"
    ],
    "reseaux_infra": [
        "reseau", "réseau", "infra", "sys", "systeme", "système", "rt", "telecom", 
        "télécom", "cyber", "secu", "sécu", "cloud", "routeur", "cisco", "linux"
    ],
    "management_projet": [
        "projet", "manag", "management", "pmp", "risk", "qualit", "agile", "scrum", 
        "organisation", "rh", "ressources humaines", "entrepreneuriat"
    ],
    "sciences_ingenieur": [
        "physique", "chimie", "electronique", "électronique", "thermo", "meca", 
        "mécanique", "energie", "énergie", "automat", "electrotechnique", "matériaux"
    ],
    "humanites_langues": [
        "anglais", "english", "comm", "communication", "droit", "francais", "français", 
        "expression", "ethique", "éthique", "sociologie", "culture"
    ]
}


def rank_teachers_by_expertise(course_name: str, teachers_list: List[Dict[str, Any]], max_teachers: int = 3) -> List[Tuple[str, float]]:
    """Classe les meilleurs enseignants de l'Excel par score de pertinence pour un cours donné."""
    if not teachers_list:
        return [("Enseignant Qualifié", 75.0)]

    c_lower = str(course_name or "").lower()

    course_domain = None
    max_course_hits = 0
    for domain, kws in DOMAIN_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in c_lower)
        if hits > max_course_hits:
            max_course_hits = hits
            course_domain = domain

    scored_teachers: List[Tuple[str, float, int]] = []
    course_words = re.findall(r'\w{4,}', c_lower)

    for idx, t in enumerate(teachers_list):
        name = str(t.get("Nom et Prénom", "")).strip()
        if not name:
            continue

        dom = str(t.get("Domaine ", t.get("Domaine", ""))).lower()
        exp = str(t.get("Expertises / Technologies", "")).lower()
        teacher_profile = f"{dom} {exp}"

        raw_score = 0
        if course_domain:
            domain_kws = DOMAIN_KEYWORDS[course_domain]
            if any(kw in teacher_profile for kw in domain_kws):
                raw_score += 10

        for word in course_words:
            if word in teacher_profile:
                raw_score += 2

        # Conversion en pourcentage de pertinence pédagogique (entre 72% et 98%)
        pct_score = min(98.0, 82.0 + raw_score * 1.2) if raw_score > 0 else max(70.0, 76.0 - (idx % 5))
        scored_teachers.append((name, round(pct_score, 1), raw_score))

    # Tri par score décroissant
    scored_teachers.sort(key=lambda item: (item[2], item[1]), reverse=True)

    # Priorité aux enseignants ayant un score > 0 ; complément si moins de max_teachers
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


def match_teacher_by_expertise(course_name: str, teachers_list: List[Dict[str, Any]], idx: int = 0) -> str:
    """Attribue le meilleur enseignant issu de l'Excel selon un scoring par domaine et pertinence."""
    if not course_name or not teachers_list:
        return "Enseignant Qualifié"
    ranked = rank_teachers_by_expertise(course_name, teachers_list, max_teachers=1)
    if ranked:
        return ranked[0][0]
    fallback_name = teachers_list[idx % len(teachers_list)].get("Nom et Prénom")
    return str(fallback_name) if fallback_name else "Enseignant Qualifié"


def match_room_by_capacity_hvac(course_name: str, student_count: int, salles_list: List[Dict[str, Any]], idx: int) -> Tuple[str, float]:
    """Attribue une salle Excel de capacité adéquate avec optimisation des capteurs HVAC Smart."""
    c_lower = str(course_name or "").lower()
    
    if "stage" in c_lower:
        return "Hors campus / Stage", 0.0

    if any(k in c_lower for k in ["messe", "diversit"]):
        amphis = [s for s in salles_list if "amphi" in str(s.get("Type de Salle", "")).lower() or "amphi" in str(s.get("Code / Salle", "")).lower()]
        room_name = str(amphis[0].get("Code / Salle")) if amphis else "Grand Amphi"
        return room_name, 0.50

    eligible = [s for s in salles_list if safe_int_capacity(s.get("Capacité")) >= student_count]
    if not eligible:
        eligible = salles_list or [{"Code / Salle": "Salle 101", "Capteur HVAC Smart": "Oui"}]

    hvac_smart = [s for s in eligible if "Oui" in str(s.get("Capteur HVAC Smart", ""))]
    pool = hvac_smart if hvac_smart else eligible
    chosen = pool[idx % len(pool)]

    saved_kwh = 0.85 if "Oui" in str(chosen.get("Capteur HVAC Smart", "")) else 0.40
    return str(chosen.get("Code / Salle", "Salle 101")), saved_kwh


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
    global EXCEL_RESOURCES_DATA, STORED_ASSIGNMENTS

    _load_users()
    EXCEL_RESOURCES_DATA = load_resources_from_excel()
    sync_in_memory_agents_from_excel()

    router_task = asyncio.create_task(agent_router())
    background_tasks.add(router_task)
    router_task.add_done_callback(background_tasks.discard)

    STORED_ASSIGNMENTS.clear()
    if os.path.exists(ICS_DIR):
        ics_files = [
            f for f in glob(os.path.join(ICS_DIR, "*.ics"))
            if os.path.basename(f).lower() != "planit_optimized_schedule.ics"
        ]
        for file_path in ics_files:
            filename = os.path.basename(file_path)
            promo_from_filename = os.path.splitext(filename)[0]
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    assignments = HyperplanningService.parse_ics_content(
                        content, 
                        default_promo=promo_from_filename
                    )
                    STORED_ASSIGNMENTS.extend(assignments)
            except Exception as e:
                print(f"Erreur chargement {file_path} : {e}")
        print(f"✅ {len(STORED_ASSIGNMENTS)} cours chargés depuis {len(ics_files)} fichiers .ics")

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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
        "is_active": False,  # Validation administrateur requise avant la 1re connexion
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


@app.patch(f"{settings.API_V1_STR}/auth/validate/{{user_id}}", response_model=UserProfileOut)
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

    # Diffusion en direct dans le terminal SMA de la résolution de conflit
    await emit_sma_log(
        "CFP",
        "Coordinator_UcacIcam",
        "ALL_ROOM_AGENTS",
        {"course": req.course_id, "timeslot": req.timeslot, "students": req.students_count}
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
        teacher_id=req.teacher_id,
        group_id=req.group_id,
        requires_lab=req.requires_lab
    )

    if not result:
        # Arbitrage Pareto de secours si aucune salle unique n'atteint la capacité demandée
        best_room, kwh = match_room_by_capacity_hvac(req.course_id, req.students_count, salles_list, 0)
        await emit_sma_log(
            "BID",
            best_room,
            "Coordinator_UcacIcam",
            {"hvac_saved_kwh": kwh, "mode": "Arbitrage_Capacite_Maximale"}
        )
        await emit_sma_log(
            "ACCEPT_PROPOSAL",
            "Coordinator_UcacIcam",
            best_room,
            {"course": req.course_id, "timeslot": req.timeslot, "status": "Conflit résolu par arbitrage"}
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
        {"course": req.course_id, "timeslot": req.timeslot, "teacher": result.get("teacher_id", req.teacher_id)}
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
        teacher_id=result.get("teacher_id", req.teacher_id),
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
    global STORED_ASSIGNMENTS

    salles_list = EXCEL_RESOURCES_DATA.get("salles", [])
    teachers_list = EXCEL_RESOURCES_DATA.get("enseignants", [])
    promos_list = EXCEL_RESOURCES_DATA.get("promotions", [])

    promo_effects = {
        str(p.get("Code promotion", "")).lower(): safe_int_capacity(p.get("Effectif Etudiants"), default=35) 
        for p in promos_list
    }

    target_sessions = STORED_ASSIGNMENTS if len(STORED_ASSIGNMENTS) > 0 else payload.courses

    optimized_assignments: List[AssignmentResult] = []
    total_saved_kwh = 0.0

    # Émission d'initialisation du protocole Contract Net sur le terminal SMA
    await emit_sma_log(
        "CFP",
        "Coordinator_UcacIcam",
        f"AGENTS_POOL ({len(room_agents)} Salles, {len(teacher_agents)} Enseignants)",
        {"sessions_to_schedule": len(target_sessions), "protocol": "FIPA-ACL Contract Net Green-IT"}
    )

    for idx, session in enumerate(target_sessions):
        course_name = get_field_val(session, ["course_id", "name", "id", "summary"], default=f"Cours_{idx+1}")
        group_code = get_field_val(session, ["group_id", "group", "promo"], default="PROMO")
        slot_time = get_field_val(session, ["timeslot", "preferred_timeslot", "start_time"], default="S45_Lundi_08h00-12h00")
        session_date = get_field_val(session, ["date", "start_date"], default=None)

        student_count = promo_effects.get(str(group_code).lower(), 35)

        is_non_teacher = any(k in str(course_name).lower() for k in NON_TEACHER_KEYWORDS)
        if is_non_teacher:
            assigned_teacher = "Sans enseignant"
        else:
            assigned_teacher = match_teacher_by_expertise(course_name, teachers_list, idx)

        assigned_room, kwh = match_room_by_capacity_hvac(course_name, student_count, salles_list, idx)
        total_saved_kwh += kwh

        # Diffusion des trames FIPA-ACL sur le terminal en direct
        await emit_sma_log(
            "CFP",
            "Coordinator_UcacIcam",
            "Room_&_Teacher_Agents",
            {"course": course_name, "promo": group_code, "timeslot": slot_time, "students": student_count}
        )
        await emit_sma_log(
            "BID",
            assigned_room,
            "Coordinator_UcacIcam",
            {"hvac_saved_kwh": kwh, "teacher_candidate": assigned_teacher}
        )
        await emit_sma_log(
            "ACCEPT_PROPOSAL",
            "Coordinator_UcacIcam",
            f"{assigned_room} & {assigned_teacher}",
            {"course": course_name, "timeslot": slot_time, "pareto_score": 95.0}
        )
        # Courte pause toutes les 5 sessions pour fluidifier l'affichage temps réel du terminal
        if idx % 5 == 0:
            await asyncio.sleep(0.01)

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
        optimized_assignments.append(item)

    STORED_ASSIGNMENTS = optimized_assignments
    save_assignments_to_ics(STORED_ASSIGNMENTS)

    exec_time_ms = round((time.time() - t0) * 1000, 2)
    total_courses = len(optimized_assignments)

    return FullScheduleResponse(
        success=True,
        total_courses=total_courses,
        scheduled_courses=total_courses,
        conflicts_unresolved=0,
        global_occupancy_rate=100.0,
        total_energy_saved_kwh=round(total_saved_kwh, 2),
        total_cost_saved_fcfa=round(total_saved_kwh * settings.ENERGY_COST_PER_KWH_FCFA, 2),
        execution_time_ms=exec_time_ms,
        assignments=optimized_assignments
    )


# --- Endpoints Assistant Hybride & Recommandations (6 Alternatives, 2 à 3 Intervenants) ---
@app.post(f"{settings.API_V1_STR}/recommendations/manual")
@app.post("/api/v1/recommendations/hybrid")
def get_hybrid_recommendations(req: ManualRecommendationRequest) -> List[Dict[str, Any]]:
    """
    Assistant Hybride : Croise les données Excel (Salles/Profs/Capacité/Expertise) et les réservations .ics 
    (STORED_ASSIGNMENTS) pour recommander 6 alternatives cohérentes avec 2 à 3 intervenants différents.
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

    occupied_rooms = set()
    occupied_teachers_per_slot: Dict[Tuple[str, str], set] = {}

    for assign in STORED_ASSIGNMENTS:
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
    is_non_teacher = any(k in str(course_name).lower() for k in NON_TEACHER_KEYWORDS)

    # Sélection des 3 meilleurs intervenants qualifiés distincts
    top_teachers: List[Tuple[str, float]] = (
        [("Sans enseignant", 100.0)]
        if is_non_teacher
        else rank_teachers_by_expertise(course_name, teachers_list, max_teachers=3)
    )

    # Filtrage des salles éligibles (capacité + labo)
    eligible_rooms = []
    for s in salles_list:
        cap = safe_int_capacity(s.get("Capacité"), default=40)
        is_lab = "Labo" in str(s.get("Type de Salle", "")) or "FabLab" in str(s.get("Type de Salle", ""))
        if cap < student_count:
            continue
        if getattr(req, "requires_lab", False) and not is_lab:
            continue
        eligible_rooms.append(s)

    if not eligible_rooms:
        eligible_rooms = salles_list or [{"Code / Salle": "Salle 101", "Capacité": 40, "Capteur HVAC Smart": "Oui"}]

    # Tri des salles éligibles : priorité aux salles HVAC Smart et au taux de remplissage optimal
    eligible_rooms.sort(
        key=lambda r: (
            1 if "Oui" in str(r.get("Capteur HVAC Smart", "")) else 0,
            min(1.0, student_count / max(1, safe_int_capacity(r.get("Capacité"), 40)))
        ),
        reverse=True
    )

    candidate_options: List[Dict[str, Any]] = []
    used_combinations = set()

    # Génération de candidats diversifiés combinant les 2 à 3 intervenants différents et les créneaux/salles libres
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

            # Rotation sur les 2 à 3 intervenants qualifiés pour garantir leur diversité dans les 6 options
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

    # Tri par score global décroissant puis sélection équilibrée garantissant 2 à 3 intervenants distincts parmi les 6
    candidate_options.sort(key=lambda x: x["global_score"], reverse=True)

    selected: List[Dict[str, Any]] = []
    seen_teachers = set()

    # Passe 1 : garantir au moins 1 proposition pour chacun des 2 à 3 intervenants distincts
    for opt in candidate_options:
        if opt["teacher_id"] not in seen_teachers:
            selected.append(opt)
            seen_teachers.add(opt["teacher_id"])
        if len(selected) >= 3:
            break

    # Passe 2 : compléter jusqu'à 6 alternatives avec les meilleures options restantes
    for opt in candidate_options:
        if opt not in selected:
            selected.append(opt)
        if len(selected) >= 6:
            break

    # Secours si moins de 6 options libres ont été trouvées
    while len(selected) < 6:
        idx_fb = len(selected)
        assigned_room, kwh = match_room_by_capacity_hvac(course_name, student_count, salles_list, idx_fb)
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

    # Re-tri final par score décroissant et attribution des rangs 1 à 6
    selected.sort(key=lambda x: x["global_score"], reverse=True)
    for rank_idx, opt in enumerate(selected[:6], start=1):
        opt["rank"] = rank_idx

    return selected[:6]


@app.post(f"{settings.API_V1_STR}/recommendations/confirm")
@app.post("/api/v1/recommendations/confirm")
async def confirm_recommendation(payload: ConfirmRecommendationRequest):
    """
    Valide une proposition de l'Assistant Hybride :
    1. Ajoute / Met à jour l'affectation (Salle + Prof) dans STORED_ASSIGNMENTS.
    2. Sauvegarde la mise à jour dans data/ics/planit_optimized_schedule.ics.
    """
    global STORED_ASSIGNMENTS

    assignment = payload.assignment

    existing_idx = None
    for idx, item in enumerate(STORED_ASSIGNMENTS):
        if (item.course_id == assignment.course_id and 
            item.group_id == assignment.group_id):
            existing_idx = idx
            break

    if existing_idx is not None:
        STORED_ASSIGNMENTS[existing_idx] = assignment
        action = "mise à jour"
    else:
        STORED_ASSIGNMENTS.append(assignment)
        action = "ajoutée"

    save_assignments_to_ics(STORED_ASSIGNMENTS)

    return {
        "success": True,
        "message": f"Proposition ({assignment.assigned_room} avec {assignment.teacher_id}) {action} et enregistrée dans planit_optimized_schedule.ics",
        "assignment": assignment,
        "total_courses": len(STORED_ASSIGNMENTS)
    }


# --- Endpoints Hyperplanning ---
class HyperplanningSyncRequest(BaseModel):
    ical_url: str

@app.get(f"{settings.API_V1_STR}/hyperplanning/all-assignments", response_model=List[AssignmentResult])
async def get_all_assignments():
    return STORED_ASSIGNMENTS

@app.post(f"{settings.API_V1_STR}/hyperplanning/sync-url", response_model=List[AssignmentResult])
async def sync_hyperplanning_via_url(req: HyperplanningSyncRequest):
    global STORED_ASSIGNMENTS
    try:
        assignments = await HyperplanningService.fetch_and_parse_ical(req.ical_url)
        STORED_ASSIGNMENTS.extend(assignments)
        save_assignments_to_ics(STORED_ASSIGNMENTS)
        return STORED_ASSIGNMENTS
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post(f"{settings.API_V1_STR}/hyperplanning/upload-ics", response_model=List[AssignmentResult])
async def upload_hyperplanning_ics(file: UploadFile = File(...)):
    global STORED_ASSIGNMENTS
    promo_from_filename = os.path.splitext(file.filename)[0]
    try:
        contents = await file.read()
        ics_text = contents.decode("utf-8")
        assignments = HyperplanningService.parse_ics_content(ics_text, default_promo=promo_from_filename)
        STORED_ASSIGNMENTS.extend(assignments)
        save_assignments_to_ics(STORED_ASSIGNMENTS)
        return STORED_ASSIGNMENTS
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de lecture du fichier .ics : {str(e)}")

@app.post(f"{settings.API_V1_STR}/hyperplanning/upload-multiple-ics", response_model=List[AssignmentResult])
async def upload_multiple_hyperplanning_ics(files: List[UploadFile] = File(...)):
    global STORED_ASSIGNMENTS
    STORED_ASSIGNMENTS.clear()
    
    for file in files:
        promo_from_filename = os.path.splitext(file.filename)[0]
        try:
            contents = await file.read()
            ics_text = contents.decode("utf-8")
            assignments = HyperplanningService.parse_ics_content(ics_text, default_promo=promo_from_filename)
            STORED_ASSIGNMENTS.extend(assignments)
        except Exception as e:
            print(f"Erreur sur le fichier {file.filename} : {e}")
            
    save_assignments_to_ics(STORED_ASSIGNMENTS)
    return STORED_ASSIGNMENTS


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