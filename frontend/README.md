# PlanIt Frontend — Interface Web React, TypeScript & Tailwind CSS

Ce dossier héberge l'application web monopage (**SPA**) de **PlanIt**. Développée avec **React**, **TypeScript**, **Vite** et **Tailwind CSS**, elle offre une interface ergonomique aux couleurs de l'**Institut Ucac-Icam** pour s'authentifier, piloter la planification académique, visualiser les négociations du Système Multi-Agents et suivre les gains énergétiques *Green-IT*.

---

## 1. Stack Technique

- **Framework & Langage :** React 18, TypeScript (`tsconfig.json`)
- **Outil de Build :** Vite (`vite.config.ts`)
- **Styles :** Tailwind CSS (`tailwind.config.js`, `postcss.config.js`, `src/index.css`)
- **Icônes :** Lucide React (`lucide-react`)
- **Communication Backend :** Client API REST & WebSocket (`src/services/api.ts`)

---

## 2. Structure du Code Source Frontend

```text
frontend/
├── public/
│   └── favicon.ico                   # Icône de l'application PlanIt
├── src/
│   ├── components/
│   │   ├── Login.tsx                 # Page de connexion institutionnelle UCAC-ICAM
│   │   ├── Register.tsx              # Formulaire d'inscription (rôles, campus, indicateur de mot de passe)
│   │   ├── Header.tsx                # Bandeau supérieur (Campus, statut SMA Live WS, profil & déconnexion)
│   │   ├── TabNavigation.tsx         # Barre d'onglets permettant de basculer entre les 5 modules
│   │   ├── TimetableGrid.tsx         # Grille hebdomadaire interactive (Vue .ics brute vs Vue SMA)
│   │   ├── SMASimulator.tsx          # Simulateur visuel et flux temps réel des échanges FIPA-ACL
│   │   ├── HybridAssistant.tsx       # Assistant hybride de replanification multicritère (Pareto)
│   │   ├── RessourceManager.tsx      # Interface CRUD synchronisée avec backend/data/ressources/ressources.xlsx
│   │   └── AnalyticsROI.tsx          # Tableau de bord des indicateurs Green-IT (kWh, FCFA, CO2)
│   ├── services/
│   │   └── api.ts                    # Appels HTTP (Auth + API) et gestion des connexions WebSocket
│   ├── types/
│   │   └── index.ts                  # Définitions TypeScript (Utilisateurs, Séances, Ressources, SMA, ROI)
│   ├── App.tsx                       # Composant racine, persistance de session et navigation par onglets
│   ├── index.css                     # Styles globaux et directives Tailwind CSS
│   ├── main.tsx                      # Point d'entrée de montage React DOM
│   └── vite-env.d.ts                 # Déclarations d'environnement Vite
├── index.html                        # Page HTML hôte
├── package.json                      # Dépendances et scripts npm
├── package-lock.json                 # Verrouillage des versions npm
├── postcss.config.js                 # Configuration PostCSS
├── tailwind.config.js                # Thème et palette de couleurs Tailwind (Bleu Marine, Or, Vert)
├── tsconfig.json                     # Configuration du compilateur TypeScript
└── vite.config.ts                    # Configuration du serveur de développement et proxy Vite
```

---

## 3. Modules Fonctionnels de l'Interface

L'application gère d'abord l'authentification utilisateur avant d'afficher l'espace de travail orchestré par `App.tsx` :

0. **Authentification & En-tête Utilisateur (`Login.tsx`, `Register.tsx`, `Header.tsx`) :**
   - Connexion sécurisée avec option *Se souvenir de moi* (`localStorage` ou `sessionStorage`).
   - Création de compte réservée aux adresses institutionnelles UCAC-ICAM (`@ucac-icam.com` et sous-domaines étudiants tels que `@2027.ucac-icam.com`) avec jauge de robustesse du mot de passe.
   - Affichage dans `Header.tsx` du sélecteur de campus (`Douala - Yansoki` / `Pointe-Noire`), de l'état de connexion du moteur temps réel (`SMA Live WS` / `WS Hors ligne`), du profil connecté (Prénom, Nom, Rôle) et du bouton **Déconnexion**.
1. **Grille d'Emploi du Temps (`TimetableGrid.tsx`) :**
   - Sélection par **promotion** (parmi les $17$ promotions Ucac-Icam) et par **semaine**.
   - Comparaison directe entre le **planning Hyperplanning initial (`.ics`)** et le **planning optimisé sans conflit**.
   - Export direct du planning consolidé (`planit_optimized_schedule.ics`).
2. **Simulateur Multi-Agents (`SMASimulator.tsx`) :**
   - Visualisation en temps réel des négociations entre l'Agent Coordinateur, les Agents Salles et les Agents Enseignants lors de la résolution d'un conflit.
3. **Assistant Hybride de Replanification (`HybridAssistant.tsx`) :**
   - Recherche d'une séance à déplacer ou replanifier en urgence.
   - Présentation des $6$ meilleures alternatives optimisées (salle disponible avec score énergétique + $2$ à $3$ enseignants qualifiés disponibles).
4. **Gestionnaire de Ressources (`RessourceManager.tsx`) :**
   - Consultation, ajout, modification et suppression des **Salles**, **Enseignants** et **Promotions** avec persistance immédiate dans `ressources.xlsx`.
5. **Analytics & ROI Green-IT (`AnalyticsROI.tsx`) :**
   - Suivi des économies d'énergie ($\text{kWh}$), des gains financiers ($\text{FCFA}$), de la réduction d'empreinte carbone ($\text{kg CO}_2$) et du taux d'occupation des salles.

---

## 4. Installation et Lancement

### Prérequis
- **Node.js** $18.0+$ et **npm**
- Le serveur **Backend FastAPI** démarré sur `http://localhost:8000`

### 1. Installer les dépendances
```bash
cd frontend
npm install
```

### 2. Lancer le serveur de développement
```bash
npm run dev
```
L'application est accessible dans votre navigateur à l'adresse `http://localhost:5173`.

### 3. Générer le build de production
```bash
npm run build
```
Les fichiers statiques optimisés sont générés dans le répertoire `dist/`.