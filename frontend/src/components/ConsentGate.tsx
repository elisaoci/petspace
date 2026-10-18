import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

/**
 * Экран согласий: показывается, если у аккаунта нет актуальных версий
 * (например, тексты обновились после регистрации). Без согласий кабинет закрыт.
 */
export function ConsentGate() {
  const { user, consentRequirements, acceptConsents, logout } = useAuth();
  const [accepted, setAccepted] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const allAccepted = consentRequirements.length > 0 && consentRequirements.every(item => accepted.includes(item.kind));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!allAccepted || busy) return;
    setBusy(true);
    setError("");
    try {
      await acceptConsents(consentRequirements.map(item => ({ kind: item.kind, version: item.version })));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Не удалось сохранить согласия.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Согласия</p>
          <h1>Обновились условия</h1>
        </div>
      </div>
      <p className="lead">
        Чтобы продолжить пользоваться кабинетом, подтвердите актуальные версии документов.
        Без согласий мы не можем обрабатывать данные питомца.
      </p>

      <section className="card form-layout">
        <form onSubmit={submit}>
          <fieldset className="consent-list">
            <legend className="soft-label">Документы</legend>
            {consentRequirements.length === 0 ? (
              <p className="muted">Загружаем тексты согласий…</p>
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
                  <span>{label(item.kind)} <span className="muted">(версия {item.version})</span></span>
                </label>
              ))
            )}
          </fieldset>

          <button className="button primary full-button" type="submit" disabled={!allAccepted || busy}>
            {busy ? "Сохраняем…" : "Принять и продолжить"}
          </button>

          {error && <p className="form-error" role="alert">{error}</p>}
        </form>

        <div>
          <p className="muted"><ShieldCheck size={14} /> Аккаунт: {user?.email}</p>
          <button className="link-button" type="button" onClick={() => void logout()}>
            Выйти из аккаунта
          </button>
        </div>
      </section>
    </main>
  );
}

function label(kind: string): string {
  switch (kind) {
    case "terms":
      return "Пользовательское соглашение";
    case "privacy":
      return "Обработка персональных данных (152-ФЗ)";
    case "ai_disclaimer":
      return "Ограничения ИИ-помощника";
    default:
      return kind;
  }
}
