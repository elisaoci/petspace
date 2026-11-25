import { useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

const maxDocumentSize = 10 * 1024 * 1024;

export function ClinicsPage() {
  const { user } = useAuth();
  const [files, setFiles] = useState<File[]>([]);
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!accepted) {
      setError("Подтвердите согласие с условиями и политикой конфиденциальности.");
      return;
    }
    if (files.some(file => file.size > maxDocumentSize || !["application/pdf", "image/jpeg", "image/png"].includes(file.type))) {
      setError("Допустимы только PDF, JPG и PNG размером не больше 10 МБ каждый.");
      return;
    }
    const form = event.currentTarget;
    const values = new FormData(form);
    files.forEach(file => values.append("documents", file));
    setBusy(true);
    setError("");
    setSubmitted(false);
    try {
      await api("/clinics/applications", { method: "POST", body: values });
      form.reset();
      setFiles([]);
      setAccepted(false);
      setSubmitted(true);
    } catch (caught) {
      setError(caught instanceof Error
        ? `Не удалось отправить заявку: ${caught.message}`
        : "Не удалось отправить заявку.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content clinics-page">
      <header className="clinics-intro">
        <p className="eyebrow">PetSpace для ветеринарных клиник</p>
        <h1>Удобная коммуникация с владельцами домашних животных</h1>
      </header>

      {user?.role.startsWith("clinic_") ? (
        <section className="clinic-application-surface">
          <div className="clinic-application-card">
            <p className="eyebrow">Личный кабинет клиники</p>
            <h2>Подключение клиник пока не настроено</h2>
            <p className="muted large">Для входа в кабинет и управления заявками нужна серверная часть клиник.</p>
          </div>
        </section>
      ) : (
        <section className="clinic-application-surface">
          <div className="clinic-application-heading">
            <span className="eyebrow">Для ветеринарных организаций</span>
            <h2>Подключить клинику</h2>
            <p>Оставьте данные организации и администратора для заявки на подключение.</p>
          </div>
          <form className="clinic-application-card" onSubmit={submit}>
            <div className="clinic-form-section">
              <h3>Организация</h3>
              <label className="field-label clinic-field-wide">Название клиники
                <input className="text-input" name="organization_name" autoComplete="organization" required />
              </label>
              <div className="clinic-form-grid">
                <label className="field-label">ИНН
                  <input className="text-input" name="inn" inputMode="numeric" pattern="[0-9]{10}|[0-9]{12}" minLength={10} maxLength={12} required />
                </label>
                <label className="field-label">Телефон
                  <input className="text-input" name="phone" type="tel" autoComplete="tel" required />
                </label>
              </div>
              <label className="field-label clinic-field-wide">Адрес
                <input className="text-input" name="address" autoComplete="street-address" required />
              </label>
              <label className="field-label clinic-field-wide">Почта клиники для клиентов <span className="muted">необязательно</span>
                <input className="text-input" name="contact_email" type="email" autoComplete="email" />
              </label>
            </div>

            <div className="clinic-form-section">
              <h3>Администратор клиники</h3>
              <label className="field-label clinic-field-wide">ФИО администратора
                <input className="text-input" name="admin_name" autoComplete="name" required />
              </label>
              <div className="clinic-form-grid">
                <label className="field-label">Почта для входа
                  <input className="text-input" name="admin_email" type="email" autoComplete="email" required />
                </label>
                <label className="field-label">Пароль
                  <input className="text-input" name="admin_password" type="password" autoComplete="new-password" minLength={8} required />
                </label>
              </div>
            </div>

            <div className="clinic-form-section">
              <h3>Документы организации</h3>
              <label className="field-label">Файлы для проверки
                <input
                  className="text-input document-input"
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png"
                  multiple
                  onChange={event => {
                    setFiles(Array.from(event.target.files || []));
                    setError("");
                  }}
                />
              </label>
              <p className="muted">PDF, JPG или PNG, до 10 МБ каждый. Проверяйте, чтобы документы не содержали лишних персональных данных.</p>
            </div>

            <label className="consent-item clinic-consent">
              <input type="checkbox" checked={accepted} onChange={event => setAccepted(event.target.checked)} />
              <span>Принимаю условия использования и политику конфиденциальности PetSpace.</span>
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            {submitted && <p className="clinic-success" role="status">Заявка отправлена. Модератор проверит данные организации.</p>}
            <button className="button primary full-button" type="submit" disabled={busy || !accepted}>
              {busy ? "Отправляем…" : "Отправить заявку"} <ArrowRight size={16} />
            </button>
            <p className="clinic-review-note"><ShieldCheck size={15} /> Интерфейс формы готов, но серверного API для заявок и документов в проекте пока нет. При отправке приложение покажет ошибку сервера, а не будет имитировать успешную подачу.</p>
          </form>
        </section>
      )}
    </main>
  );
}
