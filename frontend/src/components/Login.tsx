import React, { useState } from 'react';
import { apiService } from '../services/api';
import { UserProfile } from '../types';

interface LoginProps {
  onSuccess: (user: UserProfile) => void;
  onSwitchToRegister: () => void;
}

export const Login: React.FC<LoginProps> = ({ onSuccess, onSwitchToRegister }) => {
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [rememberMe, setRememberMe] = useState<boolean>(false);
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const features: string[] = [
    'Planning sans conflit',
    'Négociation automatique entre agents',
    "Économies d'énergie mesurées",
  ];

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!/^[a-zA-Z0-9._-]+@([a-zA-Z0-9-]+\.)?ucac-icam\.com$/i.test(email.trim())) {
      setError(
        'Veuillez saisir une adresse e-mail institutionnelle UCAC-ICAM (@ucac-icam.com ou @2027.ucac-icam.com).'
      );
      return;
    }

    if (password.length < 8) {
      setError('Le mot de passe doit contenir au moins 8 caractères.');
      return;
    }

    try {
      setLoading(true);
      const data = await apiService.login({ email: email.trim(), password, rememberMe });
      const storage = rememberMe ? localStorage : sessionStorage;
      storage.setItem('planit_token', data.access_token);
      storage.setItem('planit_user', JSON.stringify(data.user));
      onSuccess(data.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de connexion.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-[#f4f7fa] font-sans">
      {/* Colonne gauche : Formulaire de connexion */}
      <div className="bg-white flex items-center justify-center px-6 py-10 sm:px-12">
        <div className="w-full max-w-md">
          <div className="inline-flex items-center gap-2.5 mb-7">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-[#16805c] to-[#132a4a] text-white font-extrabold text-lg flex items-center justify-center shadow-sm">
              P
            </div>
            <span className="text-2xl font-extrabold tracking-tight text-[#132a4a]">
              Plan<span className="text-[#16805c]">It</span>
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-bold text-[#0f2342]">Connexion</h1>
          <p className="text-sm text-slate-500 mt-1 mb-7">
            Accédez à votre espace de planification
          </p>

          {error && (
            <div
              role="alert"
              className="mb-5 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm font-medium text-red-700"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="login-email"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Adresse e-mail
              </label>
              <input
                id="login-email"
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
                htmlFor="login-password"
                className="block text-xs font-bold uppercase tracking-wider text-[#132a4a] mb-1.5"
              >
                Mot de passe
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Saisissez votre mot de passe"
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

            <div className="flex items-center justify-between pt-1 pb-2 text-sm">
              <label className="inline-flex items-center gap-2 text-slate-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 accent-[#16805c]"
                />
                <span>Se souvenir de moi</span>
              </label>

              <button
                type="button"
                onClick={() =>
                  setError('Contactez un administrateur PlanIt pour réinitialiser votre accès.')
                }
                className="font-semibold text-[#16805c] hover:underline"
              >
                Mot de passe oublié ?
              </button>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-[#132a4a] py-3 text-sm font-semibold text-white shadow-md shadow-[#132a4a]/20 hover:bg-[#0f2342] disabled:opacity-60 transition-all cursor-pointer"
            >
              {loading ? 'Connexion en cours...' : 'Se connecter'}
            </button>
          </form>

          <div className="relative my-6 flex items-center justify-center">
            <div className="w-full border-t border-slate-200" />
            <span className="bg-white px-3 text-xs font-medium text-slate-400">ou</span>
          </div>

          <button
            type="button"
            onClick={() =>
              setError('Authentification SSO institutionnelle UCAC-ICAM en cours de configuration.')
            }
            className="w-full rounded-xl border border-slate-300 bg-white py-2.5 px-4 text-sm font-semibold text-[#132a4a] hover:bg-slate-50 hover:border-[#132a4a] flex items-center justify-center gap-2.5 transition-all cursor-pointer"
          >
            <svg width="18" height="18" viewBox="0 0 21 21" aria-hidden="true">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            <span>Continuer avec le compte institutionnel</span>
          </button>

          <p className="mt-7 text-center text-sm text-slate-500">
            Pas encore de compte ?{' '}
            <button
              type="button"
              onClick={onSwitchToRegister}
              className="font-semibold text-[#16805c] hover:underline cursor-pointer"
            >
              Créer un compte
            </button>
          </p>
        </div>
      </div>

      {/* Colonne droite : Panneau de présentation PlanIt */}
      <div className="hidden lg:flex relative overflow-hidden bg-gradient-to-br from-[#1b3d6d] via-[#132a4a] to-[#0f2342] text-white items-center justify-center p-12">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full border border-emerald-400/20 pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 w-80 h-80 rounded-full border border-amber-400/20 pointer-events-none" />

        <div className="relative z-10 max-w-md">
          <span className="inline-block rounded-full bg-emerald-500/15 border border-emerald-400/30 px-3.5 py-1 text-xs font-semibold text-emerald-300 mb-5">
            UCAC-ICAM • Smart Scheduling &amp; Green IT
          </span>

          <h2 className="text-3xl font-extrabold leading-tight mb-4">Bienvenue sur PlanIt</h2>
          <p className="text-slate-300 text-base leading-relaxed mb-8">
            Gérez vos salles, vos enseignants et vos emplois du temps en quelques clics.
          </p>

          <ul className="space-y-3.5">
            {features.map((item) => (
              <li
                key={item}
                className="flex items-center gap-3.5 rounded-xl bg-white/[0.06] border border-white/10 px-4 py-3.5 text-sm font-medium"
              >
                <span className="w-6 h-6 rounded-md bg-[#16805c] text-white font-bold flex items-center justify-center shrink-0">
                  +
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};