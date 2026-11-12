from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "PlanIt - Ucac-Icam Timetabling Engine"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Campus Ucac-Icam
    CAMPUSES: List[str] = ["Douala - Yansoki", "Pointe-Noire", "Douala - Akwa"]
    DEFAULT_CAMPUS: str = "Douala - Yansoki"
    
    # Paramètres SMA & Négociation
    CNP_TIMEOUT_SECONDS: float = 0.4
    OR_TOOLS_TIMEOUT_SECONDS: float = 2.0
    
    # Paramètres Green-IT & HVAC
    HVAC_KWH_STANDARD: float = 1.20
    HVAC_KWH_SMART_SENSOR: float = 0.35
    ENERGY_COST_PER_KWH_FCFA: float = 100.0  # Tarif moyen XAF/kWh
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    class Config:
        case_sensitive = True

settings = Settings()