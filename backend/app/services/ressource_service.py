import os
import pandas as pd
from typing import Dict, List, Any

# Détection du chemin vers le fichier Excel dans backend/data/ressources/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESOURCE_DIR = os.path.join(BASE_DIR, "data", "ressources")

def get_excel_file_path() -> str:
    possible_names = ["resources.xlsx", "ressources.xlsx"]
    for name in possible_names:
        path = os.path.join(RESOURCE_DIR, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"Aucun fichier Excel de ressources trouvé dans {RESOURCE_DIR}")

def load_all_resources_from_excel() -> Dict[str, List[Dict[str, Any]]]:
    excel_path = get_excel_file_path()
    xls = pd.ExcelFile(excel_path)

    # 1. Feuille Salles
    df_salles = pd.read_excel(xls, sheet_name="Salles").fillna("")
    salles = df_salles.to_dict(orient="records")

    # 2. Feuille Enseignants
    df_enseignants = pd.read_excel(xls, sheet_name="Enseignants").fillna("")
    enseignants = df_enseignants.to_dict(orient="records")

    # 3. Feuille Promotions
    df_promotions = pd.read_excel(xls, sheet_name="Promotions").fillna("")
    promotions = df_promotions.to_dict(orient="records")

    return {
        "salles": salles,
        "enseignants": enseignants,
        "promotions": promotions
    }