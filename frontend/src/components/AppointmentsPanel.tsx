import { useEffect, useState } from "react";
import { CalendarPlus, XCircle } from "lucide-react";
import { usePets } from "../context/PetContext";
import { useToast } from "./Toast";
import { SkeletonLines } from "./Skeleton";
import { api } from "../lib/api";
import { track } from "../lib/analytics";
import type { Appointment } from "../lib/types";

const STATUS_LABELS: Record<Appointment["status"], string> = {
  requested: "заявка отправлена",
  confirmed: "подтверждена клиникой",
  cancelled: "отменена",
};

function defaultSlot(): string {
  const date = new Date();
  date.setDate(date.getDate() + 2);
  date.setHours(10, 0, 0, 0);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function AppointmentsPanel() {
  const { pet } = usePets();
  const { show } = useToast();
  const [items, setItems] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [clinic, setClinic] = useState("");
  const [slot, setSlot] = useState(defaultSlot);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async (petId: number) => {
    setLoading(true);
    setError("");
    try {
      setItems(await api<Appointment[]>(`/pets/${petId}/appointments`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить заявки.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (pet) load(pet.id).catch(() => undefined);
    else setItems([]);
  }, [pet?.id]);

  if (!pet) {
    return <p className="muted">Сначала добавьте питомца.</p>;
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!clinic.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(`/pets/${pet.id}/appointments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clinic_name: clinic.trim(),
          slot_start: new Date(slot).toISOString(),
          comment: comment.trim() || null,
        }),
      });
      setClinic("");
      setComment("");
      setSlot(defaultSlot());
      await load(pet.id);
      show("Заявка отправлена клинике");
      track("appointment_requested", "/app/smart-id");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отправить заявку.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (appointmentId: number) => {
    try {
      await api(`/appointments/${appointmentId}/cancel`, { method: "POST" });
      await load(pet.id);
      show("Заявка отменена");
      track("appointment_cancelled", "/app/smart-id");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отменить заявку.");
    }
  };

  return (
    <div className="card">
      <div className="card-heading">
        <div>
          <span className="card-kicker">Запись на приём</span>
          <h3>Заявка в клинику</h3>
        </div>
      </div>
      <p className="muted">
        Выберите клинику и удобное время — заявка появится в списке со статусом.
        Подтверждение от клиники станет доступно на следующем этапе.
      </p>

      <form onSubmit={submit} className="record-form">
        <label className="soft-label" htmlFor="clinic-name">Клиника</label>
        <input
          className="text-input"
          id="clinic-name"
          placeholder="Клиника «Айболит»"
          value={clinic}
          onChange={event => setClinic(event.target.value)}
          required
        />

        <label className="soft-label" htmlFor="clinic-slot">Дата и время</label>
        <input
          className="text-input"
          id="clinic-slot"
          type="datetime-local"
          value={slot}
          onChange={event => setSlot(event.target.value)}
          required
        />

        <label className="soft-label" htmlFor="clinic-comment">Что беспокоит</label>
        <textarea
          className="text-input record-textarea"
          id="clinic-comment"
          placeholder="Коротко опишите причину визита"
          value={comment}
          onChange={event => setComment(event.target.value)}
        />

        <button className="button primary full-button" type="submit" disabled={busy}>
          <CalendarPlus size={16} /> {busy ? "Отправляем…" : "Отправить заявку"}
        </button>
      </form>

      {error && <p className="form-error" role="alert">{error}</p>}
      {loading && <SkeletonLines />}

      {!loading && items.length === 0 && <p className="muted">Заявок пока нет.</p>}

      <ul className="record-list">
        {items.map(item => (
          <li className="record-row" key={item.id}>
            <div className="record-meta">
              <strong>{item.clinic_name}</strong>
              <span className="muted">
                {new Date(item.slot_start).toLocaleString("ru-RU")} · {STATUS_LABELS[item.status]}
              </span>
              {item.comment && <p className="record-text">{item.comment}</p>}
            </div>
            <div className="record-actions">
              {item.status !== "cancelled" && (
                <button className="ghost-button" type="button" onClick={() => void cancel(item.id)}>
                  <XCircle size={16} /> Отменить
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
