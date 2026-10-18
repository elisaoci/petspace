import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { usePets } from "../context/PetContext";
import { api } from "../lib/api";
import type { MedicalRecord, RecordKind } from "../lib/types";

const KIND_LABELS: Record<RecordKind, string> = {
  visit: "Приём",
  vaccination: "Прививка",
  lab: "Анализы",
  prescription: "Назначение",
  other: "Другое",
};

export function RecordsPanel() {
  const { pet } = usePets();
  const [records, setRecords] = useState<MedicalRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [kind, setKind] = useState<RecordKind>("visit");
  const [title, setTitle] = useState("");
  const [occurredAt, setOccurredAt] = useState(new Date().toISOString().slice(0, 16));
  const [clinicName, setClinicName] = useState("");
  const [description, setDescription] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async (petId: number) => {
    setLoading(true);
    setError("");
    try {
      setRecords(await api<MedicalRecord[]>(`/pets/${petId}/records`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить медкарту.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (pet) load(pet.id).catch(() => undefined);
    else setRecords([]);
  }, [pet?.id]);

  if (!pet) {
    return <p className="muted">Сначала добавьте питомца.</p>;
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(`/pets/${pet.id}/records`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          title: title.trim(),
          occurred_at: new Date(occurredAt).toISOString(),
          clinic_name: clinicName.trim() || null,
          description: description.trim() || null,
          diagnosis: diagnosis.trim() || null,
        }),
      });
      setTitle("");
      setClinicName("");
      setDescription("");
      setDiagnosis("");
      setFormOpen(false);
      await load(pet.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить запись.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (recordId: number) => {
    if (!confirm("Удалить запись из медкарты?")) return;
    try {
      await api(`/records/${recordId}`, { method: "DELETE" });
      await load(pet.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось удалить запись.");
    }
  };

  return (
    <div className="card">
      <div className="card-heading">
        <div>
          <span className="card-kicker">Smart-ID</span>
          <h3>История приёмов, прививок и назначений</h3>
        </div>
        <button className="button secondary" type="button" onClick={() => setFormOpen(value => !value)}>
          {formOpen ? "Скрыть форму" : <><Plus size={16} /> Добавить запись</>}
        </button>
      </div>

      {formOpen && (
        <form onSubmit={submit} className="record-form">
          <label className="soft-label" htmlFor="record-kind">Тип</label>
          <select
            className="text-input"
            id="record-kind"
            value={kind}
            onChange={event => setKind(event.target.value as RecordKind)}
          >
            {Object.entries(KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          <label className="soft-label" htmlFor="record-title">Название</label>
          <input
            className="text-input"
            id="record-title"
            placeholder="Например: приём в клинике"
            value={title}
            onChange={event => setTitle(event.target.value)}
            required
          />

          <label className="soft-label" htmlFor="record-date">Дата и время</label>
          <input
            className="text-input"
            id="record-date"
            type="datetime-local"
            value={occurredAt}
            onChange={event => setOccurredAt(event.target.value)}
            required
          />

          <label className="soft-label" htmlFor="record-clinic">Клиника</label>
          <input
            className="text-input"
            id="record-clinic"
            placeholder="Клиника и врач"
            value={clinicName}
            onChange={event => setClinicName(event.target.value)}
          />

          <label className="soft-label" htmlFor="record-description">Что было на приёме</label>
          <textarea
            className="text-input record-textarea"
            id="record-description"
            placeholder="Жалобы, осмотр, результаты"
            value={description}
            onChange={event => setDescription(event.target.value)}
          />

          <label className="soft-label" htmlFor="record-diagnosis">Диагноз и назначения</label>
          <textarea
            className="text-input record-textarea"
            id="record-diagnosis"
            placeholder="Диагноз, препараты, диета"
            value={diagnosis}
            onChange={event => setDiagnosis(event.target.value)}
          />

          <button className="button primary full-button" type="submit" disabled={busy}>
            {busy ? "Сохраняем…" : "Сохранить запись"}
          </button>
        </form>
      )}

      {error && <p className="form-error" role="alert">{error}</p>}
      {loading && <p className="muted">Загружаем медкарту…</p>}

      {!loading && records.length === 0 && (
        <p className="muted">Записей пока нет. Добавьте первый приём или прививку.</p>
      )}

      <ul className="record-list">
        {records.map(record => (
          <li className="record-row" key={record.id}>
            <div className="record-meta">
              <div className="record-head">
                <span className="record-kind">{KIND_LABELS[record.kind] ?? record.kind}</span>
                <strong>{record.title}</strong>
              </div>
              <span className="muted">
                {new Date(record.occurred_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}
                {record.clinic_name ? ` · ${record.clinic_name}` : ""}
              </span>
              {record.description && <p className="record-text">{record.description}</p>}
              {record.diagnosis && <p className="record-text"><strong>Диагноз:</strong> {record.diagnosis}</p>}
              <span className="record-source">
                {record.author_type === "clinic" ? "клиника" : "владелец"} · {record.source === "mis" ? "из МИС" : "вручную"}
              </span>
            </div>
            <div className="record-actions">
              <button className="ghost-button" type="button" onClick={() => void remove(record.id)} aria-label="Удалить запись">
                <Trash2 size={16} />
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
