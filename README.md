# PlanIt — Plateforme Intelligente de Planification Académique & Optimisation Green-IT

![Statut](https://img.shields.io/badge/Statut-Prototype%20Op%C3%A9rationnel-108A65?style=flat-square)
![Python](https://img.shields.io/badge/Backend-Python%203.11%20%7C%20FastAPI-0F294A?style=flat-square)
![React](https://img.shields.io/badge/Frontend-React%20%7C%20TypeScript%20%7C%20Vite-D99B26?style=flat-square)
![IA](https://img.shields.io/badge/IA-SMA%20FIPA--ACL%20%7C%20OR--Tools-108A65?style=flat-square)
![Docker](https://img.shields.io/badge/Déploiement-Docker%20Ready-0F294A?style=flat-square)

> **Projet Smart Realization — Année Académique 2026-2027 | Promotion X2027**  
> **Institut Ucac-Icam (Campus de Douala - Yansoki & Pointe-Noire) — Groupe 02**

---

## 1. Présentation du Projet

**PlanIt** est une plateforme web intelligente d’ordonnancement académique et d’optimisation énergétique (*Green-IT*) conçue pour l'**Institut Ucac-Icam** (campus de **Douala - Yansoki** et **Pointe-Noire**).

En couplant un **Système Multi-Agents (SMA)** basé sur un protocole d'enchères distribuées (`protocol.py` / `agents.py`) à un **solveur sous contraintes** (`solver.py`), PlanIt exploite directement les emplois du temps exportés depuis **Hyperplanning (`backend/data/ics/*.ics`)** et le référentiel centralisé des ressources **`backend/data/ressources/ressources.xlsx`** afin de :
- **Détecter et éliminer $100\%$ des conflits** d’affectation (chevauchements de salles ou d’enseignants sur les $17$ promotions du campus) ;
- **Réduire de $15\%$ à $25\%$ la consommation électrique** liée à la climatisation (**HVAC**) en priorisant les salles équipées de capteurs *HVAC Smart* et en adaptant la jauge des salles aux effectifs réels ;
- **Assister les replanifications d'urgence** en moins de $2,0\text{ s}$ via un **Assistant Hybride Pareto** proposant les meilleures combinaisons (salle disponible + enseignants qualifiés) ;
- **Sécuriser l'accès par rôles institutionnels** (`administrateur`, `enseignant`, `responsable_pedagogique`, `etudiant`) avec validation préalable des comptes par un administrateur.

---

## 2. Architecture Générale du Dépôt

```text
planit/
├── backend/                                      # API FastAPI, authentification, moteur SMA et données
│   ├── app/
│   │   ├── api/
│   │   │   └── endpoints/
│   │   │       └── ressource.py                  # Endpoints REST (ressources, planning, SMA, assistant, ROI)
│   │   ├── core/
│   │   │   └── config.py                         # Configuration globale, chemins data/ et paramètres CORS
│   │   ├── models/
│   │   │   └── schemas.py                        # Modèles de données Pydantic (Séances, Ressources, SMA)
│   │   ├── services/
│   │   │   ├── hyperplanning.py                  # Parsing des 17 fichiers .ics et export optimisé
│   │   │   └── ressource_service.py              # Lecture/écriture CRUD sur ressources.xlsx
│   │   ├── sma/
│   │   │   ├── agents.py                         # Définition des Agents (Coordinateur, Salles, Enseignants)
│   │   │   ├── protocol.py                       # Protocole de négociation FIPA-ACL (CFP, PROPOSE, ACCEPT)
│   │   │   └── solver.py                         # Solveur sous contraintes & calcul de front de Pareto
│   │   └── main.py                               # Point d'entrée FastAPI, Authentification & WebSockets
│   ├── data/
│   │   ├── ics/                                  # 17 emplois du temps Hyperplanning + export optimisé
│   │   │   ├── Edt_X2027___X5.ics ... Edt_X2031___X1.ics
│   │   │   ├── Edt_B2029__B3.ics ... Edt_B2032___BP.ics
│   │   │   ├── Edt_A2027___A5.ics, Edt_A2028___A4.ics
│   │   │   ├── Edt_IP2027___IP5.ics, Edt_IP2028___IP4.ics, Edt_L3_IP_L2029.ics
│   │   │   ├── Edt_FC2026___C5.ics ... Edt_FC2029___C3.ics
│   │   │   └── planit_optimized_schedule.ics     # Planning global consolidé et optimisé par PlanIt
│   │   ├── ressources/
│   │   │   └── ressources.xlsx                   # Référentiel maître (Salles, Enseignants, Promotions)
│   │   └── users.json                            # Base JSON des comptes utilisateurs et rôles (auto-générée)
│   ├── Dockerfile                                # Image Docker pour le déploiement du backend
│   ├── requirements.txt                          # Dépendances Python 3.11
│   └── README.md                                 # Documentation technique du Backend
├── frontend/                                     # Interface web React + TypeScript + Tailwind CSS
│   ├── public/
│   │   └── favicon.ico
│   ├── src/
│   │   ├── components/
│   │   │   ├── Login.tsx                         # Écran de connexion institutionnelle UCAC-ICAM
│   │   │   ├── Register.tsx                      # Formulaire d'inscription avec validation de domaine
│   │   │   ├── Header.tsx                        # En-tête (Campus, profil connecté, déconnexion, statut WS)
│   │   │   ├── TabNavigation.tsx                 # Navigation principale entre les 5 modules
│   │   │   ├── TimetableGrid.tsx                 # Grille hebdomadaire (.ics initial vs SMA optimisé)
│   │   │   ├── SMASimulator.tsx                  # Simulateur et journal temps réel des négociations SMA
│   │   │   ├── HybridAssistant.tsx               # Assistant hybride de replanification Pareto
│   │   │   ├── RessourceManager.tsx              # Gestionnaire CRUD synchronisé avec ressources.xlsx
│   │   │   └── AnalyticsROI.tsx                  # Tableau de bord énergétique (kWh, FCFA, CO2)
│   │   ├── services/
│   │   │   └── api.ts                            # Client HTTP (Auth + API) et WebSocket vers FastAPI
│   │   ├── types/
│   │   │   └── index.ts                          # Interfaces et types TypeScript partagés
│   │   ├── App.tsx                               # Gestion de session et orchestration des vues
│   │   ├── main.tsx                              # Point d'entrée React
│   │   └── index.css                             # Configuration Tailwind CSS
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── README.md                                 # Documentation technique du Frontend
└── README.md                                     # Documentation générale du projet
```

---

## 3. Périmètre des Données Académiques (`backend/data/`)

Le système couvre l'ensemble des **$17$ promotions** de l'Institut Ucac-Icam réparties en $5$ filières :
- **Ingénieur Généraliste (X) :** `X1` (`Edt_X2031___X1.ics`), `X2` (`Edt_X2030___X2.ics`), `X3` (`Edt_X2029___X3.ics`), `X4` (`Edt_X2028___X4.ics`), `X5` (`Edt_X2027___X5.ics`)
- **Bachelor (B) :** `BP` (`Edt_B2032___BP.ics`), `B1` (`Edt_B2031___B1.ics`), `B2` (`Edt_B2030___B2.ics`), `B3` (`Edt_B2029__B3.ics`)
- **Apprentissage / Alternance (A) :** `A4` (`Edt_A2028___A4.ics`), `A5` (`Edt_A2027___A5.ics`)
- **Ingénieur Informatique & Procédés (IP) :** `L3_IP` (`Edt_L3_IP_L2029.ics`), `IP4` (`Edt_IP2028___IP4.ics`), `IP5` (`Edt_IP2027___IP5.ics`)
- **Formation Continue (FC) :** `C3` (`Edt_FC2029___C3.ics`), `C4` (`Edt_FC2028___C4.ics`), `C5` (`Edt_FC2026___C5.ics`)

---

## 4. Authentification & Gestion des Comptes

L'accès à l'espace de planification est protégé par une authentification institutionnelle intégrée dans `backend/app/main.py` :
- **Adresses autorisées :** Domaines institutionnels `@ucac-icam.com` (personnel et enseignants) ainsi que les sous-domaines de promotion étudiants (ex. `@2027.ucac-icam.com`).
- **Workflow d'inscription :** Tout nouveau compte créé via `Register.tsx` est enregistré dans `backend/data/users.json` avec le statut inactif (`is_active: false`) jusqu'à validation par un administrateur (`PATCH /api/v1/auth/validate/{user_id}`).
- **Compte Administrateur initial (auto-généré au premier démarrage du backend) :**
  - **E-mail :** `admin@ucac-icam.com`
  - **Mot de passe :** `AdminPlanIt2026!`

---

## 5. Installation et Démarrage Rapide

### Option A : Lancement Local (Développement)

#### 1. Cloner le dépôt
```bash
git clone [https://github.com/ATOUGAIIEmmanuelDesire/Projet-planit.git](https://github.com/ATOUGAIIEmmanuelDesire/Projet-planit.git)
cd planit
```

#### 2. Démarrer le Backend (`Python 3.11+`, port `8000`)
```bash
cd backend
python -m venv venv

# Activation sous Windows (PowerShell) :
.\venv\Scripts\Activate.ps1
# Activation sous Linux / macOS :
# source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
L'API est disponible sur `http://localhost:8000` et sa documentation interactive Swagger sur `http://localhost:8000/docs`.

#### 3. Démarrer le Frontend (`Node.js 18+`, port `5173`)
Dans un second terminal à la racine du projet :
```bash
cd frontend
npm install
npm run dev
```
L'interface web est accessible sur `http://localhost:5173`.

### Option B : Lancement du Backend via Docker
Un `Dockerfile` est fourni dans `backend/` pour conteneuriser le serveur FastAPI et ses données :
```bash
cd backend
docker build -t planit-backend .
docker run -d -p 8000:8000 --name planit-api planit-backend
```

---

## 6. Indicateurs Clés de Performance (SMART)

| Indicateur | Cible | Impact Métier & Technique |
| :--- | :--- | :--- |
| **Temps de calcul & Pareto** | $< 2,0\text{ s}$ | Résolution quasi instantanée via `app/sma/solver.py` |
| **Taux de conflits résiduels** | $0\%$ | Arbitrage automatique par négociation SMA (`app/sma/protocol.py`) |
| **Économie d'énergie HVAC** | $-15\%$ à $-25\%$ | Priorisation des salles *HVAC Smart* ($\approx 0,85\text{ kWh}$ économisés/séance) |
| **Réduction d'empreinte carbone** | $0,45\text{ kg CO}_2 / \text{kWh}$ | Suivi consolidé dans le composant `AnalyticsROI.tsx` |
| **Gain de productivité administrative** | $-60\%$ | Synchronisation directe Hyperplanning `.ics` et référentiel `ressources.xlsx` |

---

## 7. Équipe Projet — Groupe 02 (Promotion X2027)

| Membre | Rôle & Contribution |
| :--- | :--- |
| **NOUNGOUA NOUNGOUA Teddy Steven (Chef projet)** | Architecture du Système Multi-Agents (`app/sma/`), protocole FIPA-ACL & solveur |
| **ATOUGA II Emmanuel Désiré** | Architecture Backend FastAPI (`app/main.py`, `app/api/`, `app/services/`), Authentification, `.ics` & Excel |
| **ANDOH Sus-shinley Mbaayi** | Développement Frontend React/TypeScript (`frontend/src/components/`), UX/UI |
| **LEUBOU YAMDJEU Eddy Rayan** | Modélisation énergétique Green-IT (HVAC, $\text{CO}_2$, ROI) & validation fonctionnelle |
