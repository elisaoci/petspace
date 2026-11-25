import { useState } from "react";
import { Check, HeartPulse, Link2, Sparkles } from "lucide-react";
import { PetSwitcher } from "../components/PetSwitcher";
import { api } from "../lib/api";

export function PlusPage() {
  const [paid, setPaid] = useState(false);
  const [error, setError] = useState("");

  const activate = async (plan: string, amount: number) => {
    setError("");
    try {
      await api("/payments/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner_id: "demo-owner", plan, amount, currency: "RUB" }),
      });
      setPaid(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось активировать демо-тариф.");
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Подписка</p>
          <h1>PetSpace Plus</h1>
        </div>
        <PetSwitcher />
      </div>
      <p className="lead">Дополнительные инструменты для заботы о питомце.</p>

      <section className="plus-benefits" aria-label="Преимущества Plus">
        <article className="card plus-benefit-card">
          <span className="icon-box lavender"><Sparkles size={20} /></span>
          <span className="card-kicker">Здоровье и уход</span>
          <h2>ИИ-помощник</h2>
          <p>Задавайте вопросы об уходе и питании питомца и получайте ответы с учётом его профиля.</p>
          <span className="benefit-access"><Check size={15} /> Доступен в текущем демо</span>
        </article>
        <article className="card plus-benefit-card">
          <span className="icon-box lavender"><Link2 size={20} /></span>
          <span className="card-kicker">Для визита к ветеринару</span>
          <h2>Медкарта по ссылке</h2>
          <p>Поделитесь основными данными и вакцинациями. Ссылка открывает карту только для просмотра.</p>
          <span className="benefit-access"><Check size={15} /> Ссылка доступна в профиле питомца</span>
        </article>
      </section>

      <section className="plus-plans" aria-label="Условия подписки">
        <article className="card plan-card">
          <span className="card-kicker">Демо-тариф</span>
          <h2>Месяц</h2>
          <strong className="plan-price">199 ₽ <small>/ мес</small></strong>
          <ul className="plan-list">
            <li>Профиль и календарь</li>
            <li>ИИ-помощник</li>
            <li>Медкарта по ссылке</li>
          </ul>
          <button className="button secondary full-button" type="button" onClick={() => activate("monthly", 199)}>
            Выбрать месяц
          </button>
        </article>
        <article className="card plan-card featured">
          <span className="card-kicker">Демо-тариф</span>
          <h2>Год</h2>
          <strong className="plan-price">1 490 ₽ <small>/ год</small></strong>
          <ul className="plan-list">
            <li>Все возможности месяца</li>
            <li>Экономия при оплате за год</li>
            <li>Оплата доступна в демо-режиме</li>
          </ul>
          <button className="button primary full-button" type="button" onClick={() => activate("yearly", 1490)}>
            {paid ? <><Check size={16} /> Plus активен</> : "Подключить Plus"}
          </button>
        </article>
      </section>
      <p className="plus-demo-note"><HeartPulse size={15} /> Демо-оплата не списывает деньги и не сохраняет платёжные данные.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
    </main>
  );
}
