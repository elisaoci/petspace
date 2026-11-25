import { useEffect, useState } from "react";
import { Check, KeyRound, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

export function SettingsPage() {
  const { user, changePassword, updateProfile } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [profileError, setProfileError] = useState("");
  const [profileDone, setProfileDone] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);

  const passwordSet = user?.has_password ?? false;

  useEffect(() => setFullName(user?.full_name || ""), [user?.full_name]);

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setProfileError("");
    setProfileDone("");
    if (fullName.trim().length < 2) {
      setProfileError("Укажите ФИО.");
      return;
    }
    setProfileBusy(true);
    try {
      await updateProfile(fullName.trim());
      setProfileDone("ФИО сохранено и будет отображаться в анкетах питомцев.");
    } catch (caught) {
      setProfileError(caught instanceof Error ? caught.message : "Не удалось сохранить ФИО.");
    } finally {
      setProfileBusy(false);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setDone("");
    if (next.length < 8) {
      setError("Пароль должен быть не короче 8 символов.");
      return;
    }
    if (next !== repeat) {
      setError("Пароли не совпадают.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(passwordSet ? current : null, next);
      setCurrent("");
      setNext("");
      setRepeat("");
      setDone("Пароль обновлён. Остальные сессии завершены.");
    } catch (caught) {
      setError(passwordError(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Настройки</p>
          <h1>Аккаунт и безопасность</h1>
        </div>
      </div>

      <section className="card form-layout">
        <div>
          <span className="card-kicker">Аккаунт</span>
          <h3>{user?.email}</h3>
          <p className="muted">
            Роль: {user?.role === "owner" ? "владелец питомца" : user?.role}. Согласия: {user?.consents_accepted ? "приняты" : "нужно обновить"}.
            Пароль: {passwordSet ? "задан" : "не задан — вход по коду с почты"}.
          </p>
          <p className="muted">
            Если пароль забыт, его можно восстановить по коду: <Link to="/reset-password">восстановление пароля</Link>.
          </p>
          <form className="profile-name-form" onSubmit={saveProfile}>
            <label className="field-label" htmlFor="owner-full-name">ФИО владельца
              <input
                className="text-input"
                id="owner-full-name"
                autoComplete="name"
                minLength={2}
                maxLength={255}
                value={fullName}
                onChange={event => setFullName(event.target.value)}
                required
              />
            </label>
            <button className="button secondary" type="submit" disabled={profileBusy}>
              {profileBusy ? "Сохраняем…" : <><Check size={15} /> Сохранить ФИО</>}
            </button>
            {profileError && <p className="form-error" role="alert">{profileError}</p>}
            {profileDone && <p className="muted" role="status">{profileDone}</p>}
          </form>
        </div>

        <form onSubmit={submit}>
          <div className="card-heading">
            <div>
              <span className="card-kicker">Безопасность</span>
              <h3><KeyRound size={16} /> {passwordSet ? "Сменить пароль" : "Задать пароль"}</h3>
            </div>
          </div>

          {passwordSet && (
            <>
              <label className="soft-label" htmlFor="current-password">Текущий пароль</label>
              <input
                className="text-input"
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={event => setCurrent(event.target.value)}
                required
              />
            </>
          )}

          <label className="soft-label" htmlFor="new-password">Новый пароль</label>
          <input
            className="text-input"
            id="new-password"
            type="password"
            autoComplete="new-password"
            placeholder="Минимум 8 символов"
            minLength={8}
            value={next}
            onChange={event => setNext(event.target.value)}
            required
          />

          <label className="soft-label" htmlFor="repeat-password">Повторите новый пароль</label>
          <input
            className="text-input"
            id="repeat-password"
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={event => setRepeat(event.target.value)}
            required
          />

          <button className="button primary full-button" type="submit" disabled={busy}>
            {busy ? "Сохраняем…" : passwordSet ? "Сменить пароль" : "Задать пароль"}
          </button>

          {error && <p className="form-error" role="alert">{error}</p>}
          {done && <p className="muted" role="status"><ShieldCheck size={14} /> {done}</p>}
        </form>
      </section>
    </main>
  );
}

function passwordError(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.code === "password_reused") return "Новый пароль совпадает с текущим.";
    if (caught.code === "current_password_required") return "Укажите текущий пароль.";
    const detail = caught.detail as { message?: string } | string | undefined;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && detail.message) return detail.message;
    if (caught.status === 401) return "Текущий пароль неверен.";
    if (caught.status === 422) return "Пароль не соответствует требованиям (минимум 8 символов).";
  }
  return caught instanceof Error ? caught.message : "Не удалось изменить пароль.";
}
