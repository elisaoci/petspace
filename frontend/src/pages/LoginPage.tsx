import { useState } from "react";
import { ArrowRight, KeyRound, LogIn, Mail, ShieldCheck, UserPlus } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

type Mode = "login" | "register" | "code";
type CodeStep = "email" | "code";

export function LoginPage() {
  const {
    user,
    loading,
    register,
    loginWithPassword,
    requestCode,
    verifyCode,
    consentRequirements,
  } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState<string[]>([]);
  const [codeStep, setCodeStep] = useState<CodeStep>("email");
  const [code, setCode] = useState("");
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

  const reset = (next: Mode) => {
    setMode(next);
    setError("");
    setCodeStep("email");
    setCode("");
    setDevCode(null);
  };

  const submitLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await loginWithPassword(email.trim(), password);
      navigate(from, { replace: true });
    } catch (caught) {
      setError(authErrorMessage(caught, "email или пароль"));
    } finally {
      setBusy(false);
    }
  };

  const submitRegister = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !allAccepted) return;
    setBusy(true);
    setError("");
    try {
      await register(
        email.trim(),
        password,
        consentRequirements.map(item => ({ kind: item.kind, version: item.version })),
      );
      navigate(from, { replace: true });
    } catch (caught) {
      setError(authErrorMessage(caught, "регистрация"));
    } finally {
      setBusy(false);
    }
  };

  const submitEmailForCode = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await requestCode(email.trim());
      setDevCode(response.dev_code ?? null);
      setCodeStep("code");
    } catch (caught) {
      setError(authErrorMessage(caught, "код"));
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
      await verifyCode(email.trim(), code.trim());
      navigate(from, { replace: true });
    } catch (caught) {
      setError(authErrorMessage(caught, "код"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Кабинет владельца</p>
          <h1>{mode === "register" ? "Регистрация" : "Вход"}</h1>
        </div>
      </div>
      <p className="lead">
        Данные питомца принадлежат владельцу: клиника получит доступ только после вашего подтверждения.
        {mode === "register" && " Аккаунт создаётся один раз — потом вы входите по паролю."}
      </p>

      <section className="card form-layout">
        {mode !== "code" && (
          <div className="segmented" role="tablist" aria-label="Вход или регистрация">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "login"}
              className={mode === "login" ? "active" : ""}
              onClick={() => reset("login")}
            >
              <LogIn size={15} /> Вход
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "register"}
              className={mode === "register" ? "active" : ""}
              onClick={() => reset("register")}
            >
              <UserPlus size={15} /> Регистрация
            </button>
          </div>
        )}

        {mode === "login" && (
          <form onSubmit={submitLogin}>
            <label className="soft-label" htmlFor="login-email">Email</label>
            <input
              className="text-input"
              id="login-email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={event => setEmail(event.target.value)}
              required
            />
            <label className="soft-label" htmlFor="login-password">Пароль</label>
            <input
              className="text-input"
              id="login-password"
              type="password"
              autoComplete="current-password"
              placeholder="Ваш пароль"
              value={password}
              onChange={event => setPassword(event.target.value)}
              required
            />
            <button className="button primary full-button" type="submit" disabled={busy}>
              {busy ? "Проверяем…" : "Войти"} <ArrowRight size={16} />
            </button>
          </form>
        )}

        {mode === "register" && (
          <form onSubmit={submitRegister}>
            <label className="soft-label" htmlFor="register-email">Email</label>
            <input
              className="text-input"
              id="register-email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={event => setEmail(event.target.value)}
              required
            />
            <label className="soft-label" htmlFor="register-password">Пароль</label>
            <input
              className="text-input"
              id="register-password"
              type="password"
              autoComplete="new-password"
              placeholder="Минимум 8 символов"
              minLength={8}
              value={password}
              onChange={event => setPassword(event.target.value)}
              required
            />

            <fieldset className="consent-list">
              <legend className="soft-label">Согласия (обязательны)</legend>
              {consentRequirements.length === 0 ? (
                <p className="form-error" role="alert">Не удалось загрузить тексты согласий. Обновите страницу.</p>
              ) : (
                consentRequirements.map(item => (
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
                ))
              )}
            </fieldset>

            <button className="button primary full-button" type="submit" disabled={busy || !allAccepted}>
              {busy ? "Создаём…" : "Создать аккаунт"} <ArrowRight size={16} />
            </button>
          </form>
        )}

        {mode === "code" && (
          <form onSubmit={codeStep === "email" ? submitEmailForCode : submitCode}>
            <div className="card-heading">
              <div>
                <span className="card-kicker">Вход по коду</span>
                <h3><KeyRound size={16} /> {codeStep === "email" ? "Куда отправить код" : "Код из письма"}</h3>
              </div>
            </div>
            {codeStep === "email" ? (
              <>
                <p className="muted">Если пароль забыт — войдите по одноразовому коду на почту.</p>
                <label className="soft-label" htmlFor="code-email">Email</label>
                <input
                  className="text-input"
                  id="code-email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={event => setEmail(event.target.value)}
                  required
                />
              </>
            ) : (
              <>
                <p className="muted">Код отправлен на {email}. Он действует несколько минут.</p>
                {devCode && <p className="demo-badge" role="status">Демо-режим: код {devCode}</p>}
                <label className="soft-label" htmlFor="code">Код</label>
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
              </>
            )}
            <button
              className="button primary full-button"
              type="submit"
              disabled={busy || (codeStep === "code" && code.length < 4)}
            >
              {busy ? "Проверяем…" : codeStep === "email" ? "Получить код" : "Войти"}
            </button>
          </form>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}

        <div className="auth-switch">
          {mode !== "code" ? (
            <button type="button" className="link-button" onClick={() => reset("code")}>
              <Mail size={14} /> Войти по коду с почты
            </button>
          ) : (
            <button type="button" className="link-button" onClick={() => reset("login")}>
              Вернуться к входу по паролю
            </button>
          )}
        </div>

        <p className="muted"><ShieldCheck size={14} /> Мы никогда не спрашиваем пароль или код по телефону и в чате.</p>
      </section>
    </main>
  );
}

function authErrorMessage(caught: unknown, what: string): string {
  if (caught instanceof ApiError) {
    const detail = caught.detail as { error?: string; message?: string } | string | undefined;
    if (detail && typeof detail === "object" && detail.error === "email_taken") {
      return "Этот email уже зарегистрирован — перейдите на вкладку «Вход».";
    }
    if (caught.status === 429) {
      return "Слишком много попыток. Подождите несколько минут или войдите по коду с почты.";
    }
    if (caught.status === 401) {
      return "Неверный email или пароль.";
    }
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && detail.message) return detail.message;
  }
  return caught instanceof Error ? caught.message : `Не удалось выполнить: ${what}.`;
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
