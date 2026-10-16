import { useState } from "react";
import { Check, ChevronDown, Plus } from "lucide-react";
import { usePets } from "../context/PetContext";
import { api } from "../lib/api";
import type { Pet } from "../lib/types";
import { DogIllustration } from "./DogIllustration";

export function PetSwitcher() {
  const { pets, selectedPetId, setSelectedPetId, reloadPets } = usePets();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [species, setSpecies] = useState("dog");
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [error, setError] = useState("");

  const addPet = async () => {
    if (!name.trim()) {
      setError("Укажите имя питомца.");
      return;
    }
    try {
      const created = await api<Pet>("/pets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          species,
          weight_kg: weight ? Number(weight) : null,
          height_cm: height ? Number(height) : null,
        }),
      });
      await reloadPets();
      setSelectedPetId(created.id);
      setName("");
      setWeight("");
      setHeight("");
      setShowForm(false);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось создать профиль.");
    }
  };

  return (
    <div className="pet-controls">
      <label className="pet-switcher">
        <span className="mini-avatar"><DogIllustration /></span>
        <select aria-label="Выбрать питомца" value={selectedPetId ?? ""} onChange={event => setSelectedPetId(Number(event.target.value))}>
          {pets.map(pet => <option key={pet.id} value={pet.id}>{pet.name}</option>)}
          {!pets.length && <option value="">Нет питомцев</option>}
        </select>
        <ChevronDown size={16} />
      </label>
      <button className="button secondary add-pet-button" type="button" onClick={() => setShowForm(true)}>
        <Plus size={16} /> Добавить
      </button>
      {showForm && (
        <div className="modal-backdrop" role="presentation" onClick={() => setShowForm(false)}>
          <div className="modal-card" role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}>
            <div className="card-heading">
              <h3>Новый питомец</h3>
              <button className="icon-action" aria-label="Закрыть" type="button" onClick={() => setShowForm(false)}>×</button>
            </div>
            <label className="field-label">Имя<input className="text-input" value={name} onChange={event => setName(event.target.value)} placeholder="Например, Луна" /></label>
            <label className="field-label">Вид
              <select className="text-input" value={species} onChange={event => setSpecies(event.target.value)}>
                <option value="dog">Собака</option>
                <option value="cat">Кошка</option>
                <option value="other">Другое</option>
              </select>
            </label>
            <label className="field-label">Вес, кг<input className="text-input" type="number" min="0" step="0.1" value={weight} onChange={event => setWeight(event.target.value)} /></label>
            <label className="field-label">Рост, см<input className="text-input" type="number" min="0" step="0.1" value={height} onChange={event => setHeight(event.target.value)} /></label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button primary full-button" type="button" onClick={addPet}><Check size={16} /> Создать профиль</button>
          </div>
        </div>
      )}
    </div>
  );
}
