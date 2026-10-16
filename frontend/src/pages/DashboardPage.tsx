import { ArrowUpRight, Bell, CalendarDays, Clock3, Heart, MessageCircle, Plus, Scale, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { DogIllustration } from "../components/DogIllustration";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { formatAge, formatDate, statusLabel } from "../lib/format";

export function DashboardPage() {
  const { pet, events } = usePets();
  const nextEvent = [...events].sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())[0];
  const todayLabel = new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });

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
        <section className="card empty-card">
          <p className="muted large">Пока нет профилей. Создайте питомца, чтобы открыть календарь, медкарту и ИИ-чат.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{todayLabel}</p>
          <h1>Привет! Как дела у {pet.name}?</h1>
        </div>
        <PetSwitcher />
      </div>
      <section className="bento-grid dashboard-grid" aria-label="Обзор питомца">
        <article className="card hero-card">
          <div className="hero-copy">
            <span className="soft-label"><Sparkles size={14} /> Всё под контролем</span>
            <h2>Забота о {pet.name}<br />в одном месте</h2>
            <p>Профиль, здоровье и полезные подсказки — всегда под рукой.</p>
            <Link className="button primary" to="/app/pet">Открыть профиль <ArrowUpRight size={17} /></Link>
          </div>
          <DogIllustration />
        </article>

        <article className="card vaccine-card">
          <div className="card-topline"><span className="icon-box lavender"><Bell size={19} /></span><span className="card-kicker">Ближайшее событие</span></div>
          <div className="metric-title">{nextEvent?.title || "Пока пусто"}</div>
          <div className="event-date">
            <CalendarDays size={16} />
            {nextEvent ? formatDate(nextEvent.starts_at) : "Добавьте прививку или визит"}
            {nextEvent && <span>{statusLabel(nextEvent.computed_status)}</span>}
          </div>
        </article>

        <article className="card weight-card">
          <div className="card-topline"><span className="icon-box warm"><Scale size={19} /></span><span className="card-kicker">Вес и возраст</span></div>
          <div className="split-metrics">
            <div><strong>{pet.weight_kg ?? "—"}</strong><span>кг</span></div>
            <div><strong>{formatAge(pet.birth_date)}</strong></div>
          </div>
          <p className="muted">{pet.breed || "Порода не указана"}</p>
        </article>

        <article className="card ai-card">
          <div className="card-topline"><span className="icon-box dark"><MessageCircle size={19} /></span><span className="card-kicker">Спросить ИИ</span></div>
          <p className="ai-prompt">Есть вопрос про {pet.name}?</p>
          <Link className="input-pill" to="/app/chat">Сколько корма давать? <ArrowUpRight size={17} /></Link>
        </article>

        <article className="card plus-card">
          <div className="plus-content">
            <span className="plus-mark"><Heart fill="currentColor" size={16} /></span>
            <div>
              <span className="card-kicker">PetSpace Plus</span>
              <strong>Больше заботы<br />для {pet.name}</strong>
            </div>
          </div>
          <Link className="button secondary" to="/plus">Узнать больше <ArrowUpRight size={16} /></Link>
        </article>

        <article className="card timeline-card">
          <div className="card-heading">
            <div><span className="card-kicker">Календарь</span><h3>Ближайшие дела</h3></div>
            <Link className="circle-button" aria-label="Открыть календарь" to="/app/calendar"><Plus size={19} /></Link>
          </div>
          {events.slice(0, 3).map(event => (
            <div className="timeline-row" key={event.id}>
              <span className={`timeline-dot${event.computed_status === "done" ? " done" : ""}`} />
              <div>
                <strong>{event.title}</strong>
                <span>{formatDate(event.starts_at)} · {statusLabel(event.computed_status)}</span>
              </div>
              <Clock3 size={16} />
            </div>
          ))}
          {!events.length && <p className="muted">Событий пока нет — добавьте первое в календаре.</p>}
        </article>
      </section>
    </main>
  );
}
