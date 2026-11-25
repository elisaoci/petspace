import { ArrowUpRight, Bell, CalendarDays, Heart, ImagePlus, MessageCircle, Scale } from "lucide-react";
import { Link } from "react-router-dom";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { formatAge, formatDate, speciesLabel, statusLabel } from "../lib/format";
import { mediaUrl } from "../lib/api";

export function DashboardPage() {
  const { pet, events } = usePets();
  const todayLabel = new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  const pendingEvents = events
    .filter(event => event.computed_status !== "done" && event.computed_status !== "cancelled")
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
  const now = Date.now();
  const nextEvent = pendingEvents.find(event => new Date(event.starts_at).getTime() >= now) ?? pendingEvents[0];

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
          <div>
            <p className="eyebrow">Кабинет</p>
            <h1>Добавьте первого питомца</h1>
          </div>
          <PetSwitcher />
        </div>
        <section className="card dashboard-empty">
          <div className="photo-placeholder"><ImagePlus size={28} /></div>
          <div>
            <h2>Профиль питомца</h2>
            <p className="muted large">Создайте анкету, чтобы вести календарь заботы и пользоваться помощником.</p>
            <Link className="button primary" to="/app/pet">Создать профиль <ArrowUpRight size={16} /></Link>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{todayLabel}</p>
          <h1>Кабинет {pet.name}</h1>
        </div>
        <PetSwitcher />
      </div>

      <section className="dashboard-widgets" aria-label="Кабинет питомца">
        <Link className="card dashboard-photo-card" to="/app/pet">
          <div className="dashboard-pet-photo">
            {pet.photo_url
              ? <img src={mediaUrl(pet.photo_url)} alt={`Фото ${pet.name}`} />
              : <div className="photo-placeholder"><ImagePlus size={32} /><span>Добавьте фото питомца</span></div>}
          </div>
          <div className="dashboard-photo-info">
            <span className="soft-label">{speciesLabel(pet.species)}</span>
            <h2>{pet.name}</h2>
            <span className="dashboard-card-link">Открыть анкету <ArrowUpRight size={16} /></span>
          </div>
        </Link>

        <Link className="card dashboard-event-card" to="/app/calendar" aria-label="Перейти в календарь событий">
          <div className="card-topline">
            <span className="icon-box lavender"><Bell size={19} /></span>
            <span className="card-kicker">Ближайшее событие</span>
          </div>
          <strong className="dashboard-event-title">{nextEvent?.title || "Событий пока нет"}</strong>
          <span className="dashboard-event-date">
            <CalendarDays size={16} />
            {nextEvent
              ? `${formatDate(nextEvent.starts_at)} · ${statusLabel(nextEvent.computed_status)}`
              : "Добавить событие в календарь"}
          </span>
          <span className="dashboard-card-link">Открыть календарь <ArrowUpRight size={16} /></span>
        </Link>

        <Link className="card dashboard-summary-card" to="/app/pet" aria-label="Открыть анкету питомца">
          <div className="card-topline">
            <span className="icon-box warm"><Scale size={19} /></span>
            <span className="card-kicker">Кратко об анкете</span>
          </div>
          <div className="dashboard-summary-grid">
            <span><small>Вес</small><strong>{pet.weight_kg ?? "—"} кг</strong></span>
            <span><small>Возраст</small><strong>{formatAge(pet.birth_date)}</strong></span>
            <span className="summary-breed"><small>Порода</small><strong>{pet.breed || "Не указана"}</strong></span>
          </div>
          <span className="dashboard-card-link">Все данные питомца <ArrowUpRight size={16} /></span>
        </Link>

        <Link className="card dashboard-ai-card" to="/app/chat">
          <div className="card-topline">
            <span className="icon-box dark"><MessageCircle size={19} /></span>
            <span className="card-kicker">Спросить ИИ</span>
          </div>
          <p className="ai-prompt">Есть вопрос про {pet.name}?</p>
          <span className="input-pill">Сколько корма давать? <ArrowUpRight size={17} /></span>
        </Link>

        <Link className="card dashboard-plus-card" to="/plus">
          <span className="plus-content">
            <span className="plus-mark"><Heart fill="currentColor" size={16} /></span>
            <span>
              <span className="card-kicker">PetSpace Plus</span>
              <strong>Больше заботы<br />для {pet.name}</strong>
            </span>
          </span>
          <span className="button secondary">Узнать больше <ArrowUpRight size={16} /></span>
        </Link>
      </section>
    </main>
  );
}
