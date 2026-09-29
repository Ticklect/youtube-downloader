import * as api from "./api.js";
import { openOrFocusDownloader } from "./navigation.js";

const helperStatus = document.getElementById("helperStatus");
const helperMessage = document.getElementById("helperMessage");
const openDownloader = document.getElementById("openDownloader");

function setHelperState(kind, message) {
  const label = kind === "online" ? "Connected" : kind === "limited" ? "Limited" : "Offline";
  helperStatus.textContent = label;
  helperStatus.className = `status status-${kind}`;
  helperMessage.textContent = message;
}

openDownloader.addEventListener("click", async () => {
  try {
    await openOrFocusDownloader(chrome);
    window.close();
  } catch (error) {
    helperMessage.textContent = error?.message || "Could not open the downloader page.";
  }
});

async function initialize() {
  try {
    const health = await api.health();
    if (health.ok) {
      setHelperState("online", "Local helper is ready for downloads.");
      return;
    }

    const messages = health.dependencies?.messages || [];
    setHelperState("limited", messages.length ? messages.join(" ") : "Helper is running with limited download capabilities.");
  } catch {
    setHelperState("offline", "Local helper is not running. Start it with scripts/start-helper.ps1, then reopen this popup.");
  }
}

initialize();
