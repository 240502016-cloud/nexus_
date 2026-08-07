import { useCallback, useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";

import { ApiError, coreApi, getToken } from "../api/client";
import { BoardGamePanel } from "../components/BoardGamePanel";
import { CommentatorPanel } from "../components/CommentatorPanel";
import { EscapeRoomPanel } from "../components/EscapeRoomPanel";
import { HiddenRoleGamePanel } from "../components/HiddenRoleGamePanel";
import { HighlightGeneratorPanel } from "../components/HighlightGeneratorPanel";
import { Icon } from "../components/Icon";
import type { IconName } from "../components/Icon";
import { MemeGeneratorPanel } from "../components/MemeGeneratorPanel";
import { PartyLorePanel } from "../components/PartyLorePanel";
import { RoastBattlePanel } from "../components/RoastBattlePanel";
import { SharedStoryPanel } from "../components/SharedStoryPanel";
import { LAB_HAS_VISIBLE_MODULES, labModuleIsVisible } from "./released";
import { loadVoiceSettings } from "../settings";
import type { ThemeMode } from "../settings";
import type { Member, Server, User } from "../types";

/** Lab modüllerinin ortak sözleşmesi. Panellerin kendi kodu değişmez. */
interface LabModuleProps {
  server: Server;
  members: Member[];
  currentUser: User;
  onClose: () => void;
}

interface LabModule {
  key: string;
  title: string;
  tagline: string;
  icon: IconName;
  category: "Anı" | "Sahne" | "Oyun";
  Component: ComponentType<LabModuleProps>;
}

/** Hangi modülün production'da açık olduğu `released.ts` içindedir. */
function isVisible(module: LabModule): boolean {
  return labModuleIsVisible(module.key);
}

/**
 * Commentator paneli ana uygulamada aktif metin kanalını alır. Lab ayrı bir pencere
 * olduğu için "şu an açık kanal" kavramı yoktur; panel kanal seçilmemiş durumda çalışır.
 */
function CommentatorModule(props: LabModuleProps) {
  return <CommentatorPanel {...props} activeChannelId={null} />;
}

const MODULES: LabModule[] = [
  {
    key: "highlight",
    title: "Highlight Generator",
    tagline: "Kayıttan öne çıkan anları ffmpeg ile kesip klip üretir.",
    icon: "screen",
    category: "Anı",
    Component: HighlightGeneratorPanel,
  },
  {
    key: "meme",
    title: "Meme Generator",
    tagline: "Oyun anını caption adaylarına ve özel bir PNG'ye dönüştürür.",
    icon: "smile",
    category: "Anı",
    Component: MemeGeneratorPanel,
  },
  {
    key: "party-lore",
    title: "Party Lore",
    tagline: "Sunucunun ortak hafızası. Her kayıt için önce onay alınır.",
    icon: "file",
    category: "Anı",
    Component: PartyLorePanel,
  },
  {
    key: "commentator",
    title: "AI Yorumcu",
    tagline: "Olayları canlı spiker diliyle anlatır.",
    icon: "bot",
    category: "Sahne",
    Component: CommentatorModule,
  },
  {
    key: "roast",
    title: "Roast Battle",
    tagline: "Onay veren oyuncular arasında sınırları belli atışma.",
    icon: "bot",
    category: "Sahne",
    Component: RoastBattlePanel,
  },
  {
    key: "board-game",
    title: "Son Portal",
    tagline: "AI anlatıcılı masa oyunu.",
    icon: "gamepad",
    category: "Oyun",
    Component: BoardGamePanel,
  },
  {
    key: "hidden-role",
    title: "Üç Mühür",
    tagline: "Gizli rol, iddia ve blöf oyunu.",
    icon: "users",
    category: "Oyun",
    Component: HiddenRoleGamePanel,
  },
  {
    key: "shared-story",
    title: "Ortak Hikâye",
    tagline: "Herkesin sırayla yazdığı, AI'ın ördüğü hikâye.",
    icon: "file",
    category: "Oyun",
    Component: SharedStoryPanel,
  },
  {
    key: "escape-room",
    title: "Escape Room",
    tagline: "Bulmaca düğümleri ve zamanlı kaçış senaryosu.",
    icon: "pin",
    category: "Oyun",
    Component: EscapeRoomPanel,
  },
];

const CATEGORIES: Array<LabModule["category"]> = ["Anı", "Sahne", "Oyun"];

function readInitialSelection(): { serverId: number | null; moduleKey: string | null } {
  const params = new URLSearchParams(window.location.search);
  const serverId = Number(params.get("server"));
  const moduleKey = params.get("module");
  return {
    serverId: Number.isInteger(serverId) && serverId > 0 ? serverId : null,
    // Gizli modüller adres çubuğundan da açılamaz.
    moduleKey: MODULES.some((item) => item.key === moduleKey && isVisible(item))
      ? moduleKey
      : null,
  };
}

/** Tema tercihini ana uygulamayla aynı localStorage anahtarından okur ve izler. */
function useSharedTheme(): void {
  useEffect(() => {
    const root = document.documentElement;
    const apply = (theme: ThemeMode) => {
      if (theme === "dark") root.removeAttribute("data-theme");
      else root.setAttribute("data-theme", theme);
    };
    const preference = loadVoiceSettings().theme;
    if (preference === "system") {
      const query = window.matchMedia("(prefers-color-scheme: light)");
      apply(query.matches ? "light" : "dark");
      const handler = (event: MediaQueryListEvent) => apply(event.matches ? "light" : "dark");
      query.addEventListener("change", handler);
      return () => query.removeEventListener("change", handler);
    }
    apply(preference);
  }, []);
}

export function LabApp() {
  useSharedTheme();
  const initial = useMemo(readInitialSelection, []);
  const [user, setUser] = useState<User | null>(null);
  const [servers, setServers] = useState<Server[]>([]);
  const [serverId, setServerId] = useState<number | null>(initial.serverId);
  const [members, setMembers] = useState<Member[]>([]);
  const [moduleKey, setModuleKey] = useState<string | null>(initial.moduleKey);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!getToken()) {
        setLoading(false);
        setError("Oturum bulunamadı. Nexus'a giriş yapıp Lab'i oradan açın.");
        return;
      }
      try {
        const [me, myServers] = await Promise.all([coreApi.me(), coreApi.myServers()]);
        if (cancelled) return;
        setUser(me);
        setServers(myServers);
        setServerId((current) =>
          current && myServers.some((item) => item.id === current)
            ? current
            : (myServers[0]?.id ?? null),
        );
      } catch (err) {
        if (!cancelled) {
          // Süresi dolmuş jetonda ham API hatası göstermek yerine ne yapılacağını söyle.
          setError(
            err instanceof ApiError && (err.status === 401 || err.status === 403)
              ? "Oturumun sona ermiş. Nexus'ta yeniden giriş yapıp Lab'i oradan aç."
              : err instanceof Error
                ? err.message
                : "Lab verileri yüklenemedi.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (serverId === null) {
      setMembers([]);
      return;
    }
    let cancelled = false;
    void coreApi
      .listMembers(serverId)
      .then((list) => {
        if (!cancelled) setMembers(list);
      })
      .catch(() => {
        if (!cancelled) setMembers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [serverId]);

  // Seçim adres çubuğuna yansır: Lab penceresi yenilendiğinde aynı modül açılır.
  useEffect(() => {
    const params = new URLSearchParams();
    if (serverId !== null) params.set("server", String(serverId));
    if (moduleKey) params.set("module", moduleKey);
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }, [serverId, moduleKey]);

  const closeModule = useCallback(() => setModuleKey(null), []);

  const activeServer = servers.find((item) => item.id === serverId) ?? null;
  const activeModule =
    MODULES.find((item) => item.key === moduleKey && isVisible(item)) ?? null;

  if (loading) {
    return (
      <div className="lab-shell lab-shell--centered">
        <div className="lab-splash">
          <Icon name="sparkles" />
          <p>Nexus Lab yükleniyor…</p>
        </div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="lab-shell lab-shell--centered">
        <div className="lab-splash">
          <Icon name="sparkles" />
          <h1>Nexus Lab</h1>
          <p>{error ?? "Oturum doğrulanamadı."}</p>
          <a className="lab-button" href="/">
            Nexus'a dön
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="lab-shell">
      <header className="lab-header">
        <div className="lab-header__brand">
          <span className="lab-header__mark">
            <Icon name="sparkles" />
          </span>
          <div>
            <h1>Nexus Lab</h1>
            <p>Deneysel modüller · ana uygulamadan ayrı çalışır</p>
          </div>
        </div>
        <div className="lab-header__actions">
          <label className="lab-server-picker">
            <span>Sunucu</span>
            <select
              value={serverId ?? ""}
              onChange={(event) => {
                setServerId(Number(event.target.value) || null);
                setModuleKey(null);
              }}
            >
              {servers.length === 0 ? <option value="">Sunucu yok</option> : null}
              {servers.map((server) => (
                <option key={server.id} value={server.id}>
                  {server.name}
                </option>
              ))}
            </select>
          </label>
          <a className="lab-button lab-button--ghost" href="/">
            <Icon name="external" />
            <span>Nexus</span>
          </a>
        </div>
      </header>

      {activeModule && activeServer ? (
        <main className="lab-stage">
          <nav className="lab-breadcrumb">
            <button type="button" className="lab-button lab-button--ghost" onClick={closeModule}>
              <Icon name="chevron" className="lab-breadcrumb__back" />
              <span>Tüm modüller</span>
            </button>
            <span className="lab-breadcrumb__here">
              {activeServer.name} · {activeModule.title}
            </span>
          </nav>
          <div className="lab-stage__surface">
            <activeModule.Component
              key={`${activeServer.id}:${activeModule.key}`}
              server={activeServer}
              members={members}
              currentUser={user}
              onClose={closeModule}
            />
          </div>
        </main>
      ) : (
        <main className="lab-home">
          {!activeServer ? (
            <p className="lab-empty">
              Henüz bir sunucun yok. Nexus'ta bir sunucu oluşturduktan sonra buradaki
              modüller kullanılabilir olur.
            </p>
          ) : !LAB_HAS_VISIBLE_MODULES ? (
            // Tüm modüller kapalıyken katalog boş kalır; yer imiyle gelen kullanıcı
            // bozuk bir sayfa değil, ne olduğunu anlatan bir mesaj görmeli.
            <p className="lab-empty">
              Lab modülleri şu an geliştirme aşamasında ve kullanıma kapalı. Hazır
              olduklarında burada tekrar görünecekler.
            </p>
          ) : (
            CATEGORIES.filter((category) =>
              MODULES.some((item) => item.category === category && isVisible(item)),
            ).map((category) => (
              <section key={category} className="lab-section">
                <h2 className="lab-section__title">{category}</h2>
                <div className="lab-grid">
                  {MODULES.filter(
                    (item) => item.category === category && isVisible(item),
                  ).map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className="lab-card"
                      onClick={() => setModuleKey(item.key)}
                    >
                      <span className="lab-card__icon">
                        <Icon name={item.icon} />
                      </span>
                      <strong className="lab-card__title">{item.title}</strong>
                      <span className="lab-card__tagline">{item.tagline}</span>
                    </button>
                  ))}
                </div>
              </section>
            ))
          )}
        </main>
      )}
    </div>
  );
}
