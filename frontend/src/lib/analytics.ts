/**
 * Аналитика экранов: только имя события и путь.
 *
 * Никакого содержимого медкарты и переписки здесь нет. События копятся в памяти
 * и уходят пачками; при выходе из аккаунта очередь очищается.
 */

import { api, getAccessToken } from "./api";

type ScreenEvent = { name: string; path: string; occurred_at: string };

const MAX_BATCH = 20;
const FLUSH_AFTER = 5;

let queue: ScreenEvent[] = [];
let flushing = false;

export function track(name: string, path?: string): void {
  // Без сессии события не отправляем: эндпоинт требует авторизации.
  if (!getAccessToken()) return;
  if (queue.length >= MAX_BATCH) queue.shift();
  queue.push({
    name,
    path: path ?? (typeof window === "undefined" ? "/" : window.location.pathname),
    occurred_at: new Date().toISOString(),
  });
  if (queue.length >= FLUSH_AFTER) void flush();
}

export async function flush(): Promise<void> {
  if (flushing || queue.length === 0) return;
  flushing = true;
  const batch = queue.splice(0, MAX_BATCH);
  try {
    await api("/analytics/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
    });
  } catch {
    // Не теряем события: вернём в очередь, но не дадим ей расти бесконечно.
    queue = [...batch, ...queue].slice(-MAX_BATCH);
  } finally {
    flushing = false;
  }
}

export function resetAnalyticsQueue(): void {
  queue = [];
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => {
    void flush();
  });
}
