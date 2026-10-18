import { useState } from "react";
import { KeyRound, ShieldCheck, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../lib/api";

export function SettingsPage() {
  const { user, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const passwordSet = user?.has_password ?? false;

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

  const deleteAccount = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!deleteConfirm || deleting) return;
    setDeleteError("");
    setDeleting(true);
    try {
      await api("/account/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, password: deletePassword || null }),
      });
      await logout();
      navigate("/", { replace: true });
    } catch (caught) {
      setDeleteError(caught instanceof ApiError ? caught.message : "Не удалось удалить аккаунт.");
    } finally {
      setDeleting(false);
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
            Роль: владелец. Согласия: {user?.consents_accepted ? "приняты" : "нужно обновить"}.
            Пароль: {passwordSet ? "задан" : "не задан — вход по коду с почты"}.
          </p>
          <p className="muted">
            Если пароль забыт, его можно восстановить по коду: <Link to="/reset-password">восстановление пароля</Link>.
          </p>
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

      <section className="card form-layout">
        <div>
          <span className="card-kicker">Удаление данных</span>
          <h3>Удалить аккаунт</h3>
          <p className="muted">
            Удаляются аккаунт, все питомцы, медкарта с историей, события календаря, переписка с ИИ
            и выданные доступы. Действие необратимо. В журнале остаётся только факт удаления — без
            персональных данных (152-ФЗ).
          </p>
        </div>

        <form onSubmit={deleteAccount}>
          {passwordSet && (
            <>
              <label className="soft-label" htmlFor="delete-password">Пароль</label>
              <input
                className="text-input"
                id="delete-password"
                type="password"
                autoComplete="current-password"
                value={deletePassword}
                onChange={event => setDeletePassword(event.target.value)}
                required
              />
            </>
          )}
          <label className="consent-item">
            <input
              type="checkbox"
              checked={deleteConfirm}
              onChange={event => setDeleteConfirm(event.target.checked)}
            />
            <span>Понимаю, что данные удалятся безвозвратно</span>
          </label>
          <button className="button secondary full-button danger" type="submit" disabled={!deleteConfirm || deleting}>
            <Trash2 size={16} /> {deleting ? "Удаляем…" : "Удалить аккаунт"}
          </button>
          {deleteError && <p className="form-error" role="alert">{deleteError}</p>}
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
