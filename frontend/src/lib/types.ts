export type User = {
  id: number;
  email?: string | null;
  phone?: string | null;
  role: string;
  status: string;
  consents_accepted: boolean;
  has_password: boolean;
  created_at: string;
};

export type ConsentRequirement = {
  kind: string;
  version: string;
};

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
  feedback?: "useful" | "not_useful" | null;
};

export type Reminder = {
  event_id: number;
  pet_id: number;
  pet_name: string;
  title: string;
  event_type: string;
  starts_at: string;
  status: "overdue" | "today" | "soon";
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

export type RecordKind = "visit" | "vaccination" | "lab" | "prescription" | "other";

export type MedicalRecord = {
  id: number;
  pet_id: number;
  kind: RecordKind;
  title: string;
  occurred_at: string;
  clinic_name?: string | null;
  author_type: "owner" | "clinic";
  source: "manual" | "mis";
  description?: string | null;
  diagnosis?: string | null;
  created_at: string;
  updated_at: string;
};

export type AccessGrant = {
  id: number;
  pet_id: number;
  label: string;
  scopes: string[];
  expires_at: string;
  revoked_at?: string | null;
  last_used_at?: string | null;
  created_at: string;
};

export type AccessGrantCreated = AccessGrant & { token: string; url: string };

export type PublicPet = Pet & { age_years?: number | null };

export type PublicAccess = {
  grant: { label: string; scopes: string[]; expires_at: string };
  pet: PublicPet | null;
  records: MedicalRecord[] | null;
  vaccinations: MedicalRecord[] | null;
};
