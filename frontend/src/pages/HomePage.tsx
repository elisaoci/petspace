import { ArrowRight, CalendarDays, HeartPulse, PawPrint, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const features = [
  {
    icon: PawPrint,
    title: "Профиль питомца",
    text: "Имя, порода, вес, рост, фотографии и заметки о здоровье — всё в одном месте.",
    note: "Важные данные всегда под рукой.",
  },
  {
    icon: CalendarDays,
    title: "Календарь заботы",
    text: "Прививки, обработки и визиты. Напоминания о событиях, которые нельзя пропускать.",
    note: "Планы и история событий в одном календаре.",
  },
  {
    icon: Sparkles,
    title: "ИИ-помощник",
    text: "Локальный помощник, который отвечает на вопросы о здоровье, уходе и питании питомца.",
    note: "Информация для заботы, не замена ветеринару.",
  },
  {
    icon: ShieldCheck,
    title: "Медкарта по ссылке",
    text: "Секретная ссылка для клиники: прививки и основные данные питомца без личных заметок владельца.",
    note: "По ссылке доступен только просмотр медкарты.",
  },
];

const steps = [
  ["Создайте профиль", "Добавьте питомца, фотографию и основные данные о его здоровье."],
  ["Заполните календарь", "Добавьте прививки, обработки, визиты к ветеринару и другие события."],
  ["Спросите помощника", "Задайте вопрос об уходе и здоровье выбранного питомца."],
  ["Поделитесь с клиникой", "Передайте основные данные по защищённой ссылке для просмотра."],
];

export function HomePage() {
  const { user } = useAuth();

  return (
    <main className="landing-page">
      <section className="content landing-hero">
        <div className="landing-intro">
          <p className="eyebrow"><HeartPulse size={15} /> Для заботливых владельцев</p>
          <h1>PetSpace</h1>
          <p className="landing-subtitle">Забота о вашем питомце в одном приложении.</p>
          <Link className="button outline-button" to={user ? "/app" : "/login"}>
            Открыть кабинет <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      <section className="content landing-section" id="features">
        <div className="landing-section-heading">
          <p className="eyebrow">Всё для заботы</p>
          <h2>Главное о питомце — в одном месте</h2>
        </div>
        <div className="feature-surface">
          <div className="landing-features">
            {features.map(({ icon: Icon, title, text, note }) => (
              <article className="feature-card" key={title}>
                <span className="icon-box lavender"><Icon size={18} /></span>
                <h3>{title}</h3>
                <p>{text}</p>
                <span className="feature-note">{note}</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="content landing-section">
        <div className="landing-section-heading">
          <p className="eyebrow">Как пользоваться</p>
          <h2>Четыре простых шага</h2>
        </div>
        <div className="steps-grid">
          {steps.map(([title, text], index) => (
            <article className="step-card" key={title}>
              <span className="step-number">{index + 1}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
