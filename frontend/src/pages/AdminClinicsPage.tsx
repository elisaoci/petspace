import { useCallback, useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { useToast } from "../components/Toast";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import {
  ROLE_LABELS,
  STATUS_LABELS,
  downloadFile,
  errorText,
  formatDate,
  formatSize,
  type Clinic,
  type ClinicDocument,
  type ClinicStatus,
} from "../lib/clinicApi";
import "../styles/clinic.css";

type Row = Clinic & { staff_count: number; documents_count: number };
type Staff = { id: number; email: string | null; full_name: string; role: string; status: string };
type Detail = Clinic & { created_by_email: string | null; moderated_by_email: string | null; staff: Staff[]; documents: ClinicDocument[] };
type Decision = "approve" | "reject" | "suspend";

const FILTERS: [ClinicStatus, string][] = [
  ["pending", "На проверке"],
  ["approved", "Подтверждённые"],
  ["rejected", "Отклонённые"],
  ["suspended", "Приостановленные"],
];

// Какие решения доступны из какого статуса (то же правило, что на сервере).
const ALLOWED: Record<ClinicStatus, Decision[]> = {
  pending: ["approve", "reject"],
  rejected: ["approve"],
  approved: ["suspend"],
  suspended: ["approve"],
};
const DONE: Record<Decision, string> = { approve: "Клиника подтверждена", reject: "Заявка отклонена", suspend: "Работа клиники приостановлена" };

function Moderation() {
  const { show } = useToast();
  const [filter, setFilter] = useState<ClinicStatus>("pending");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  const loadRows = useCallback(async () => {
    try {
      setRows(await api<Row[]>(`/admin/clinics?status=${filter}`));
      setError("");
    } catch (caught) {
      setError(errorText(caught, "Не удалось загрузить заявки."));
    }
  }, [filter]);
  const loadDetail = useCallback(async (id: number) => {
    try {
      setDetail(await api<Detail>(`/admin/clinics/${id}`));
    } catch (caught) {
      show(errorText(caught, "Не удалось загрузить клинику."));
    }
  }, [show]);

  useEffect(() => {
    void loadRows();
  }, [loadRows]);
  useEffect(() => {
    setDetail(null);
    setReason("");
    if (selected !== null) void loadDetail(selected);
  }, [selected, loadDetail]);

  const decide = async (decision: Decision) => {
    if (!detail) return;
    const needsReason = decision !== "approve";
    if (needsReason && reason.trim().length < 5) {
      show("Укажите причину: её увидит клиника (не короче 5 символов).");
      return;
    }
    try {
      await api(`/admin/clinics/${detail.id}/${decision}`, {
        method: "POST",
        ...(needsReason ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: reason.trim() }) } : {}),
      });
      show(DONE[decision]);
      setReason("");
      await Promise.all([loadRows(), loadDetail(detail.id)]);
    } catch (caught) {
      show(errorText(caught, "Не удалось применить решение."));
    }
  };

  return (
    <>
      <div className="cl-tabs" role="group" aria-label="Статус заявок">
        {FILTERS.map(([id, title]) => (
          <button key={id} type="button" aria-pressed={filter === id} onClick={() => { setFilter(id); setSelected(null); }}>
            {title}
          </button>
        ))}
      </div>
      {error && <p className="cl-error" role="alert">{error}</p>}
      <div className="cl-admin">
        <div className="cl-rows">
          {rows === null && !error && <p className="muted">Загружаем…</p>}
          {rows?.length === 0 && <p className="muted">В этом разделе пока пусто.</p>}
          {rows?.map(row => (
            <button key={row.id} type="button" className="cl-row" aria-pressed={selected === row.id} onClick={() => setSelected(row.id)}>
              <b>{row.name}</b>
              <small>ИНН {row.inn}, {formatDate(row.created_at)}</small>
              <small>Документов: {row.documents_count}, сотрудников: {row.staff_count}</small>
            </button>
          ))}
        </div>

        <section className="card cl-stack">
          {!detail && <p className="muted" style={{ margin: 0 }}>Выберите клинику слева, чтобы посмотреть данные и документы.</p>}
          {detail && (
            <>
              <div>
                <span className={`cl-badge ${detail.status}`}>{STATUS_LABELS[detail.status]}</span>
                <h2 style={{ margin: "12px 0 4px" }}>{detail.name}</h2>
              </div>
              <p className="cl-facts">
                <span>ИНН: <b>{detail.inn}</b></span>
                <span>Адрес: <b>{detail.address}</b></span>
                <span>Телефон: <b>{detail.phone}</b></span>
                <span>Заявку подал: <b>{detail.created_by_email ?? "аккаунт удалён"}</b>, {formatDate(detail.created_at)}</span>
                {detail.moderated_by_email && <span>Решение принял: <b>{detail.moderated_by_email}</b></span>}
              </p>
              {detail.status_reason && <p className="cl-error">Причина: {detail.status_reason}</p>}

              <h3 style={{ margin: 0 }}>Документы</h3>
              {detail.documents.length === 0 && <p className="muted" style={{ margin: 0 }}>Документов нет: можно отклонить заявку с причиной.</p>}
              <ul className="cl-docs">
                {detail.documents.map(item => (
                  <li key={item.id}>
                    <span><FileText size={16} aria-hidden="true" />{item.title} <small>{formatSize(item.size_bytes)}</small></span>
                    <button className="button secondary" type="button" onClick={() => downloadFile(`/admin/clinics/${detail.id}/documents/${item.id}/download`, item.filename).catch(caught => show(errorText(caught, "Не удалось скачать.")))}>
                      Скачать
                    </button>
                  </li>
                ))}
              </ul>

              <h3 style={{ margin: 0 }}>Сотрудники</h3>
              <ul className="cl-docs">
                {detail.staff.map(member => (
                  <li key={member.id}><span>{member.full_name} <small>{member.email}</small></span><small>{ROLE_LABELS[member.role] ?? member.role}</small></li>
                ))}
              </ul>

              <div className="cl-actions">
                {ALLOWED[detail.status].some(item => item !== "approve") && (
                  <textarea value={reason} onChange={event => setReason(event.target.value)} placeholder="Причина (её увидит клиника)" aria-label="Причина решения" />
                )}
                {ALLOWED[detail.status].includes("approve") && (
                  <button className="button primary" type="button" onClick={() => decide("approve")}>Подтвердить</button>
                )}
                {ALLOWED[detail.status].includes("reject") && (
                  <button className="button secondary danger" type="button" onClick={() => decide("reject")}>Отклонить</button>
                )}
                {ALLOWED[detail.status].includes("suspend") && (
                  <button className="button secondary danger" type="button" onClick={() => decide("suspend")}>Приостановить</button>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}

export function AdminClinicsPage() {
  const { user } = useAuth();
  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Модерация</p>
          <h1>Заявки клиник</h1>
        </div>
      </div>
      {user?.role === "platform_admin" ? (
        <Moderation />
      ) : (
        <section className="card">
          <p className="lead" style={{ margin: 0 }}>Раздел доступен только модератору платформы.</p>
        </section>
      )}
    </main>
  );
}
