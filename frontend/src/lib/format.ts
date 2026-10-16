const speciesLabels: Record<string, string> = {
  dog: "Собака",
  cat: "Кошка",
  other: "Другое",
};

export function speciesLabel(species?: string | null) {
  if (!species) return "Питомец";
  return speciesLabels[species] || species;
}

export function ageFromBirthDate(birthDate?: string | null) {
  if (!birthDate) return null;
  const birth = new Date(birthDate);
  if (Number.isNaN(birth.getTime())) return null;
  const today = new Date();
  let years = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) years -= 1;
  return Math.max(0, years);
}

export function formatAge(birthDate?: string | null) {
  const years = ageFromBirthDate(birthDate);
  if (years === null) return "—";
  const mod10 = years % 10;
  const mod100 = years % 100;
  if (mod10 === 1 && mod100 !== 11) return `${years} год`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${years} года`;
  return `${years} лет`;
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    planned: "запланировано",
    overdue: "просрочено",
    done: "выполнено",
    cancelled: "отменено",
  };
  return labels[status] || status;
}

export function notePart(notes: string | undefined | null, label: string) {
  if (!notes) return "";
  const line = notes.split("\n").find(item => item.startsWith(`${label}:`));
  return line ? line.slice(label.length + 1).trim() : "";
}
