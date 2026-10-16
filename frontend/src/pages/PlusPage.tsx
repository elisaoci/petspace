import { useState } from "react";
import { Check } from "lucide-react";
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
      <p className="lead">Демо-оплата: номер карты не вводится и не сохраняется. Это визуализация тарифов, не настоящий платёж.</p>
      <div className="plans">
        <section className="card plan-card">
          <span className="card-kicker">Помощь рядом</span>
          <h2>Месяц</h2>
          <strong className="plan-price">199 ₽ <small>/ мес</small></strong>
          <ul className="plan-list">
            <li>Календарь и напоминания</li>
            <li>Профиль и медкарта</li>
            <li>ИИ-помощник</li>
          </ul>
          <button className="button secondary full-button" type="button" onClick={() => activate("monthly", 199)}>Выбрать месяц</button>
        </section>
        <section className="card plan-card featured">
          <span className="plan-badge">Выгоднее</span>
          <span className="card-kicker">Лучший выбор</span>
          <h2>Год</h2>
          <strong className="plan-price">1 490 ₽ <small>/ год</small></strong>
          <ul className="plan-list">
            <li>Всё из месячного тарифа</li>
            <li>Приоритетная поддержка в демо</li>
            <li>Два месяца в подарок</li>
          </ul>
          <button className="button primary full-button" type="button" onClick={() => activate("yearly", 1490)}>
            {paid ? <><Check size={16} /> Plus активен</> : "Подключить Plus"}
          </button>
        </section>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <section className="card payment-card">
        <div className="card-heading">
          <div>
            <span className="card-kicker">Демо-оплата</span>
            <h3>Безопасная визуализация карты</h3>
          </div>
          <span className="demo-badge">ДАННЫЕ НЕ СОХРАНЯЮТСЯ</span>
        </div>
        <div className="fake-card">
          <span>PetSpace Plus</span>
          <strong>••••  ••••  ••••  4242</strong>
          <small>Тестовая карта</small>
        </div>
      </section>
    </main>
  );
}
