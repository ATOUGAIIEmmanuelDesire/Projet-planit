import re
import httpx
from icalendar import Calendar
from datetime import datetime, date
from typing import List
from app.models.schemas import AssignmentResult

class HyperplanningService:
    """Service de parsing iCal/ICS UCAC-Icam aligné sur la grille React et 2 demi-journées."""

    @staticmethod
    async def fetch_and_parse_ical(ical_url: str) -> List[AssignmentResult]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            response = await client.get(ical_url)
            if response.status_code != 200:
                raise ValueError(f"Erreur d'accès Hyperplanning UCAC-Icam (HTTP {response.status_code})")
            
            return HyperplanningService.parse_ics_content(response.text)

    @staticmethod
    def parse_ics_content(ics_content: str, default_promo: str = "") -> List[AssignmentResult]:
        cal = Calendar.from_ical(ics_content)
        parsed_assignments: List[AssignmentResult] = []
        days_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

        # Formate proprement le nom du fichier (ex: "Edt_X2027___X5" -> "X2027 - X5")
        cleaned_promo = default_promo
        if cleaned_promo.startswith("Edt_"):
            cleaned_promo = cleaned_promo[4:]
        cleaned_promo = cleaned_promo.replace("___", " - ").replace("__", " - ").replace("_", " ").strip()

        for component in cal.walk('VEVENT'):
            summary = str(component.get('summary', ''))
            description = str(component.get('description', ''))
            location = str(component.get('location', 'Salle non définie'))
            dtstart = component.get('dtstart').dt

            if isinstance(dtstart, datetime):
                dt_obj = dtstart
            elif isinstance(dtstart, date):
                dt_obj = datetime.combine(dtstart, datetime.min.time())
            else:
                continue

            day_name = days_fr[dt_obj.weekday()]
            week_num = dt_obj.isocalendar()[1]
            date_str = dt_obj.strftime("%Y-%m-%d")

            # Mappage strict sur les 2 tranches d'heures (08h00-12h00 et 13h00-17h00)
            hour = dt_obj.hour
            if hour < 12:
                slot_time = "08h00-12h00"
            else:
                slot_time = "13h00-17h00"

            timeslot_key = f"S{week_num}_{day_name}_{slot_time}"

            raw_text = summary if summary.strip() else description
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

            course_title = lines[0] if len(lines) > 0 else "Cours UCAC-Icam"
            teacher_name = lines[1] if len(lines) > 1 else "Enseignant non spécifié"

            # Assignation de la promotion : Priorité au nom du fichier nettoyé
            if cleaned_promo:
                promo_group = cleaned_promo
            else:
                promo_match = re.search(r'(X20\d{2}(?:\s*-\s*X\d)?|ING\d|M\d|MASTER\d)', raw_text, re.IGNORECASE)
                if promo_match:
                    promo_group = promo_match.group(1).upper()
                elif len(lines) > 2 and lines[2]:
                    promo_group = lines[2]
                else:
                    promo_group = "Promotion UCAC"

            room_name = location if location and location != 'Salle non définie' else (lines[3] if len(lines) > 3 else "201")

            parsed_assignments.append(
                AssignmentResult(
                    course_id=course_title,
                    timeslot=timeslot_key,
                    assigned_room=room_name,
                    teacher_id=teacher_name,
                    group_id=promo_group,
                    score=95.0,
                    hvac_kwh=0.35,
                    hvac_saved_kwh=0.85,
                    resolution_method=f"HP_DATE_{date_str}"
                )
            )

        return parsed_assignments