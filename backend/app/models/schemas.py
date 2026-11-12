from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum

class SessionType(str, Enum):
    CM = "CM"  # Cours Magistral
    TD = "TD"  # Travaux Dirigés
    TP = "TP"  # Travaux Pratiques

class CampusEnum(str, Enum):
    YANSOKI = "Douala - Yansoki"
    POINTE_NOIRE = "Pointe-Noire"

class RoomSchema(BaseModel):
    id: str
    name: str
    capacity: int
    campus: CampusEnum = CampusEnum.YANSOKI
    has_hvac_sensor: bool = True
    is_lab: bool = False

class TeacherSchema(BaseModel):
    id: str
    name: str
    department: str
    preferred_timeslots: List[str] = Field(default_factory=list)
    unavailabilities: List[str] = Field(default_factory=list)

class GroupSchema(BaseModel):
    id: str
    name: str
    student_count: int
    promotion: str  # ex: "ING3", "MASTER1"

class CourseSessionSchema(BaseModel):
    id: str
    name: Optional[str] = ""
    teacher_id: str
    group_id: str
    student_count: int
    requires_lab: bool = False
    preferred_timeslot: Optional[str] = None

class FullScheduleRequest(BaseModel):
    courses: List[CourseSessionSchema]
    timeslots: List[str]

class SingleNegotiationRequest(BaseModel):
    course_id: str
    title: Optional[str] = ""
    teacher_id: str
    group_id: str
    students_count: int
    timeslot: str
    session_type: SessionType = SessionType.CM
    requires_lab: bool = False

class AssignmentResult(BaseModel):
    course_id: str
    timeslot: str
    assigned_room: str
    teacher_id: str
    group_id: str
    score: float
    hvac_kwh: float
    hvac_saved_kwh: float
    resolution_method: str = "SMA_CNP"  # SMA_CNP ou OR_TOOLS

class NegotiationResponse(BaseModel):
    success: bool
    assignment: Optional[AssignmentResult] = None
    reason: Optional[str] = None
    execution_time_ms: float

class ManualRecommendationRequest(BaseModel):
    course_id: str
    group_id: str
    teacher_id: str
    students_count: int

class RecommendationOption(BaseModel):
    rank: int
    timeslot: str
    room_id: str
    hvac_efficiency_score: float
    teacher_preference_score: float
    global_score: float
    co2_saved_kg: float

class FullScheduleResponse(BaseModel):
    success: bool
    total_courses: int
    scheduled_courses: int
    conflicts_unresolved: int
    global_occupancy_rate: float
    total_energy_saved_kwh: float
    total_cost_saved_fcfa: float
    execution_time_ms: float
    assignments: List[AssignmentResult]