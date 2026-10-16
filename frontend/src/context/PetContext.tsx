import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import type { CalendarEvent, Pet } from "../lib/types";
import { useAuth } from "./AuthContext";

type PetContextValue = {
  pets: Pet[];
  events: CalendarEvent[];
  selectedPetId: number | null;
  pet: Pet | null;
  setSelectedPetId: (id: number) => void;
  reloadPets: () => Promise<Pet[]>;
  reloadEvents: () => Promise<void>;
  updatePet: (pet: Pet) => void;
};

const PetContext = createContext<PetContextValue | null>(null);

export function PetProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [pets, setPets] = useState<Pet[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [selectedPetId, setSelectedPetId] = useState<number | null>(null);

  const reloadPets = async () => {
    const value = await api<Pet[]>("/pets").catch(() => [] as Pet[]);
    setPets(value);
    setSelectedPetId(current => {
      if (current && value.some(item => item.id === current)) return current;
      return value[0]?.id ?? null;
    });
    return value;
  };

  const reloadEvents = async () => {
    if (!selectedPetId) {
      setEvents([]);
      return;
    }
    const value = await api<CalendarEvent[]>(`/events?pet_id=${selectedPetId}`).catch(() => [] as CalendarEvent[]);
    setEvents(value);
  };

  useEffect(() => {
    // Данные грузим только после входа, а при выходе очищаем: чужой сессии здесь быть не должно.
    if (!user) {
      setPets([]);
      setEvents([]);
      setSelectedPetId(null);
      return;
    }
    reloadPets().catch(() => undefined);
  }, [user]);

  useEffect(() => {
    reloadEvents().catch(() => undefined);
  }, [selectedPetId]);

  const pet = useMemo(() => pets.find(item => item.id === selectedPetId) ?? pets[0] ?? null, [pets, selectedPetId]);

  const updatePet = (next: Pet) => {
    setPets(current => current.map(item => (item.id === next.id ? next : item)));
  };

  return (
    <PetContext.Provider value={{ pets, events, selectedPetId: pet?.id ?? null, pet, setSelectedPetId, reloadPets, reloadEvents, updatePet }}>
      {children}
    </PetContext.Provider>
  );
}

export function usePets() {
  const value = useContext(PetContext);
  if (!value) throw new Error("usePets must be used inside PetProvider");
  return value;
}
