import { useMemo, useState } from "react";
import { Bell, CalendarDays, Check, Pencil, Plus, Trash2 } from "lucide-react";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { api } from "../lib/api";
import { formatDate, statusLabel } from "../lib/format";

const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const eventTypeLabels: Record<string, string> = {
  vaccine: "Прививка",
  vaccination: "Прививка",
  parasite_treatment: "Обработка",
  vet_visit: "Визит к ветеринару",
  medication: "Лекарства",
  other: "Другое",
};

export function CalendarPage() {
  const { pet, events, reloadEvents, notificationsEnabled, setNotificationsEnabled } = usePets();
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [eventTitle, setEventTitle] = useState("Вакцинация");
  const [eventDate, setEventDate] = useState("");
  const [eventTime, setEventTime] = useState("12:00");
  const [eventType, setEventType] = useState("vaccine");
  const [eventDescription, setEventDescription] = useState("");
  const [eventStatus, setEventStatus] = useState("planned");
  const [editingEventId, setEditingEventId] = useState<number | null>(null);
  const [eventError, setEventError] = useState("");

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startOffset = (new Date(year, month, 1).getDay() + 6) % 7;
  const monthLabel = cursor.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });

  const eventsByDay = useMemo(() => {
    const map = new Map<number, typeof events>();
    events.forEach(event => {
      const date = new Date(event.starts_at);
      if (date.getFullYear() !== year || date.getMonth() !== month) return;
      const day = date.getDate();
      map.set(day, [...(map.get(day) || []), event]);
    });
    return map;
  }, [events, year, month]);

  const notify = async () => {
    if (!pet) return;
    if (!("Notification" in window)) {
      setEventError("Браузер не поддерживает уведомления.");
      return;
    }
    setEventError("");
    try {
      const permission = await Notification.requestPermission();
      const enabled = permission === "granted";
      setNotificationsEnabled(enabled);
      if (!enabled) {
        setEventError("Уведомления отключены в браузере. Разрешите их в настройках сайта.");
        return;
      }
      new Notification("PetSpace", { body: `Напоминания для ${pet.name} включены.` });
    } catch (caught) {
      setEventError(`Не удалось включить уведомления: ${caught instanceof Error ? caught.message : "ошибка браузера"}`);
    }
  };

  const openAdd = (day?: number) => {
    const chosen = day ?? selectedDay;
    setEventError("");
    setEditingEventId(null);
    setEventTitle("");
    setEventTime("12:00");
    setEventType("vaccine");
    setEventDescription("");
    setEventStatus("planned");
    if (chosen) {
      const monthNumber = String(month + 1).padStart(2, "0");
      const dayNumber = String(chosen).padStart(2, "0");
      setEventDate(`${year}-${monthNumber}-${dayNumber}`);
    } else setEventDate("");
    setShowAdd(true);
  };

  const openEdit = (event: (typeof events)[number]) => {
    const startsAt = new Date(event.starts_at);
    setEditingEventId(event.id);
    setEventTitle(event.title);
    setEventDate(`${startsAt.getFullYear()}-${String(startsAt.getMonth() + 1).padStart(2, "0")}-${String(startsAt.getDate()).padStart(2, "0")}`);
    setEventTime(`${String(startsAt.getHours()).padStart(2, "0")}:${String(startsAt.getMinutes()).padStart(2, "0")}`);
    setEventType(event.event_type);
    setEventDescription(event.description || "");
    setEventStatus(event.status);
    setEventError("");
    setShowAdd(true);
  };

  const saveEvent = async () => {
    if (!eventTitle.trim() || !eventDate || !eventTime) {
      setEventError("Укажите название, дату и время события.");
      return;
    }
    const payload = {
      title: eventTitle.trim(),
      description: eventDescription.trim() || null,
      event_type: eventType,
      starts_at: new Date(`${eventDate}T${eventTime}`).toISOString(),
      status: eventStatus,
      ...(editingEventId ? {} : { pet_id: pet!.id }),
    };
    try {
      await api(editingEventId ? `/events/${editingEventId}` : "/events", {
        method: editingEventId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await reloadEvents();
      setShowAdd(false);
      setEventError("");
    } catch (caught) {
      setEventError(`Не удалось сохранить событие: ${caught instanceof Error ? caught.message : "ошибка сервера"}`);
    }
  };

  const removeEvent = async (id: number) => {
    if (!window.confirm("Удалить это событие?")) return;
    try {
      await api(`/events/${id}`, { method: "DELETE" });
      await reloadEvents();
      setEventError("");
    } catch (caught) {
      setEventError(`Не удалось удалить событие: ${caught instanceof Error ? caught.message : "ошибка сервера"}`);
    }
  };

  const setStatus = async (id: number, status: string) => {
    try {
      await api(`/events/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await reloadEvents();
      setEventError("");
    } catch (caught) {
      setEventError(`Не удалось изменить статус: ${caught instanceof Error ? caught.message : "ошибка сервера"}`);
    }
  };

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
            <div><h1>Сначала добавьте питомца</h1></div>
          <PetSwitcher />
        </div>
      </main>
    );
  }

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <h1>Календарь заботы</h1>
        </div>
        <div className="pet-controls">
          <PetSwitcher />
          <button className="button primary" type="button" onClick={() => openAdd()}><Plus size={17} /> Добавить</button>
        </div>
      </div>
      <div className="calendar-layout">
        <section className="card calendar-card">
          <div className="calendar-toolbar">
            <button type="button" aria-label="Предыдущий месяц" onClick={() => setCursor(value => new Date(value.getFullYear(), value.getMonth() - 1, 1))}>‹</button>
            <h3>{monthLabel}</h3>
            <button type="button" aria-label="Следующий месяц" onClick={() => setCursor(value => new Date(value.getFullYear(), value.getMonth() + 1, 1))}>›</button>
          </div>
          <div className="week-grid">{weekdays.map(day => <span key={day}>{day}</span>)}</div>
          <div className="month-grid">
            {Array.from({ length: startOffset }, (_, index) => <span key={`empty-${index}`} />)}
            {Array.from({ length: daysInMonth }, (_, index) => {
              const day = index + 1;
              const isToday = day === new Date().getDate() && month === new Date().getMonth() && year === new Date().getFullYear();
              return (
                <button
                  className={`day${selectedDay === day ? " selected" : ""}${isToday ? " today" : ""}`}
                  key={day}
                  onClick={() => { setSelectedDay(day); }}
                  type="button"
                >
                  {day}
                  {eventsByDay.has(day) && <i className="event-dot" />}
                </button>
              );
            })}
          </div>
          {selectedDay && <p className="selected-day">Выбрано: {selectedDay} {monthLabel} · <button type="button" onClick={() => openAdd(selectedDay)}>добавить событие</button></p>}
        </section>
        <section className="card upcoming-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">Ближайшие события</span>
              <h3>События</h3>
            </div>
            <button className="icon-action" aria-label="Добавить событие" type="button" onClick={() => openAdd()}><CalendarDays size={20} /></button>
          </div>
          {events.length ? events.map(event => (
            <div className="calendar-event-row" key={event.id}>
              <span className={`event-bullet ${event.computed_status === "overdue" ? "red-dot" : event.computed_status === "done" ? "green-dot" : "lavender-dot"}`} />
              <div className="calendar-event-copy">
                <strong>{event.title}</strong>
                <span>{eventTypeLabels[event.event_type] || event.event_type} · {formatDate(event.starts_at)} · {new Date(event.starts_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · {statusLabel(event.computed_status)}</span>
                {event.description && <span>{event.description}</span>}
              </div>
              <div className="calendar-event-actions">
                <button className="icon-action" type="button" aria-label={`Изменить событие ${event.title}`} onClick={() => openEdit(event)}><Pencil size={15} /></button>
                <button className="icon-action danger-action" type="button" aria-label={`Удалить событие ${event.title}`} onClick={() => removeEvent(event.id)}><Trash2 size={15} /></button>
              </div>
              <select className={`event-status-select status-${event.computed_status}`} value={event.status} onChange={change => setStatus(event.id, change.target.value)} aria-label={`Статус события ${event.title}`}>
                <option value="planned">Запланировано</option>
                <option value="done">Сделано</option>
                <option value="overdue">Просрочено</option>
              </select>
            </div>
          )) : <p className="muted">Событий пока нет.</p>}
          {eventError && !showAdd && <p className="form-error" role="alert">{eventError}</p>}
          <button className="button secondary full-button" type="button" onClick={notify}>
            {notificationsEnabled ? <><Check size={16} /> Уведомления включены</> : <><Bell size={16} /> Включить уведомления</>}
          </button>
          <p className="muted notification-note">Напоминания приходят, пока приложение открыто и браузер разрешает уведомления.</p>
        </section>
      </div>
      {showAdd && (
        <div className="modal-backdrop" role="presentation" onClick={() => setShowAdd(false)}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="add-event-title" onClick={event => event.stopPropagation()}>
            <div className="card-heading">
              <h3 id="add-event-title">{editingEventId ? "Изменить событие" : "Новое событие"}</h3>
              <button className="icon-action" aria-label="Закрыть" type="button" onClick={() => setShowAdd(false)}>×</button>
            </div>
            <label className="field-label">Название<input className="text-input" value={eventTitle} onChange={event => setEventTitle(event.target.value)} /></label>
            <label className="field-label">Тип события
              <select className="text-input" value={eventType} onChange={event => setEventType(event.target.value)}>
                <option value="vaccine">Прививка</option>
                <option value="parasite_treatment">Обработка от паразитов</option>
                <option value="vet_visit">Посещение ветеринара</option>
                <option value="medication">Приём лекарств</option>
                <option value="other">Другое</option>
              </select>
            </label>
            <div className="calendar-form-grid">
              <label className="field-label">Дата<input className="text-input" type="date" value={eventDate} onChange={event => setEventDate(event.target.value)} /></label>
              <label className="field-label">Время<input className="text-input" type="time" value={eventTime} onChange={event => setEventTime(event.target.value)} /></label>
            </div>
            <label className="field-label">Описание или комментарий<textarea className="text-input notes-input" value={eventDescription} onChange={event => setEventDescription(event.target.value)} /></label>
            <label className="field-label">Статус
              <select className="text-input" value={eventStatus} onChange={event => setEventStatus(event.target.value)}>
                <option value="planned">Запланировано</option><option value="done">Сделано</option><option value="overdue">Просрочено</option>
              </select>
            </label>
            {eventError && <p className="form-error" role="alert">{eventError}</p>}
            <button className="button primary full-button" type="button" onClick={saveEvent}><Check size={16} /> Сохранить</button>
          </div>
        </div>
      )}
    </main>
  );
}
