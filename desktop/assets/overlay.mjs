const channelName = document.getElementById("channel-name");
const participants = document.getElementById("participants");
const muteButton = document.getElementById("mute-button");
const deafenButton = document.getElementById("deafen-button");
const closeButton = document.getElementById("close-button");

function render(state) {
  channelName.textContent = state.connected ? state.channelName || "Ses kanalı" : "Ses bağlantısı yok";
  muteButton.disabled = !state.connected;
  deafenButton.disabled = !state.connected;
  muteButton.classList.toggle("active", state.muted);
  deafenButton.classList.toggle("active", state.deafened);
  muteButton.textContent = state.muted ? "🎤 Mikrofon kapalı" : "🎤 Mikrofon açık";
  deafenButton.textContent = state.deafened ? "🔇 Ses kapalı" : "🔊 Ses açık";

  if (!state.connected || state.participants.length === 0) {
    participants.innerHTML =
      '<p class="overlay__empty">Bir ses kanalına katıldığınızda katılımcılar burada görünür.</p>';
    return;
  }
  participants.replaceChildren(
    ...state.participants.map((participant) => {
      const row = document.createElement("div");
      row.className = `overlay__participant${participant.speaking ? " speaking" : ""}`;
      const dot = document.createElement("span");
      dot.className = "overlay__dot";
      const name = document.createElement("span");
      name.className = "overlay__name";
      name.textContent = participant.username;
      const status = document.createElement("span");
      status.className = "overlay__state";
      status.textContent = participant.muted ? "sessiz" : participant.speaking ? "konuşuyor" : "";
      row.append(dot, name, status);
      return row;
    }),
  );
}

window.nexusDesktop.onVoiceState(render);

muteButton.addEventListener("click", () => window.nexusDesktop.sendOverlayAction("toggle-mute"));
deafenButton.addEventListener("click", () => window.nexusDesktop.sendOverlayAction("toggle-deafen"));
closeButton.addEventListener("click", () => window.nexusDesktop.closeOverlay());
