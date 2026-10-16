import { ArrowUpRight, CalendarDays, Heart, MessageCircle, PawPrint, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { DogIllustration } from "../components/DogIllustration";

const features = [
  {
    icon: PawPrint,
    title: "Профиль питомца",
    text: "Имя, порода, вес, рост, фото и заметки о здоровье — всё в одном месте.",
  },
  {
    icon: CalendarDays,
    title: "Календарь заботы",
    text: "Прививки, обработки и визиты. Просроченные события подсвечиваются сами.",
  },
  {
    icon: MessageCircle,
    title: "ИИ-помощник",
    text: "Локальные ответы по уходу и кормлению с учётом данных питомца. Без диагнозов.",
  },
  {
    icon: ShieldCheck,
    title: "Медкарта по ссылке",
    text: "Секретная ссылка для клиники: прививки и основные данные, без личных заметок.",
  },
];

export function HomePage() {
  return (
    <main>
      <section className="content landing-hero">
        <div className="card hero-card landing-hero-card">
          <div className="hero-copy">
            <span className="soft-label"><Heart size={14} /> Для владельцев собак и кошек</span>
            <h1>Забота о питомце в одном спокойном месте</h1>
            <p>PetSpace — сайт, где хранится профиль, календарь здоровья и осторожный ИИ-помощник. Без ленты, без шума, только то, что нужно каждый день.</p>
            <div className="hero-actions">
              <Link className="button primary" to="/app">Открыть кабинет <ArrowUpRight size={17} /></Link>
              <a className="button secondary" href="#features">Как это устроено</a>
            </div>
          </div>
          <DogIllustration />
        </div>
      </section>

      <section className="content" id="features">
        <div className="page-heading">
          <div>
            <p className="eyebrow">Возможности</p>
            <h2>Сайт, а не набор разрозненных заметок</h2>
          </div>
        </div>
        <div className="bento-grid landing-features">
          {features.map(feature => (
            <article className="card" key={feature.title}>
              <span className="icon-box lavender"><feature.icon size={19} /></span>
              <h3>{feature.title}</h3>
              <p className="muted large">{feature.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="content">
        <div className="page-heading">
          <div>
            <p className="eyebrow">Как пользоваться</p>
            <h2>Три шага</h2>
          </div>
        </div>
        <div className="steps-grid">
          <article className="card"><span className="step-number">1</span><h3>Создайте профиль</h3><p className="muted">Добавьте питомца, фото и важные пометки: аллергии, вес, рост.</p></article>
          <article className="card"><span className="step-number">2</span><h3>Заполните календарь</h3><p className="muted">Прививки и обработки появятся в кабинете и напомнят о себе.</p></article>
          <article className="card"><span className="step-number">3</span><h3>Спросите помощника</h3><p className="muted">ИИ отвечает по-русски и всегда напоминает, что это не замена врачу.</p></article>
        </div>
      </section>

      <section className="content landing-cta">
        <article className="card plus-card">
          <div className="plus-content">
            <span className="plus-mark"><Heart fill="currentColor" size={16} /></span>
            <div>
              <span className="card-kicker">PetSpace Plus</span>
              <strong>Больше спокойствия для вас и питомца</strong>
            </div>
          </div>
          <Link className="button secondary" to="/plus">Смотреть тарифы <ArrowUpRight size={16} /></Link>
        </article>
      </section>
    </main>
  );
}
