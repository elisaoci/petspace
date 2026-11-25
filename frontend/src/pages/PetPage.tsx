import { useEffect, useRef, useState } from "react";
import { Check, ImagePlus, Pencil, Upload, X } from "lucide-react";
import { Link } from "react-router-dom";
import { PetSwitcher } from "../components/PetSwitcher";
import { useAuth } from "../context/AuthContext";
import { usePets } from "../context/PetContext";
import { api, mediaUrl } from "../lib/api";
import { formatAge, notePart, speciesLabel } from "../lib/format";
import type { Pet } from "../lib/types";

const photoLimit = 10 * 1024 * 1024;

export function PetPage() {
  const { pet, updatePet } = usePets();
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [species, setSpecies] = useState("dog");
  const [breed, setBreed] = useState("");
  const [sex, setSex] = useState("");
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [allergies, setAllergies] = useState("");
  const [conditions, setConditions] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [photoBusy, setPhotoBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!pet) return;
    setName(pet.name);
    setSpecies(pet.species);
    setBreed(pet.breed || "");
    setSex(pet.sex || "");
    setWeight(pet.weight_kg != null ? String(pet.weight_kg) : "");
    setHeight(pet.height_cm != null ? String(pet.height_cm) : "");
    setBirthDate(pet.birth_date || "");
    setAllergies(notePart(pet.owner_notes, "Аллергии"));
    setConditions(notePart(pet.owner_notes, "Заболевания"));
    setNotes((pet.owner_notes || "").split("\n").filter(line =>
      !line.startsWith("Аллергии:") && !line.startsWith("Заболевания:"),
    ).join("\n").trim());
    setEditing(false);
    setError("");
  }, [pet]);

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
          <div><h1>Создайте анкету питомца</h1></div>
          <PetSwitcher />
        </div>
        <section className="card empty-card">
          <p className="muted large">Добавьте профиль, чтобы хранить основные данные и заметки о здоровье.</p>
        </section>
      </main>
    );
  }

  const save = async () => {
    setError("");
    try {
      const ownerNotes = [
        allergies.trim() && `Аллергии: ${allergies.trim()}`,
        conditions.trim() && `Заболевания: ${conditions.trim()}`,
        notes.trim(),
      ].filter(Boolean).join("\n");
      const updated = await api<Pet>(`/pets/${pet.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() || pet.name,
          species,
          breed: breed.trim() || null,
          sex: sex || null,
          weight_kg: weight ? Number(weight) : null,
          height_cm: height ? Number(height) : null,
          birth_date: birthDate || null,
          owner_notes: ownerNotes || null,
        }),
      });
      updatePet(updated);
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить анкету.");
    }
  };

  const uploadPhoto = async (file?: File) => {
    if (!file) return;
    setError("");
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("Поддерживаются только изображения JPG, PNG и WebP.");
      return;
    }
    if (file.size > photoLimit) {
      setError("Размер фотографии не должен превышать 10 МБ.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    setPhotoBusy(true);
    try {
      updatePet(await api<Pet>(`/pets/${pet.id}/photo`, { method: "POST", body: form }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить фотографию.");
    } finally {
      setPhotoBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <h1>{pet.name}</h1>
        </div>
        <div className="pet-controls">
          <PetSwitcher />
          {editing ? (
            <>
              <button className="button primary" type="button" onClick={save}><Check size={16} /> Сохранить</button>
              <button className="button secondary" type="button" onClick={() => { setEditing(false); setError(""); }}>
                <X size={16} /> Отмена
              </button>
            </>
          ) : (
            <button className="button primary" type="button" onClick={() => setEditing(true)}><Pencil size={16} /> Редактировать</button>
          )}
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="pet-profile-layout">
        <section className="card pet-profile-card">
          <div className="pet-profile-photo">
            {pet.photo_url
              ? <img src={mediaUrl(pet.photo_url)} alt={`Фото ${pet.name}`} />
              : <div className="photo-placeholder"><ImagePlus size={32} /><span>Добавьте фото питомца</span></div>}
            <input
              ref={fileRef}
              className="visually-hidden"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={event => uploadPhoto(event.target.files?.[0])}
            />
            <button className="button secondary photo-upload-button" type="button" onClick={() => fileRef.current?.click()} disabled={photoBusy}>
              <Upload size={15} /> {photoBusy ? "Загружаем…" : pet.photo_url ? "Изменить фото" : "Загрузить фото"}
            </button>
          </div>
          <div className="pet-profile-summary">
            <span className="soft-label">{speciesLabel(pet.species)}</span>
            <h2>{pet.name}</h2>
            <p className="muted large">{pet.breed || "Порода не указана"}</p>
            <div className="profile-facts">
              <span><strong>{pet.weight_kg ?? "—"} кг</strong>Вес</span>
              <span><strong>{pet.height_cm ?? "—"} см</strong>Рост</span>
              <span><strong>{formatAge(pet.birth_date)}</strong>Возраст</span>
            </div>
          </div>
        </section>

        <section className="card pet-form-card">
          <div className="pet-section-heading">
            <span className="card-kicker">01 · Основные данные</span>
            <h3>О питомце</h3>
          </div>
          <div className="pet-fields-grid">
            <label className="field-label">Кличка
              <input className="text-input" value={editing ? name : pet.name} disabled={!editing} onChange={event => setName(event.target.value)} />
            </label>
            <label className="field-label">Вид
              <select className="text-input" value={editing ? species : pet.species} disabled={!editing} onChange={event => setSpecies(event.target.value)}>
                <option value="dog">Собака</option><option value="cat">Кошка</option><option value="other">Другое</option>
              </select>
            </label>
            <label className="field-label">Порода
              <input className="text-input" value={editing ? breed : pet.breed || ""} disabled={!editing} placeholder="Не указана" onChange={event => setBreed(event.target.value)} />
            </label>
            <label className="field-label">Пол
              <select className="text-input" value={editing ? sex : pet.sex || ""} disabled={!editing} onChange={event => setSex(event.target.value)}>
                <option value="">Не указан</option><option value="male">Самец</option><option value="female">Самка</option>
              </select>
            </label>
            <label className="field-label">Дата рождения
              <input className="text-input" type="date" value={editing ? birthDate : pet.birth_date || ""} disabled={!editing} onChange={event => setBirthDate(event.target.value)} />
            </label>
            <label className="field-label">Вес, кг
              <input className="text-input" type="number" min="0" step="0.1" value={editing ? weight : pet.weight_kg ?? ""} disabled={!editing} onChange={event => setWeight(event.target.value)} />
            </label>
            <label className="field-label">Рост, см
              <input className="text-input" type="number" min="0" step="0.1" value={editing ? height : pet.height_cm ?? ""} disabled={!editing} onChange={event => setHeight(event.target.value)} />
            </label>
          </div>
        </section>

        <section className="card pet-form-card pet-health-card">
          <div className="pet-section-heading">
            <span className="card-kicker">02 · Медицина</span>
            <h3>Здоровье и заметки</h3>
          </div>
          <div className="pet-fields-grid">
            <label className="field-label">Аллергии
              <input className="text-input" value={editing ? allergies : notePart(pet.owner_notes, "Аллергии")} disabled={!editing} placeholder="Не указаны" onChange={event => setAllergies(event.target.value)} />
            </label>
            <label className="field-label">Хронические заболевания
              <input className="text-input" value={editing ? conditions : notePart(pet.owner_notes, "Заболевания")} disabled={!editing} placeholder="Не указаны" onChange={event => setConditions(event.target.value)} />
            </label>
            <label className="field-label notes-field">Заметки владельца
              <textarea
                className="text-input notes-input"
                value={editing ? notes : (pet.owner_notes || "").split("\n").filter(line =>
                  !line.startsWith("Аллергии:") && !line.startsWith("Заболевания:"),
                ).join("\n").trim()}
                disabled={!editing}
                placeholder="Особенности ухода, важные наблюдения…"
                onChange={event => setNotes(event.target.value)}
              />
            </label>
          </div>
          <p className="muted">Записи о прививках и визитах можно добавить в календаре.</p>
          <Link className="button secondary" to="/app/calendar">Открыть календарь</Link>
        </section>
        <section className="card pet-form-card pet-owner-card">
          <div className="pet-section-heading">
            <span className="card-kicker">03 · Владелец</span>
            <h3>{user?.full_name || "ФИО не указано"}</h3>
          </div>
          <p className="muted">Имя владельца берётся из профиля аккаунта и применяется ко всем анкетам питомцев.</p>
          <Link className="button secondary" to="/app/settings">Изменить ФИО в настройках</Link>
        </section>
      </div>
    </main>
  );
}
