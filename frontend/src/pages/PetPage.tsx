import { useEffect, useRef, useState } from "react";
import { Check, Heart, MessageCircle, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { DogIllustration } from "../components/DogIllustration";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { api, authorizedFetch, mediaUrl } from "../lib/api";
import { formatAge, notePart, speciesLabel } from "../lib/format";
import type { Pet } from "../lib/types";

export function PetPage() {
  const { pet, updatePet } = usePets();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [breed, setBreed] = useState("");
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [allergies, setAllergies] = useState("");
  const [conditions, setConditions] = useState("");
  const [photoName, setPhotoName] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!pet) return;
    setName(pet.name);
    setBreed(pet.breed || "");
    setWeight(pet.weight_kg != null ? String(pet.weight_kg) : "");
    setHeight(pet.height_cm != null ? String(pet.height_cm) : "");
    setBirthDate(pet.birth_date || "");
    setAllergies(notePart(pet.owner_notes, "Аллергии"));
    setConditions(notePart(pet.owner_notes, "Заболевания"));
  }, [pet]);

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
          <div><p className="eyebrow">Профиль</p><h1>Сначала добавьте питомца</h1></div>
          <PetSwitcher />
        </div>
      </main>
    );
  }

  const save = async () => {
    setError("");
    try {
      const notes = [allergies && `Аллергии: ${allergies}`, conditions && `Заболевания: ${conditions}`].filter(Boolean).join("\n");
      const updated = await api<Pet>(`/pets/${pet.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() || pet.name,
          breed: breed.trim() || null,
          weight_kg: weight ? Number(weight) : null,
          height_cm: height ? Number(height) : null,
          birth_date: birthDate || null,
          owner_notes: notes || null,
        }),
      });
      updatePet(updated);
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить профиль.");
    }
  };

  const copyCard = async () => {
    if (!pet.medical_secret_token) return;
    const url = `${window.location.origin}/medical/${pet.medical_secret_token}`;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Профиль питомца</p>
          <h1>{pet.name} — ваш лучший друг</h1>
        </div>
        <div className="pet-controls">
          <PetSwitcher />
          <button className="button primary" type="button" onClick={() => (editing ? save() : setEditing(true))}>
            {editing ? <><Check size={16} /> Сохранить</> : "Редактировать"}
          </button>
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-layout">
        <section className="card profile-card">
          <div className="profile-visual">
            {pet.photo_url ? <img className="pet-photo" src={mediaUrl(pet.photo_url)} alt={`Фото ${pet.name}`} /> : <DogIllustration />}
            <input
              ref={fileRef}
              className="visually-hidden"
              type="file"
              accept="image/*"
              onChange={async event => {
                const file = event.target.files?.[0];
                if (!file) return;
                setPhotoName(file.name);
                const form = new FormData();
                form.append("file", file);
                const response = await authorizedFetch(`/pets/${pet.id}/photo`, { method: "POST", body: form });
                if (response.ok) updatePet(await response.json());
              }}
            />
            <button className="avatar-upload" type="button" onClick={() => fileRef.current?.click()}>
              <Upload size={16} /> {photoName ? "Фото выбрано" : "Загрузить фото"}
            </button>
          </div>
          <div>
            <span className="soft-label">{speciesLabel(pet.species)}</span>
            {editing ? <input className="text-input" value={name} onChange={event => setName(event.target.value)} /> : <h2>{pet.name}</h2>}
            {editing ? (
              <label className="field-label">Порода<input className="text-input" value={breed} onChange={event => setBreed(event.target.value)} /></label>
            ) : (
              <p className="muted large">{pet.breed || "Порода не указана"}</p>
            )}
            <div className="profile-facts">
              <span>
                <strong>{editing ? <input className="text-input compact" type="number" value={weight} onChange={event => setWeight(event.target.value)} /> : `${pet.weight_kg ?? "—"} кг`}</strong>
                вес
              </span>
              <span>
                <strong>{editing ? <input className="text-input compact" type="number" value={height} onChange={event => setHeight(event.target.value)} /> : `${pet.height_cm ?? "—"} см`}</strong>
                рост
              </span>
              <span>
                <strong>{editing ? <input className="text-input compact" type="date" value={birthDate} onChange={event => setBirthDate(event.target.value)} /> : formatAge(pet.birth_date)}</strong>
                возраст
              </span>
            </div>
          </div>
        </section>
        <section className="card info-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">Здоровье</span>
              <h3>Важная информация</h3>
            </div>
            <Link className="icon-action" aria-label="Спросить ИИ о здоровье" to="/app/chat"><Heart size={20} color="#8e7cc3" /></Link>
          </div>
          <label className="field-label">Аллергии<input className="text-input" disabled={!editing} value={allergies} onChange={event => setAllergies(event.target.value)} placeholder="Не указаны" /></label>
          <label className="field-label">Хронические заболевания<input className="text-input" disabled={!editing} value={conditions} onChange={event => setConditions(event.target.value)} placeholder="Не указаны" /></label>
          <button className="button secondary" type="button" onClick={copyCard}>
            {copied ? "Ссылка скопирована" : "Скопировать ссылку на медкарту"}
          </button>
          <Link className="button secondary" to="/app/chat">Спросить ИИ о здоровье <MessageCircle size={16} /></Link>
        </section>
      </div>
    </main>
  );
}
