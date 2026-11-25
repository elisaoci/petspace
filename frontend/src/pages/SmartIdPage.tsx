import { useState } from "react";
import { AccessPanel } from "../components/AccessPanel";
import { RecordsPanel } from "../components/RecordsPanel";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { Link } from "react-router-dom";

type Tab = "records" | "access";

export function SmartIdPage() {
  const { pet } = usePets();
  const [tab, setTab] = useState<Tab>("records");

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
          <div><h1>Медкарта питомца</h1></div>
          <PetSwitcher />
        </div>
        <section className="card empty-card">
          <p className="muted large">Сначала создайте анкету питомца.</p>
          <Link className="button primary" to="/app/pet">Перейти к питомцу</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="content">
      <div className="page-heading">
        <div><h1>Smart ID · Медкарта питомца</h1></div>
        <PetSwitcher />
      </div>
      <p className="lead">
        Ведите историю приёмов и прививок, выдавайте клинике ограниченный по сроку доступ и
        отзывайте ссылку в любой момент. Клиника по ссылке может только просматривать карту.
      </p>

      <div className="segmented smartid-tabs" role="tablist" aria-label="Разделы Smart ID">
        <button type="button" role="tab" aria-selected={tab === "records"} className={tab === "records" ? "active" : ""} onClick={() => setTab("records")}>
          Записи
        </button>
        <button type="button" role="tab" aria-selected={tab === "access"} className={tab === "access" ? "active" : ""} onClick={() => setTab("access")}>
          Доступы клиник
        </button>
      </div>

      <div className="smartid-panel">
        {tab === "records" ? <RecordsPanel /> : <AccessPanel />}
      </div>
    </main>
  );
}
