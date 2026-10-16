import { useEffect, useMemo, useState } from "react";
import { Bell, CalendarDays, Check, Plus } from "lucide-react";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { api } from "../lib/api";
import { formatDate, statusLabel } from "../lib/format";

const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function CalendarPage() {
  const { pet, events, reloadEvents } = usePets();
  const [notified, setNotified] = useState(false);
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [eventTitle, setEventTitle] = useState("Вакцинация");
  const [eventDate, setEventDate] = useState("");
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

  useEffect(() => {
    if (!pet || !("Notification" in window) || Notification.permission !== "granted") return;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    events.forEach(event => {
      if (event.computed_status === "done" || event.computed_status === "cancelled") return;
      const eventDate = new Date(event.starts_at);
      eventDate.setHours(0, 0, 0, 0);
      const daysUntil = Math.round((eventDate.getTime() - today.getTime()) / 86400000);
      if (daysUntil !== 0 && daysUntil !== 3) return;
      const reminderKey = `petspace-reminder-${pet.id}-${event.id}-${daysUntil}`;
      if (localStorage.getItem(reminderKey)) return;
      new Notification(`Напоминание для ${pet.name}`, { body: daysUntil === 0 ? `Сегодня: ${event.title}` : `Через 3 дня: ${event.title}` });
      localStorage.setItem(reminderKey, "1");
    });
  }, [events, pet]);

  const notify = async () => {
    if (!pet) return;
    if (!("Notification" in window)) {
      setEventError("Браузер не поддерживает уведомления.");
      setNotified(true);
      return;
    }
    if (Notification.permission === "default") await Notification.requestPermission();
    if (Notification.permission === "granted") {
      new Notification("PetSpace", { body: `Пора проверить календарь ${pet.name}` });
      setNotified(true);
      setEventError("");
    } else {
      setEventError("Браузер запретил уведомления. Разрешите их в настройках сайта.");
      setNotified(true);
    }
  };

  const openAdd = (day?: number) => {
    const chosen = day ?? selectedDay;
    setEventError("");
    if (chosen) {
      const monthNumber = String(month + 1).padStart(2, "0");
      const dayNumber = String(chosen).padStart(2, "0");
      setEventDate(`${year}-${monthNumber}-${dayNumber}`);
    }
    setShowAdd(true);
  };

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
          <div><p className="eyebrow">Календарь</p><h1>Сначала добавьте питомца</h1></div>
          <PetSwitcher />
        </div>
      </main>
    );
  }

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Здоровье {pet.name}</p>
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
            <div className="event-item" key={event.id}>
              <span className={`event-bullet ${event.computed_status === "overdue" ? "red-dot" : "lavender-dot"}`} />
              <div>
                <strong>{event.title}</strong>
                <span>{formatDate(event.starts_at)} · {statusLabel(event.computed_status)}</span>
              </div>
            </div>
          )) : <p className="muted">Событий пока нет.</p>}
          {eventError && !showAdd && <p className="form-error" role="alert">{eventError}</p>}
          <button className="button secondary full-button" type="button" onClick={notify}>
            {notified ? <><Check size={16} /> Проверка выполнена</> : <><Bell size={16} /> Проверить уведомление</>}
          </button>
        </section>
      </div>
      {showAdd && (
        <div className="modal-backdrop" role="presentation" onClick={() => setShowAdd(false)}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="add-event-title" onClick={event => event.stopPropagation()}>
            <div className="card-heading">
              <h3 id="add-event-title">Новое событие</h3>
              <button className="icon-action" aria-label="Закрыть" type="button" onClick={() => setShowAdd(false)}>×</button>
            </div>
            <label className="field-label">Название<input className="text-input" value={eventTitle} onChange={event => setEventTitle(event.target.value)} /></label>
            <label className="field-label">Дата<input className="text-input" type="date" value={eventDate} onChange={event => setEventDate(event.target.value)} /></label>
            {eventError && <p className="form-error" role="alert">{eventError}</p>}
            <button
              className="button primary full-button"
              type="button"
              onClick={async () => {
                if (!eventTitle.trim() || !eventDate) {
                  setEventError("Укажите название и дату события.");
                  return;
                }
                try {
                  await api("/events", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      pet_id: pet.id,
                      title: eventTitle.trim(),
                      starts_at: `${eventDate}T12:00:00+03:00`,
                      event_type: eventTitle.toLowerCase().includes("вакцин") ? "vaccine" : "other",
                      status: "planned",
                    }),
                  });
                  await reloadEvents();
                  setShowAdd(false);
                  setEventError("");
                  setEventTitle("Вакцинация");
                  setEventDate("");
                } catch (error) {
                  setEventError(`Не удалось сохранить событие: ${error instanceof Error ? error.message : "ошибка backend"}`);
                }
              }}
            >
              <Check size={16} /> Сохранить
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
