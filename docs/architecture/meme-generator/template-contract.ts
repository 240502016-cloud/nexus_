export type MemeCategory =
  | "REPEATED_FAILURE"
  | "OVERCONFIDENT_FAILURE"
  | "ACCIDENTAL_SUCCESS"
  | "BETRAYAL"
  | "USELESS_PREPARATION"
  | "BAD_NAVIGATION"
  | "PANIC"
  | "CLUTCH"
  | "FAKE_EXPERT"
  | "BLAMING_LAG"
  | "SILENT_DISASTER"
  | "TEAM_WIDE_FAILURE"
  | "GREED_PUNISHED"
  | "FRIENDLY_FIRE"
  | "MISSED_OBVIOUS"
  | "RESOURCE_HOARDER"
  | "PREMATURE_CELEBRATION"
  | "IMPOSSIBLE_COMEBACK"
  | "AFK_TIMING"
  | "CURSED_PLAN";

export type CaptionZoneId = "TOP" | "BOTTOM" | "TITLE" | "SUBTITLE" | "STAT" | "FOOTER";

export interface CaptionZone {
  id: CaptionZoneId;
  /** Normalized coordinates in the 0..1 range. */
  x: number;
  y: number;
  width: number;
  height: number;
  maxChars: number;
  maxLines: number;
  minFontSize: number;
  maxFontSize: number;
  fontFamily: "Noto Sans";
  fontWeight: 400 | 700 | 900;
  align: "LEFT" | "CENTER" | "RIGHT";
  verticalAlign: "TOP" | "MIDDLE" | "BOTTOM";
  textColor: string;
  strokeColor?: string;
  strokeWidth?: number;
  uppercase: boolean;
}

export interface MemeTemplate {
  id: string;
  version: number;
  name: string;
  categories: MemeCategory[];
  imageAssetId: string;
  captionZones: CaptionZone[];
  safeTextLimits: {
    totalChars: number;
    maximumWords: number;
  };
  aspectRatio: {
    width: number;
    height: number;
  };
  tags: string[];
  requiredContext: Array<
    "ACTOR" | "TARGET" | "SETUP" | "PAYOFF" | "SCREENSHOT" | "NUMERIC_FACT" | "LORE"
  >;
  recentUseCooldownHours: number;
  suitabilityRules: {
    minimumImportance: number;
    maximumHarshness: 0 | 1 | 2 | 3;
    preferredMomentTypes: string[];
    requiresScreenshot: boolean;
  };
  enabled: boolean;
}

export const expectationRealityTemplate: MemeTemplate = {
  id: "f927443c-e3ce-4a61-b746-7a482aed4e46",
  version: 1,
  name: "Beklenti / Gerçeklik — İki Panel",
  categories: ["OVERCONFIDENT_FAILURE", "USELESS_PREPARATION", "CURSED_PLAN"],
  imageAssetId: "79dcf765-5fc4-4e72-b9e4-c237d063df9d",
  captionZones: [
    {
      id: "TOP",
      x: 0.04,
      y: 0.03,
      width: 0.92,
      height: 0.18,
      maxChars: 48,
      maxLines: 2,
      minFontSize: 30,
      maxFontSize: 58,
      fontFamily: "Noto Sans",
      fontWeight: 900,
      align: "CENTER",
      verticalAlign: "MIDDLE",
      textColor: "#FFFFFF",
      strokeColor: "#000000",
      strokeWidth: 3,
      uppercase: false,
    },
    {
      id: "BOTTOM",
      x: 0.04,
      y: 0.79,
      width: 0.92,
      height: 0.18,
      maxChars: 48,
      maxLines: 2,
      minFontSize: 30,
      maxFontSize: 58,
      fontFamily: "Noto Sans",
      fontWeight: 900,
      align: "CENTER",
      verticalAlign: "MIDDLE",
      textColor: "#FFFFFF",
      strokeColor: "#000000",
      strokeWidth: 3,
      uppercase: false,
    },
  ],
  safeTextLimits: { totalChars: 96, maximumWords: 18 },
  aspectRatio: { width: 1, height: 1 },
  tags: ["iki-panel", "hazırlık", "plan", "başarısızlık"],
  requiredContext: ["ACTOR", "SETUP", "PAYOFF"],
  recentUseCooldownHours: 168,
  suitabilityRules: {
    minimumImportance: 0.6,
    maximumHarshness: 2,
    preferredMomentTypes: ["FAILURE", "PREPARATION"],
    requiresScreenshot: false,
  },
  enabled: true,
};

