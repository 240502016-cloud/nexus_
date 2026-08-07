/**
 * Nexus Lab modüllerinin production görünürlüğü.
 *
 * Bu dosya bilinçli olarak küçüktür ve panel bileşenlerini import etmez: hem `LabApp`
 * hem ana uygulama okur. Ana uygulama `LabApp`'i import etseydi Lab'in ayrı chunk
 * olması bozulur ve ana paket büyürdü.
 *
 * **6 Ağustos 2026: liste bilinçli olarak boş.** Dokuz modülün de backend'i sunucuda
 * çalışıyor ve `0019` migration'ı uygulanmış durumda; kapalı olmalarının sebebi teknik
 * değil, deneyimin yeterince iyi olmaması. Geliştirme bitince modüller tek tek buraya
 * eklenerek açılır — başka hiçbir değişiklik gerekmez.
 *
 * Geçerli anahtarlar: highlight · meme · party-lore · commentator · roast ·
 * board-game · hidden-role · shared-story · escape-room
 */
export const RELEASED_LAB_MODULES: ReadonlySet<string> = new Set<string>([]);

/**
 * Geliştirmede dağıtılmamış modüller de görünür: `docs/LOCAL_HUMAN_TEST.md` ortamı tam da
 * bunları gerçek arayüzden denemek için var. Production build'de yalnız `VITE_LAB_UNRELEASED=1`
 * ile açılırlar.
 */
export const SHOW_UNRELEASED = import.meta.env.DEV || import.meta.env.VITE_LAB_UNRELEASED === "1";

export function labModuleIsVisible(key: string): boolean {
  return SHOW_UNRELEASED || RELEASED_LAB_MODULES.has(key);
}

/**
 * Hiç görünür modül yoksa ana araç çubuğundaki Lab düğmesi de gizlenir; aksi hâlde
 * düğme boş bir pencere açardı.
 */
export const LAB_HAS_VISIBLE_MODULES = SHOW_UNRELEASED || RELEASED_LAB_MODULES.size > 0;
