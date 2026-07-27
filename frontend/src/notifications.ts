export function playMessageNotification(): void {
  try {
    const audio = new AudioContext();
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    const start = audio.currentTime;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(660, start);
    oscillator.frequency.exponentialRampToValueAtTime(880, start + 0.1);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.12, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.18);
    oscillator.connect(gain);
    gain.connect(audio.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.2);
    oscillator.addEventListener("ended", () => void audio.close(), { once: true });
  } catch {
    // WebAudio desteklenmiyor veya otomatik oynatma engellendi.
  }
}
