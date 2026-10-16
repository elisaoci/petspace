import { useState } from "react";
import { ArrowRight, KeyRound, Mail, ShieldCheck } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type Step = "email" | "code";

export function LoginPage() {
  const { user, loading, requestCode, verifyCode, consentRequirements } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [accepted, setAccepted] = useState<string[]>([]);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/app";

  if (loading) {
    return (
      <main className="content">
        <section className="card empty-card">
          <p className="muted">Проверяем сессию…</p>
        </section>
      </main>
    );
  }

  if (user) return <Navigate to={from} replace />;

  const allAccepted = consentRequirements.every(item => accepted.includes(item.kind));

  const submitEmail = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!allAccepted || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await requestCode(email.trim());
      setDevCode(response.dev_code ?? null);
      setStep("code");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отправить код.");
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await verifyCode(
        email.trim(),
        code.trim(),
        consentRequirements.map(item => ({ kind: item.kind, version: item.version })),
      );
      navigate(from, { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Вход</p>
          <h1>Кабинет владельца</h1>
        </div>
      </div>
      <p className="lead">
        Вход по одноразовому коду: пароль не нужен. Данные питомца принадлежат владельцу — клиника получит
        доступ только после вашего подтверждения.
      </p>

      <section className="card form-layout">
        {step === "email" ? (
          <form onSubmit={submitEmail}>
            <div className="card-heading">
              <div>
                <span className="card-kicker">Шаг 1 из 2</span>
                <h3><Mail size={16} /> Куда отправить код</h3>
              </div>
            </div>
            <label className="soft-label" htmlFor="email">Email</label>
            <input
              className="text-input"
              id="email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={event => setEmail(event.target.value)}
              required
            />

            {consentRequirements.length > 0 && (
              <fieldset className="consent-list">
                <legend className="soft-label">Согласия</legend>
                {consentRequirements.map(item => (
                  <label className="consent-item" key={item.kind}>
                    <input
                      type="checkbox"
                      checked={accepted.includes(item.kind)}
                      onChange={event => setAccepted(current =>
                        event.target.checked ? [...current, item.kind] : current.filter(kind => kind !== item.kind),
                      )}
                    />
                    <span>{consentLabel(item.kind)} <span className="muted">(версия {item.version})</span></span>
                  </label>
                ))}
              </fieldset>
            )}

            <button className="button primary full-button" type="submit" disabled={!allAccepted || busy}>
              {busy ? "Отправляем…" : "Получить код"} <ArrowRight size={16} />
            </button>
          </form>
        ) : (
          <form onSubmit={submitCode}>
            <div className="card-heading">
              <div>
                <span className="card-kicker">Шаг 2 из 2</span>
                <h3><KeyRound size={16} /> Введите код</h3>
              </div>
            </div>
            <p className="muted">Код отправлен на {email}. Он действует несколько минут.</p>
            {devCode && (
              <p className="demo-badge" role="status">Демо-режим: код {devCode}</p>
            )}
            <label className="soft-label" htmlFor="code">Код из письма</label>
            <input
              className="text-input"
              id="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              maxLength={6}
              value={code}
              onChange={event => setCode(event.target.value.replace(/\D/g, ""))}
              required
            />
            <button className="button primary full-button" type="submit" disabled={code.length < 4 || busy}>
              {busy ? "Проверяем…" : "Войти"}
            </button>
            <button className="button secondary full-button" type="button" onClick={() => setStep("email")}>
              Изменить email
            </button>
          </form>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}

        <p className="muted"><ShieldCheck size={14} /> Мы никогда не спрашиваем код по телефону или в чате.</p>
      </section>
    </main>
  );
}

function consentLabel(kind: string): string {
  switch (kind) {
    case "terms":
      return "Принимаю пользовательское соглашение";
    case "privacy":
      return "Согласен на обработку персональных данных (152-ФЗ)";
    case "ai_disclaimer":
      return "Понимаю, что ответы ИИ не заменяют ветеринара";
    default:
      return `Согласие: ${kind}`;
  }
}
