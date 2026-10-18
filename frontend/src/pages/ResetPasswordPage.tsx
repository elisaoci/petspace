import { useState } from "react";
import { ArrowRight, KeyRound, Mail } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

type Step = "email" | "confirm";

export function ResetPasswordPage() {
  const { requestPasswordReset, confirmPasswordReset } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submitEmail = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await requestPasswordReset(email.trim());
      setDevCode(response.dev_code ?? null);
      setStep("confirm");
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  };

  const submitConfirm = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError("");
    if (password.length < 8) {
      setError("Пароль должен быть не короче 8 символов.");
      return;
    }
    if (password !== repeat) {
      setError("Пароли не совпадают.");
      return;
    }
    setBusy(true);
    try {
      await confirmPasswordReset(email.trim(), code.trim(), password);
      navigate("/app", { replace: true });
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Восстановление</p>
          <h1>Новый пароль</h1>
        </div>
      </div>
      <p className="lead">
        Отправим код на почту, привязанную к аккаунту. После смены пароля все прежние сессии завершатся.
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
            <label className="soft-label" htmlFor="reset-email">Email</label>
            <input
              className="text-input"
              id="reset-email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={event => setEmail(event.target.value)}
              required
            />
            <button className="button primary full-button" type="submit" disabled={busy || !email.trim()}>
              {busy ? "Отправляем…" : "Получить код"} <ArrowRight size={16} />
            </button>
            <p className="muted">Если аккаунт существует, код придёт на этот адрес.</p>
          </form>
        ) : (
          <form onSubmit={submitConfirm}>
            <div className="card-heading">
              <div>
                <span className="card-kicker">Шаг 2 из 2</span>
                <h3><KeyRound size={16} /> Код и новый пароль</h3>
              </div>
            </div>
            <p className="muted">Код отправлен на {email}.</p>
            {devCode && <p className="demo-badge" role="status">Демо-режим: код {devCode}</p>}

            <label className="soft-label" htmlFor="reset-code">Код из письма</label>
            <input
              className="text-input"
              id="reset-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              maxLength={6}
              value={code}
              onChange={event => setCode(event.target.value.replace(/\D/g, ""))}
              required
            />

            <label className="soft-label" htmlFor="reset-password">Новый пароль</label>
            <input
              className="text-input"
              id="reset-password"
              type="password"
              autoComplete="new-password"
              placeholder="Минимум 8 символов"
              minLength={8}
              value={password}
              onChange={event => setPassword(event.target.value)}
              required
            />

            <label className="soft-label" htmlFor="reset-repeat">Повторите пароль</label>
            <input
              className="text-input"
              id="reset-repeat"
              type="password"
              autoComplete="new-password"
              value={repeat}
              onChange={event => setRepeat(event.target.value)}
              required
            />

            <button className="button primary full-button" type="submit" disabled={busy || code.length < 4}>
              {busy ? "Сохраняем…" : "Сохранить пароль"}
            </button>
            <button
              className="button secondary full-button"
              type="button"
              onClick={() => setStep("email")}
            >
              Изменить email
            </button>
          </form>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}

        <p className="muted"><Link to="/login">Вернуться ко входу</Link></p>
      </section>
    </main>
  );
}

function message(caught: unknown): string {
  if (caught instanceof ApiError) {
    const detail = caught.detail as { error?: string; message?: string } | string | undefined;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      if (detail.error === "user_not_found") return "Аккаунт с таким email не найден.";
      if (detail.message) return detail.message;
    }
    if (caught.status === 401) return "Код не подошёл: проверьте его или запросите новый.";
    if (caught.status === 429) return "Слишком много попыток. Подождите несколько минут.";
    if (caught.status === 422) return "Пароль не соответствует требованиям (минимум 8 символов).";
  }
  return caught instanceof Error ? caught.message : "Не удалось выполнить запрос.";
}
