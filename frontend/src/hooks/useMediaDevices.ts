import { useCallback, useEffect, useState } from "react";

export interface MediaDeviceInfoLite {
  deviceId: string;
  label: string;
}

export interface MediaDevices {
  microphones: MediaDeviceInfoLite[];
  cameras: MediaDeviceInfoLite[];
  speakers: MediaDeviceInfoLite[];
}

const EMPTY: MediaDevices = { microphones: [], cameras: [], speakers: [] };

// Ses çıkışı seçimi (setSinkId) yalnızca bazı tarayıcılarda (Chrome/Edge) desteklenir.
export const SINK_ID_SUPPORTED =
  typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;

function labelFor(device: MediaDeviceInfo, index: number, kind: string): string {
  if (device.label) return device.label;
  // İzin verilmeden önce tarayıcı label'ları gizler; anlamlı bir yer tutucu göster.
  return `${kind} ${index + 1}`;
}

/**
 * Kullanılabilir mikrofon/kamera/hoparlör cihazlarını listeler ve `devicechange` olaylarını
 * dinler. Cihaz label'ları yalnızca kullanıcı en az bir kez izin verdikten sonra görünür;
 * `permissionGranted` bunu bildirir.
 */
export function useMediaDevices() {
  const [devices, setDevices] = useState<MediaDevices>(EMPTY);
  const [permissionGranted, setPermissionGranted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enumerate = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setError("Bu tarayıcı cihaz listelemeyi desteklemiyor.");
      return;
    }
    try {
      const list = await navigator.mediaDevices.enumerateDevices();
      const microphones: MediaDeviceInfoLite[] = [];
      const cameras: MediaDeviceInfoLite[] = [];
      const speakers: MediaDeviceInfoLite[] = [];
      list.forEach((d, i) => {
        if (d.kind === "audioinput") microphones.push({ deviceId: d.deviceId, label: labelFor(d, i, "Mikrofon") });
        else if (d.kind === "videoinput") cameras.push({ deviceId: d.deviceId, label: labelFor(d, i, "Kamera") });
        else if (d.kind === "audiooutput") speakers.push({ deviceId: d.deviceId, label: labelFor(d, i, "Hoparlör") });
      });
      setDevices({ microphones, cameras, speakers });
      // Label doluysa izin verilmiş demektir.
      setPermissionGranted(list.some((d) => d.label !== ""));
    } catch (err) {
      setError(`Cihazlar listelenemedi: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, []);

  // İzin isteyerek cihaz label'larının açığa çıkmasını sağlar (mikrofon + kamera).
  const requestPermission = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      stream.getTracks().forEach((t) => t.stop());
    } catch {
      // Kamera reddedilse bile en azından mikrofon için tekrar dene (sadece ses).
      try {
        const audio = await navigator.mediaDevices.getUserMedia({ audio: true });
        audio.getTracks().forEach((t) => t.stop());
      } catch (err) {
        setError(`İzin alınamadı: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
    await enumerate();
  }, [enumerate]);

  useEffect(() => {
    void enumerate();
    const handler = () => void enumerate();
    navigator.mediaDevices?.addEventListener?.("devicechange", handler);
    return () => navigator.mediaDevices?.removeEventListener?.("devicechange", handler);
  }, [enumerate]);

  return { devices, permissionGranted, error, refresh: enumerate, requestPermission };
}
