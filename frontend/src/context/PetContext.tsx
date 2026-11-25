import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import type { CalendarEvent, Pet } from "../lib/types";
import { useAuth } from "./AuthContext";

type PetContextValue = {
  pets: Pet[];
  events: CalendarEvent[];
  selectedPetId: number | null;
  pet: Pet | null;
  notificationsEnabled: boolean;
  setSelectedPetId: (id: number) => void;
  setNotificationsEnabled: (enabled: boolean) => void;
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
  const [notificationsEnabled, setNotificationsEnabled] = useState(
    () => typeof Notification !== "undefined" && Notification.permission === "granted",
  );
  const sentReminders = useRef(new Set<string>());

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

  const pet = useMemo(() => pets.find(item => item.id === selectedPetId) ?? pets[0] ?? null, [pets, selectedPetId]);

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

  useEffect(() => {
    if (!notificationsEnabled || !pet) return;
    const now = Date.now();
    const timers: number[] = [];

    events.forEach(event => {
      if (event.computed_status === "done" || event.computed_status === "cancelled") return;
      const eventTime = new Date(event.starts_at).getTime();
      if (!Number.isFinite(eventTime) || eventTime <= now) return;

      [7, 3, 1, 0].forEach(daysBefore => {
        const reminderTime = eventTime - daysBefore * 24 * 60 * 60 * 1000;
        const delay = reminderTime - Date.now();
        if (delay < -24 * 60 * 60 * 1000) return;

        const key = `petspace-reminder-${pet.id}-${event.id}-${eventTime}-${daysBefore}`;
        if (sentReminders.current.has(key)) return;
        try {
          if (localStorage.getItem(key)) {
            sentReminders.current.add(key);
            return;
          }
        } catch (caught) {
          console.error("Не удалось проверить сохранённые напоминания", caught);
        }

        const showReminder = () => {
          if (Date.now() < reminderTime) {
            timers.push(window.setTimeout(showReminder, Math.min(reminderTime - Date.now(), 2_147_000_000)));
            return;
          }
          if (Date.now() >= eventTime || Notification.permission !== "granted") return;

          const body = daysBefore === 0
            ? `Сегодня: ${event.title}`
            : daysBefore === 1
              ? `Завтра: ${event.title}`
              : `Через ${daysBefore} дней: ${event.title}`;
          try {
            new Notification(`Напоминание для ${pet.name}`, { body });
            sentReminders.current.add(key);
            try {
              localStorage.setItem(key, "1");
            } catch (caught) {
              console.error("Не удалось сохранить статус напоминания", caught);
            }
          } catch (caught) {
            console.error("Не удалось показать браузерное напоминание", caught);
            setNotificationsEnabled(false);
          }
        };

        timers.push(window.setTimeout(showReminder, Math.max(delay, 0)));
      });
    });

    return () => timers.forEach(timer => window.clearTimeout(timer));
  }, [events, notificationsEnabled, pet]);

  const updatePet = (next: Pet) => {
    setPets(current => current.map(item => (item.id === next.id ? next : item)));
  };

  return (
    <PetContext.Provider value={{ pets, events, selectedPetId: pet?.id ?? null, pet, notificationsEnabled, setSelectedPetId, setNotificationsEnabled, reloadPets, reloadEvents, updatePet }}>
      {children}
    </PetContext.Provider>
  );
}

export function usePets() {
  const value = useContext(PetContext);
  if (!value) throw new Error("usePets must be used inside PetProvider");
  return value;
}
