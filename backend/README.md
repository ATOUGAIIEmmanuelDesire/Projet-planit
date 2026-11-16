# PlanIt Backend — API FastAPI, Authentification, Moteur SMA & Intégration Hyperplanning / Excel

Ce dossier contient le serveur backend de **PlanIt**, développé en **Python 3.11** avec **FastAPI**. Il orchestre l'authentification institutionnelle, la lecture des emplois du temps Hyperplanning (`.ics`), la gestion transactionnelle du référentiel Excel (`ressources.xlsx`), les négociations du **Système Multi-Agents (SMA)** et le solveur d'optimisation sous contraintes.

---

## 1. Structure du Code Backend

```text
backend/
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       └── ressource.py          # Routes REST modulaires pour ressources, plannings et ROI
│   ├── core/
│   │   └── config.py                 # Paramètres d'application, chemins vers data/ et configuration CORS
│   ├── models/
│   │   └── schemas.py                # Schémas Pydantic de validation des requêtes et réponses JSON
│   ├── services/
│   │   ├── hyperplanning.py          # Parsing des 17 fichiers .ics et génération de planit_optimized_schedule.ics
│   │   └── ressource_service.py      # Opérations CRUD sur ressources.xlsx (Salles, Enseignants, Promotions)
│   ├── sma/
│   │   ├── agents.py                 # Modélisation des Agents (Coordinateur, Salles, Enseignants, Groupes)
│   │   ├── protocol.py               # Implémentation du protocole d'enchères FIPA-ACL (CFP, BID, ACCEPT)
│   │   └── solver.py                 # Solveur d'optimisation sous contraintes et classement Pareto
│   ├── __init__.py
│   └── main.py                       # Serveur FastAPI, Authentification, CRUD Excel, SMA & WebSocket
├── data/
│   ├── ics/                          # Fichiers calendaires des 17 promotions + planning optimisé exporté
│   │   ├── Edt_A2027___A5.ics
│   │   ├── Edt_A2028___A4.ics
│   │   ├── Edt_B2029__B3.ics
│   │   ├── Edt_B2030___B2.ics
│   │   ├── Edt_B2031___B1.ics
│   │   ├── Edt_B2032___BP.ics
│   │   ├── Edt_FC2026___C5.ics
│   │   ├── Edt_FC2028___C4.ics
│   │   ├── Edt_FC2029___C3.ics
│   │   ├── Edt_IP2027___IP5.ics
│   │   ├── Edt_IP2028___IP4.ics
│   │   ├── Edt_L3_IP_L2029.ics
│   │   ├── Edt_X2027___X5.ics
│   │   ├── Edt_X2028___X4.ics
│   │   ├── Edt_X2029___X3.ics
│   │   ├── Edt_X2030___X2.ics
│   │   ├── Edt_X2031___X1.ics
│   │   └── planit_optimized_schedule.ics
│   ├── ressources/
│   │   └── ressources.xlsx           # Base de données maître des ressources physiques et humaines
│   └── users.json                    # Persistance JSON des comptes utilisateurs (créé automatiquement)
├── Dockerfile                        # Configuration de conteneurisation Python 3.11
└── requirements.txt                  # Dépendances Python du projet
```

---

## 2. Description des Modules Clés

- **`app/main.py` & `app/core/config.py` :** Configurent le serveur ASGI FastAPI, l'authentification institutionnelle (`users.json`), le chargement/sauvegarde Excel (`ressources.xlsx`), la négociation SMA, l'Assistant Hybride et le flux WebSocket `/ws/sma-logs`.
- **`app/services/hyperplanning.py` :** Analyse les $17$ fichiers `.ics` issus d'Hyperplanning, détecte les collisions temporelles et génère le fichier consolidé `backend/data/ics/planit_optimized_schedule.ics` conforme à la norme RFC 5545.
- **`app/services/ressource_service.py` :** Assure la lecture et l'écriture synchronisée sur le classeur `backend/data/ressources/ressources.xlsx` (onglets `Salles`, `Enseignants`, `Promotions`) avec gestion des verrous fichiers (`HTTP 423 Locked` si le fichier est ouvert dans Excel).
- **`app/sma/agents.py`, `protocol.py` & `solver.py` :** Implémentent le mécanisme d'appel d'offres (*Contract Net*), l'évaluation multicritère (disponibilité, capacité, équipements, capteur *HVAC Smart*) et le calcul de solutions non-dominées au sens de Pareto.

---

## 3. Authentification & Gestion des Utilisateurs (`app/main.py`)

Les routes d'authentification sont directement exposées sous le préfixe `/api/v1/auth` avec stockage persistant dans `backend/data/users.json` :

| Méthode | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Inscription (`@ucac-icam.com` ou `@<promo>.ucac-icam.com`). Compte créé avec `is_active: false`. |
| `POST` | `/api/v1/auth/login` | Authentification par e-mail/mot de passe (`PBKDF2-HMAC-SHA256`) et génération d'un jeton signé (`HMAC-SHA256`). |
| `GET` | `/api/v1/auth/pending` | Liste les comptes utilisateurs en attente d'activation par un administrateur. |
| `PATCH` | `/api/v1/auth/validate/{user_id}` | Active le compte d'un utilisateur (`is_active: true`) pour autoriser sa première connexion. |

- **Compte administrateur par défaut :** Initialisé automatiquement dans `backend/data/users.json` au démarrage (`lifespan`) avec `admin@ucac-icam.com` / `AdminPlanIt2026!`.

---

## 4. Installation et Exécution

### Exécution locale (Python 3.11+)
```bash
cd backend
python -m venv venv

# Windows (PowerShell) :
.\venv\Scripts\Activate.ps1

# Linux / macOS :
# source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Serveur API :** `http://localhost:8000`
- **Documentation Interactive (Swagger UI) :** `http://localhost:8000/docs`

### Exécution avec Docker
```bash
cd backend
docker build -t planit-backend .
docker run -p 8000:8000 planit-backend
```

---

## 5. Modèle Énergétique Green-IT

Le moteur d'évaluation énergétique intégré aux services backend applique les paramètres calibrés pour le campus de Yansoki :
- **Gain énergétique moyen par séance optimisée :** $\Delta E \approx 0,85\text{ kWh}$ via l'allocation prioritaire aux salles *HVAC Smart* et l'ajustement capacité/effectif.
- **Facteur d'émission carbone :** $0,45\text{ kg CO}_2 / \text{kWh}$.
- **Émissions évitées :**
  $$M_{\text{CO}_2} = E_{\text{économisée}} \times 0,45$$

---

## 6. Bonnes Pratiques & Dépannage

1. **Verrouillage de `ressources.xlsx` :** Avant toute opération d'ajout, de modification ou de suppression via l'interface `RessourceManager`, veillez à fermer le fichier `backend/data/ressources/ressources.xlsx` dans Microsoft Excel pour éviter une erreur d'accès concurrent (`HTTP 423`).
2. **Support WebSocket (`/ws/sma-logs`) :** Vérifiez que le paquet `websockets` est bien installé dans votre environnement virtuel Python (`pip install websockets`) afin que le terminal temps réel affiche le statut connecté (`SMA Live WS`).
3. **Fichiers compilés dans Git :** Pensez à exclure `__pycache__/`, `*.pyc` et `backend/data/users.json` dans le `.gitignore` à la racine du dépôt.