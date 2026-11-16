import React, { useMemo, useState } from 'react';
import { apiService } from '../services/api';
import { UserRole } from '../types';

interface RegisterProps {
  onSwitchToLogin: () => void;
}

export const Register: React.FC<RegisterProps> = ({ onSwitchToLogin }) => {
  const [nom, setNom] = useState<string>('');
  const [prenom, setPrenom] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [campus, setCampus] = useState<string>('Douala - Yansoki');
  const [role, setRole] = useState<UserRole | ''>('');
  const [password, setPassword] = useState<string>('');
  const [passwordConfirm, setPasswordConfirm] = useState<string>('');
  const [acceptTerms, setAcceptTerms] = useState<boolean>(false);

  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [showConfirm, setShowConfirm] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: 'error' | 'success'; message: string } | null>(
    null
  );
  const [loading, setLoading] = useState<boolean>(false);

  const strength = useMemo(() => {
    if (!password) {
      return { level: 2, label: 'moyen', textClass: 'text-amber-600', barClass: 'bg-amber-500' };
    }
    let score = 0;
    if (password.length >= 8) score += 1;
    if (/[A-Z]/.test(password) && /[0-9]/.test(password)) score += 1;
    if (/[^A-Za-z0-9]/.test(password) && password.length >= 10) score += 1;

    if (score <= 1) {
      return { level: 1, label: 'faible', textClass: 'text-red-600', barClass: 'bg-red-500' };
    }
    if (score === 2) {
      return { level: 2, label: 'moyen', textClass: 'text-amber-600', barClass: 'bg-amber-500' };
    }
    return { level: 3, label: 'fort', textClass: 'text-[#16805c]', barClass: 'bg-[#16805c]' };
  }, [password]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFeedback(null);

    if (!nom.trim() || !prenom.trim()) {
      setFeedback({ type: 'error', message: 'Veuillez renseigner votre nom et votre prénom.' });
      return;
    }

    if (!/^[a-zA-Z0-9._-]+@([a-zA-Z0-9-]+\.)?ucac-icam\.com$/i.test(email.trim())) {
      setFeedback({
        type: 'error',
        message:
          'Utilisez votre adresse institutionnelle UCAC-ICAM (@ucac-icam.com ou @2027.ucac-icam.com).',
      });
      return;
    }

    if (!role) {
      setFeedback({ type: 'error', message: 'Veuillez choisir un rôle.' });
      return;
    }

    if (password.length < 8) {
      setFeedback({
        type: 'error',
        message: 'Le mot de passe doit contenir au minimum 8 caractères.',
      });
      return;
    }

    if (password !== passwordConfirm) {
      setFeedback({ type: 'error', message: 'Les deux mots de passe ne correspondent pas.' });
      return;
    }

    if (!acceptTerms) {
      setFeedback({
        type: 'error',
        message: "Veuillez accepter les conditions d'utilisation et la politique de confidentialité.",
      });
      return;
    }

    try {
      setLoading(true);
      await apiService.register({
        nom: nom.trim(),
        prenom: prenom.trim(),
        email: email.trim().toLowerCase(),
        campus,
        role,
        password,
      });

      setFeedback({
        type: 'success',
        message: `Compte créé pour ${prenom} ${nom}. Il sera validé par un administrateur avant la première connexion.`,
      });
      setPassword('');
      setPasswordConfirm('');
    } catch (err) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : "Erreur lors de l'inscription.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f4f7fa] flex items-center justify-center px-4 py-10 font-sans">
      <div className="w-full max-w-2xl rounded-2xl bg-white border border-slate-200/80 shadow-xl shadow-[#0f2342]/[0.06] p-6 sm:p-10">
        <div className="inline-flex items-center gap-2.5 mb-6">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-[#16805c] to-[#132a4a] text-white font-extrabold text-lg flex items-center justify-center shadow-sm">
            P
          </div>
          <span className="text-2xl font-extrabold tracking-tight text-[#132a4a]">
            Plan<span className="text-[#16805c]">It</span>
          </span>
        </div>

        <h1 className="text-2xl sm:text-3xl font-bold text-[#0f2342]">Créer un compte</h1>
        <p className="text-sm text-slate-500 mt-1 mb-7">
          Renseignez vos informations pour rejoindre PlanIt
        </p>

        {feedback && (
          <div
            role="alert"
            className={`mb-6 rounded-xl px-4 py-3 text-sm font-medium border ${
              feedback.type === 'error'
                ? 'bg-red-50 text-red-700 border-red-200'
                : 'bg-emerald-50 text-emerald-700 border-emerald-200'
            }`}
          >
            {feedback.message}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="reg-nom"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Nom
              </label>
              <input
                id="reg-nom"
                type="text"
                value={nom}
                onChange={(e) => setNom(e.target.value)}
                placeholder="Votre nom"
                className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
                required
              />
            </div>

            <div>
              <label
                htmlFor="reg-prenom"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Prénom
              </label>
              <input
                id="reg-prenom"
                type="text"
                value={prenom}
                onChange={(e) => setPrenom(e.target.value)}
                placeholder="Votre prénom"
                className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="reg-email"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                E-mail institutionnel
              </label>
              <input
                id="reg-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="prenom.nom@ucac-icam.com"
                className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
                required
              />
            </div>

            <div>
              <label
                htmlFor="reg-campus"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Campus
              </label>
              <select
                id="reg-campus"
                value={campus}
                onChange={(e) => setCampus(e.target.value)}
                className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
              >
                <option value="Douala - Yansoki">Douala - Yansoki</option>
                <option value="Pointe-Noire">Pointe-Noire</option>
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="reg-role"
              className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
            >
              Rôle
            </label>
            <select
              id="reg-role"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
              required
            >
              <option value="" disabled>
                Choisir un rôle
              </option>
              <option value="administrateur">Administrateur / Planificateur</option>
              <option value="enseignant">Enseignant / Intervenant</option>
              <option value="responsable_pedagogique">Responsable pédagogique</option>
              <option value="etudiant">Étudiant / Délégué de promotion</option>
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="reg-password"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Mot de passe
              </label>
              <div className="relative">
                <input
                  id="reg-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Minimum 8 caractères"
                  className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 pr-20 text-sm text-slate-900 placeholder-slate-400 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-semibold text-[#16805c] hover:bg-emerald-50 transition-colors"
                >
                  {showPassword ? 'Masquer' : 'Afficher'}
                </button>
              </div>
            </div>

            <div>
              <label
                htmlFor="reg-confirm"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Confirmation
              </label>
              <div className="relative">
                <input
                  id="reg-confirm"
                  type={showConfirm ? 'text' : 'password'}
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  placeholder="Répéter le mot de passe"
                  className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 pr-20 text-sm text-slate-900 placeholder-slate-400 focus:border-[#16805c] focus:outline-none focus:ring-2 focus:ring-[#16805c]/20"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm((prev) => !prev)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-semibold text-[#16805c] hover:bg-emerald-50 transition-colors"
                >
                  {showConfirm ? 'Masquer' : 'Afficher'}
                </button>
              </div>
            </div>
          </div>

          <div className="pt-0.5">
            <div className="grid grid-cols-3 gap-1.5 mb-1.5">
              {[1, 2, 3].map((step) => (
                <div
                  key={step}
                  className={`h-1.5 rounded-full transition-colors ${
                    step <= strength.level ? strength.barClass : 'bg-slate-200'
                  }`}
                />
              ))}
            </div>
            <p className="text-xs text-slate-500">
              Niveau de sécurité :{' '}
              <span className={`font-bold ${strength.textClass}`}>{strength.label}</span>
            </p>
          </div>

          <div className="pt-1 pb-2">
            <label className="inline-flex items-start gap-2.5 text-sm text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={acceptTerms}
                onChange={(e) => setAcceptTerms(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-[#16805c]"
                required
              />
              <span>
                J&apos;accepte les{' '}
                <a href="#conditions" className="font-semibold text-[#16805c] hover:underline">
                  conditions d&apos;utilisation
                </a>{' '}
                et la{' '}
                <a href="#confidentialite" className="font-semibold text-[#16805c] hover:underline">
                  politique de confidentialité
                </a>
              </span>
            </label>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-[#132a4a] py-3 text-sm font-semibold text-white shadow-md shadow-[#132a4a]/20 hover:bg-[#0f2342] disabled:opacity-60 transition-all cursor-pointer"
          >
            {loading ? 'Création du compte...' : 'Créer mon compte'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          Vous avez déjà un compte ?{' '}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="font-semibold text-[#16805c] hover:underline cursor-pointer"
          >
            Se connecter
          </button>
        </p>

        <div className="mt-6 rounded-xl bg-slate-50 border border-slate-200 border-l-4 border-l-amber-500 px-4 py-3 text-xs sm:text-sm text-[#132a4a]">
          Votre compte sera validé par un administrateur avant la première connexion.
        </div>
      </div>
    </div>
  );
};