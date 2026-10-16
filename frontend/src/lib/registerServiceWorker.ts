/**
 * Регистрация service worker нужна только в production-сборке:
 * в dev-режиме кэш service worker перехватывает ответы Vite и ломает горячую перезагрузку.
 */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return;
  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.error("Не удалось зарегистрировать service worker", error);
    });
  });
}
