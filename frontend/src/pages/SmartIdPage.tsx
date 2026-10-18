import { useState } from "react";
import { AccessPanel } from "../components/AccessPanel";
import { AppointmentsPanel } from "../components/AppointmentsPanel";
import { RecordsPanel } from "../components/RecordsPanel";
import { PetSwitcher } from "../components/PetSwitcher";

type Tab = "records" | "access" | "appointments";

export function SmartIdPage() {
  const [tab, setTab] = useState<Tab>("records");

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Smart-ID</p>
          <h1>Медкарта питомца</h1>
        </div>
        <PetSwitcher />
      </div>
      <p className="lead">
        История приёмов, прививок, анализов и назначений в одном месте. Каждая запись помечена
        источником, а доступ к карте выдаётся по ссылке и отзывается в любой момент.
      </p>

      <div className="segmented" role="tablist" aria-label="Разделы Smart-ID">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "records"}
          className={tab === "records" ? "active" : ""}
          onClick={() => setTab("records")}
        >
          Записи
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "access"}
          className={tab === "access" ? "active" : ""}
          onClick={() => setTab("access")}
        >
          Доступы клиник
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "appointments"}
          className={tab === "appointments" ? "active" : ""}
          onClick={() => setTab("appointments")}
        >
          Запись на приём
        </button>
      </div>

      <div className="smartid-panel">
        {tab === "records" ? <RecordsPanel /> : tab === "access" ? <AccessPanel /> : <AppointmentsPanel />}
      </div>
    </main>
  );
}
