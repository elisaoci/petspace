import { useCallback, useEffect, useState, type FormEvent, type InputHTMLAttributes } from "react";
import { FileText, Trash2 } from "lucide-react";
import { useToast } from "../components/Toast";
import { useAuth } from "../context/AuthContext";
import { api, setTokens, type TokenPair } from "../lib/api";
import {
  STATUS_LABELS,
  downloadFile,
  errorText,
  formatDate,
  formatSize,
  type Clinic,
  type ClinicDocument,
} from "../lib/clinicApi";
import "../styles/clinic.css";

const EMPTY = { clinic_name: "", inn: "", address: "", phone: "", email: "", contact_name: "", admin_email: "", password: "" };

function Field({ label, wide, ...props }: { label: string; wide?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={`field-label${wide ? " wide" : ""}`}>
      {label}
      <input className="text-input" {...props} />
    </label>
  );
}

/** Заявка организации: создаёт клинику на проверке и аккаунт её администратора. */
function ApplyForm() {
  const { consentRequirements } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bind = (key: keyof typeof EMPTY) => ({
    value: form[key],
    onChange: (event: { target: { value: string } }) => setForm(current => ({ ...current, [key]: event.target.value })),
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await api<TokenPair>("/clinics/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, email: form.email.trim() || null, consents: consentRequirements }),
      });
      setTokens(result);
      // Полная перезагрузка: приложение заново читает сессию уже с токеном клиники.
      window.location.assign("/clinic");
    } catch (caught) {
      setError(errorText(caught, "Не удалось отправить заявку."));
      setBusy(false);
    }
  };

  return (
    <form className="card cl-form" onSubmit={submit}>
      <h2>Организация</h2>
      <div className="cl-grid">
        <Field label="Название клиники" wide required {...bind("clinic_name")} />
        <Field label="ИНН (10 или 12 цифр)" inputMode="numeric" required {...bind("inn")} />
        <Field label="Телефон" type="tel" placeholder="+7 495 123-45-67" required {...bind("phone")} />
        <Field label="Адрес" wide required {...bind("address")} />
        <Field label="Почта клиники для клиентов (необязательно)" wide type="email" {...bind("email")} />
      </div>
      <h2>Администратор клиники</h2>
      <div className="cl-grid">
        <Field label="Ваше имя" wide required {...bind("contact_name")} />
        <Field label="Почта для входа" type="email" autoComplete="email" required {...bind("admin_email")} />
        <Field label="Пароль (от 8 символов)" type="password" autoComplete="new-password" minLength={8} required {...bind("password")} />
      </div>
      <label className="cl-check">
        <input type="checkbox" checked={agree} onChange={event => setAgree(event.target.checked)} />
        Принимаю условия использования и политику конфиденциальности PetSpace.
      </label>
      {error && <p className="cl-error" role="alert">{error}</p>}
      <div>
        <button className="button primary" type="submit" disabled={busy || !agree || consentRequirements.length === 0}>
          {busy ? "Отправляем…" : "Отправить заявку"}
        </button>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: ".8rem" }}>
        После отправки модератор проверит организацию. Пока идёт проверка, можно загрузить документы.
      </p>
    </form>
  );
}

type MyClinic = Clinic & { my_role: string };

const STATUS_HINT: Record<Clinic["status"], string> = {
  pending: "Заявка на проверке. Приложите документы организации (лицензию, выписку из ЕГРЮЛ), так проверка пройдёт быстрее.",
  approved: "Клиника подтверждена. Кабинет врача, поиск пациентов и приём появятся в следующем обновлении.",
  rejected: "Заявка отклонена. Исправьте данные, при необходимости загрузите документы и отправьте на повторную проверку.",
  suspended: "Работа клиники приостановлена. Свяжитесь с поддержкой PetSpace.",
};

/** Статус заявки и документы. Загружать и удалять документы может администратор клиники. */
function ClinicStatus() {
  const { show } = useToast();
  const [clinic, setClinic] = useState<MyClinic | null>(null);
  const [documents, setDocuments] = useState<ClinicDocument[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [mine, docs] = await Promise.all([api<MyClinic>("/clinics/me"), api<ClinicDocument[]>("/clinics/me/documents")]);
      setClinic(mine);
      setDocuments(docs);
    } catch (caught) {
      setError(errorText(caught, "Не удалось загрузить данные клиники."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const run = async (action: () => Promise<unknown>, done: string) => {
    try {
      await action();
      show(done);
      await load();
    } catch (caught) {
      show(errorText(caught, "Не получилось, попробуйте ещё раз."));
    }
  };
  const upload = (file: File) =>
    run(() => {
      const body = new FormData();
      body.append("file", file);
      body.append("title", file.name);
      return api("/clinics/me/documents", { method: "POST", body });
    }, "Документ загружен");

  if (error) return <p className="cl-error" role="alert">{error}</p>;
  if (!clinic) return <p className="muted">Загружаем данные клиники…</p>;

  const isAdmin = clinic.my_role === "clinic_admin";
  const canDelete = isAdmin && (clinic.status === "pending" || clinic.status === "rejected");

  return (
    <div className="cl-stack">
      <section className="card cl-stack">
        <div>
          <span className={`cl-badge ${clinic.status}`}>{STATUS_LABELS[clinic.status]}</span>
          <h2 style={{ margin: "12px 0 4px" }}>{clinic.name}</h2>
        </div>
        <p className="cl-facts">
          <span>ИНН: <b>{clinic.inn}</b></span>
          <span>Адрес: <b>{clinic.address}</b></span>
          <span>Телефон: <b>{clinic.phone}</b></span>
          <span>Заявка подана: <b>{formatDate(clinic.created_at)}</b></span>
        </p>
        <p className="lead" style={{ margin: 0 }}>{STATUS_HINT[clinic.status]}</p>
        {clinic.status_reason && <p className="cl-error">Причина: {clinic.status_reason}</p>}
        {isAdmin && clinic.status === "rejected" && (
          <div>
            <button className="button primary" type="button" onClick={() => run(() => api("/clinics/me/resubmit", { method: "POST" }), "Заявка отправлена повторно")}>
              Отправить на повторную проверку
            </button>
          </div>
        )}
      </section>

      <section className="card cl-stack">
        <h2 style={{ margin: 0, fontSize: "1.05rem" }}>Документы</h2>
        {documents.length === 0 && <p className="muted" style={{ margin: 0 }}>Документов пока нет.</p>}
        <ul className="cl-docs">
          {documents.map(item => (
            <li key={item.id}>
              <span><FileText size={16} aria-hidden="true" />{item.title} <small>{formatSize(item.size_bytes)}</small></span>
              <span>
                <button className="button secondary" type="button" onClick={() => downloadFile(`/clinics/me/documents/${item.id}/download`, item.filename).catch(caught => show(errorText(caught, "Не удалось скачать.")))}>
                  Скачать
                </button>
                {canDelete && (
                  <button className="button secondary" type="button" aria-label={`Удалить ${item.title}`} onClick={() => run(() => api(`/clinics/me/documents/${item.id}`, { method: "DELETE" }), "Документ удалён")}>
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
        {isAdmin && (
          <label className="field-label">
            Загрузить документ (PDF, JPG или PNG до 5 МБ)
            <input
              className="text-input"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              onChange={event => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void upload(file);
              }}
            />
          </label>
        )}
      </section>
    </div>
  );
}

export function ClinicPage() {
  const { user, loading } = useAuth();
  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Для клиник</p>
          <h1>{user?.role.startsWith("clinic_") ? "Ваша клиника" : "Подключить клинику"}</h1>
        </div>
      </div>
      {loading ? (
        <p className="muted">Проверяем сессию…</p>
      ) : !user ? (
        <ApplyForm />
      ) : user.role.startsWith("clinic_") ? (
        <ClinicStatus />
      ) : (
        <section className="card">
          <p className="lead" style={{ margin: 0 }}>
            Вы вошли как владелец питомца. Чтобы подключить клинику, выйдите из аккаунта и подайте заявку, либо войдите под аккаунтом клиники.
          </p>
        </section>
      )}
    </main>
  );
}
