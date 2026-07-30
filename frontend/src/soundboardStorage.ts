export interface StoredSoundboardClip {
  id: string;
  ownerId: number;
  name: string;
  category: string;
  blob: Blob;
  createdAt: number;
}

const DATABASE_NAME = "nexus-soundboard";
const STORE_NAME = "clips";

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("ownerId", "ownerId");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Soundboard deposu açılamadı"));
  });
}

export async function listSoundboardClips(ownerId: number): Promise<StoredSoundboardClip[]> {
  const database = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).index("ownerId").getAll(ownerId);
      request.onsuccess = () => resolve(
        (request.result as StoredSoundboardClip[])
          .sort((left, right) => right.createdAt - left.createdAt),
      );
      request.onerror = () => reject(request.error ?? new Error("Soundboard sesleri okunamadı"));
    });
  } finally {
    database.close();
  }
}

export async function saveSoundboardClip(
  ownerId: number,
  file: File,
  category: string,
): Promise<StoredSoundboardClip> {
  const clip: StoredSoundboardClip = {
    id: `${ownerId}:${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`,
    ownerId,
    name: file.name.replace(/\.[^.]+$/, "").slice(0, 60) || "Özel ses",
    category: category.trim().slice(0, 32) || "Özel",
    blob: file.slice(0, file.size, file.type),
    createdAt: Date.now(),
  };
  const database = await openDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(clip);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Soundboard sesi kaydedilemedi"));
    });
  } finally {
    database.close();
  }
  return clip;
}

export async function deleteSoundboardClip(id: string): Promise<void> {
  const database = await openDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(id);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Soundboard sesi silinemedi"));
    });
  } finally {
    database.close();
  }
}
