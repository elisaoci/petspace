import { ApiError, authorizedFetch } from "./api";

export type ClinicStatus = "pending" | "approved" | "rejected" | "suspended";

export type Clinic = {
  id: number;
  name: string;
  inn: string;
  address: string;
  phone: string;
  email: string | null;
  status: ClinicStatus;
  status_reason: string | null;
  created_at: string;
};

export type ClinicDocument = { id: number; title: string; filename: string; content_type: string; size_bytes: number; created_at: string };

export const STATUS_LABELS: Record<ClinicStatus, string> = {
  pending: "На проверке",
  approved: "Подтверждена",
  rejected: "Отклонена",
  suspended: "Приостановлена",
};

export const ROLE_LABELS: Record<string, string> = { clinic_admin: "Администратор", clinic_doctor: "Врач", clinic_registrar: "Регистратор" };

export const formatSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;

export const formatDate = (iso: string) => new Date(iso).toLocaleDateString("ru-RU");

/** Текст ошибки для пользователя: у ошибок валидации собираем сообщения по полям. */
export function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError && Array.isArray(error.detail)) {
    const messages = error.detail
      .map(item => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg).replace(/^Value error, /, "") : ""))
      .filter(Boolean);
    if (messages.length) return messages.join(". ");
  }
  return error instanceof Error ? error.message : fallback;
}

/** Файлы отдаются только с токеном, поэтому ссылкой <a href> их не скачать: берём blob и сохраняем. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await authorizedFetch(path);
  if (!response.ok) throw new Error("Не удалось скачать файл.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
