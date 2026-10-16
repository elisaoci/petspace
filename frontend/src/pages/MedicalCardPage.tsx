import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { DogIllustration } from "../components/DogIllustration";
import { api, mediaUrl } from "../lib/api";
import { formatAge, formatDate, speciesLabel } from "../lib/format";
import type { PublicMedicalCard } from "../lib/types";

export function MedicalCardPage() {
  const { token } = useParams();
  const [card, setCard] = useState<PublicMedicalCard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    api<PublicMedicalCard>(`/pets/public/medical-card/${token}`)
      .then(setCard)
      .catch(() => setError("Медкарта не найдена или ссылка устарела."));
  }, [token]);

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Публичная медкарта</p>
          <h1>{card ? card.name : "Карта питомца"}</h1>
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {card && (
        <div className="form-layout">
          <section className="card profile-card">
            <div className="profile-visual">
              {card.photo_url ? <img className="pet-photo" src={mediaUrl(card.photo_url)} alt={`Фото ${card.name}`} /> : <DogIllustration />}
            </div>
            <div>
              <span className="soft-label">{speciesLabel(card.species)}</span>
              <h2>{card.name}</h2>
              <p className="muted large">{card.breed || "Порода не указана"}</p>
              <div className="profile-facts">
                <span><strong>{card.weight_kg ?? "—"} кг</strong>вес</span>
                <span><strong>{card.height_cm ?? "—"} см</strong>рост</span>
                <span><strong>{card.age_years != null ? `${card.age_years}` : formatAge(card.birth_date)}</strong>возраст</span>
              </div>
            </div>
          </section>
          <section className="card">
            <span className="card-kicker">Прививки</span>
            <h3>Вакцинации</h3>
            {card.vaccinations.length ? card.vaccinations.map(item => (
              <div className="event-item" key={`${item.title}-${item.date}`}>
                <span className="event-bullet lavender-dot" />
                <div>
                  <strong>{item.title}</strong>
                  <span>{formatDate(item.date)} · {item.status}</span>
                </div>
              </div>
            )) : <p className="muted">Записей о вакцинации пока нет.</p>}
            <p className="disclaimer">Личные заметки владельца в эту карту не входят.</p>
          </section>
        </div>
      )}
    </main>
  );
}
