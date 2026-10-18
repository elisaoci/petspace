/**
 * Офлайн-кэш Smart-ID.
 *
 * Данные медкарты — медицинские, поэтому на устройстве они лежат только в зашифрованном виде:
 * AES-256-GCM, ключ генерируется в браузере как неизвлекаемый (extractable: false) и хранится
 * в IndexedDB. Сайт не может выгрузить сам ключ, а кэш очищается при выходе из аккаунта.
 */

const DB_NAME = "petspace-offline";
const DB_VERSION = 1;
const CACHE_STORE = "records";
const KEY_STORE = "keys";
const KEY_ID = "aes-gcm";

type CachedPayload = { iv: number[]; data: ArrayBuffer; updatedAt: string };

export type CachedRecords<T> = { records: T; updatedAt: string };

export function offlineSupported(): boolean {
  return typeof indexedDB !== "undefined" && Boolean(globalThis.crypto?.subtle);
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(CACHE_STORE)) db.createObjectStore(CACHE_STORE);
      if (!db.objectStoreNames.contains(KEY_STORE)) db.createObjectStore(KEY_STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function read<T>(store: string, key: IDBValidKey): Promise<T | undefined> {
  return openDb().then(
    db =>
      new Promise<T | undefined>((resolve, reject) => {
        const tx = db.transaction(store, "readonly");
        const request = tx.objectStore(store).get(key);
        request.onsuccess = () => resolve(request.result as T | undefined);
        request.onerror = () => reject(request.error);
      }),
  );
}

function write(store: string, key: IDBValidKey, value: unknown): Promise<void> {
  return openDb().then(
    db =>
      new Promise<void>((resolve, reject) => {
        const tx = db.transaction(store, "readwrite");
        tx.objectStore(store).put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      }),
  );
}

function clearStore(store: string): Promise<void> {
  return openDb().then(
    db =>
      new Promise<void>((resolve, reject) => {
        const tx = db.transaction(store, "readwrite");
        tx.objectStore(store).clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      }),
  );
}

async function getKey(): Promise<CryptoKey> {
  const existing = await read<CryptoKey>(KEY_STORE, KEY_ID);
  if (existing) return existing;

  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, [
    "encrypt",
    "decrypt",
  ]);
  await write(KEY_STORE, KEY_ID, key);
  return key;
}

export async function saveRecordsCache(petId: number, records: unknown): Promise<void> {
  if (!offlineSupported()) return;
  const key = await getKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(JSON.stringify(records));
  const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);

  await write(CACHE_STORE, petId, {
    iv: Array.from(iv),
    data,
    updatedAt: new Date().toISOString(),
  } satisfies CachedPayload);
}

export async function loadRecordsCache<T>(petId: number): Promise<CachedRecords<T> | null> {
  if (!offlineSupported()) return null;
  const cached = await read<CachedPayload>(CACHE_STORE, petId);
  if (!cached) return null;

  const key = await getKey();
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(cached.iv) },
    key,
    cached.data,
  );
  return {
    records: JSON.parse(new TextDecoder().decode(plain)) as T,
    updatedAt: cached.updatedAt,
  };
}

/** Полная очистка: и данные, и ключ. Вызывается при выходе из аккаунта. */
export async function clearOfflineCache(): Promise<void> {
  if (!offlineSupported()) return;
  await clearStore(CACHE_STORE);
  await clearStore(KEY_STORE);
}
