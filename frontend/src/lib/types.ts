export type Pet = {
  id: number;
  name: string;
  species: string;
  breed?: string | null;
  birth_date?: string | null;
  sex?: string | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  owner_notes?: string | null;
  photo_url?: string | null;
  medical_secret_token?: string;
};

export type CalendarEvent = {
  id: number;
  pet_id: number;
  title: string;
  description?: string | null;
  event_type: string;
  starts_at: string;
  ends_at?: string | null;
  status: string;
  computed_status: string;
};

export type ChatHistoryItem = {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type PublicMedicalCard = {
  id: number;
  name: string;
  species: string;
  breed?: string | null;
  birth_date?: string | null;
  sex?: string | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  photo_url?: string | null;
  age_years?: number | null;
  vaccinations: { title: string; date: string; status: string }[];
};
