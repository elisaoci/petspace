import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { API_URL } from "../lib/api";
import type { PublicAccess } from "../lib/types";

const KIND_LABELS: Record<string, string> = {
  visit: "Приём",
  vaccination: "Прививка",
  lab: "Анализы",
  prescription: "Назначение",
  other: "Другое",
};

/** Страница для клиники: открывается по ссылке доступа, без авторизации. */
export function AccessCardPage() {
  const { token } = useParams();
  const [data, setData] = useState<PublicAccess | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch(`${API_URL}/medical/access/${token}`);
        if (!response.ok) {
          setError("Ссылка недействительна, истекла или отозвана владельцем.");
          return;
        }
        const body = (await response.json()) as PublicAccess;
        if (!cancelled) setData(body);
      } catch {
        if (!cancelled) setError("Не удалось открыть медкарту. Проверьте соединение.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Smart-ID</p>
          <h1>Медкарта по ссылке</h1>
        </div>
      </div>

      {loading && <p className="muted">Открываем медкарту…</p>}
      {error && (
        <section className="card empty-card">
          <p className="form-error" role="alert">{error}</p>
          <Link className="button secondary" to="/">На главную</Link>
        </section>
      )}

      {data && (
        <>
          <p className="lead">
            Доступ выдан: <strong>{data.grant.label}</strong>. Ссылка действует до{" "}
            {new Date(data.grant.expires_at).toLocaleDateString("ru-RU")}.
          </p>

          {data.pet && (
            <section className="card">
              <span className="card-kicker">Пациент</span>
              <h2>{data.pet.name}</h2>
              <p className="muted">
                {data.pet.breed ?? data.pet.species}
                {data.pet.age_years ? ` · ${data.pet.age_years} лет` : ""}
                {data.pet.weight_kg ? ` · ${data.pet.weight_kg} кг` : ""}
                {data.pet.height_cm ? ` · ${data.pet.height_cm} см` : ""}
              </p>
            </section>
          )}

          {data.vaccinations && (
            <section className="card">
              <span className="card-kicker">Прививки</span>
              {data.vaccinations.length === 0 ? (
                <p className="muted">Прививок в карте нет.</p>
              ) : (
                <ul className="record-list">
                  {data.vaccinations.map(record => (
                    <li className="record-row" key={record.id}>
                      <div className="record-meta">
                        <strong>{record.title}</strong>
                        <span className="muted">
                          {new Date(record.occurred_at).toLocaleDateString("ru-RU")}
                          {record.clinic_name ? ` · ${record.clinic_name}` : ""}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {data.records && (
            <section className="card">
              <span className="card-kicker">История приёмов</span>
              {data.records.length === 0 ? (
                <p className="muted">Записей пока нет.</p>
              ) : (
                <ul className="record-list">
                  {data.records.map(record => (
                    <li className="record-row" key={record.id}>
                      <div className="record-meta">
                        <div className="record-head">
                          <span className="record-kind">{KIND_LABELS[record.kind] ?? record.kind}</span>
                          <strong>{record.title}</strong>
                        </div>
                        <span className="muted">
                          {new Date(record.occurred_at).toLocaleDateString("ru-RU")}
                          {record.clinic_name ? ` · ${record.clinic_name}` : ""}
                        </span>
                        {record.description && <p className="record-text">{record.description}</p>}
                        {record.diagnosis && <p className="record-text"><strong>Диагноз:</strong> {record.diagnosis}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <p className="muted">
            <ShieldCheck size={14} /> Доступ выдал владелец питомца. Заметки владельца в эту карту
            не входят.
          </p>
        </>
      )}
    </main>
  );
}
