const form = document.getElementById("media-form");
const urlInput = document.getElementById("url");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("submit-btn");
const stepInput = document.getElementById("step-input");
const stepLoading = document.getElementById("step-loading");
const stepResult = document.getElementById("step-result");
const resultPlatformEl = document.getElementById("result-platform");
const resultTitleEl = document.getElementById("result-title");
const resultSubtitleEl = document.getElementById("result-subtitle");
const resultCountEl = document.getElementById("result-count");
const mediaGridEl = document.getElementById("media-grid");
const backBtn = document.getElementById("back-btn");

const ENABLED_PLATFORMS = window.ENABLED_PLATFORMS || ["Instagram", "Facebook", "Loom"];

const SAMPLE_LINKS = {
  YouTube: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  Instagram: "https://www.instagram.com/p/CuQ6f2VIg3U/",
  Facebook: "https://www.facebook.com/reel/690088753344573/",
  Loom: "https://www.loom.com/share/4f0f8f8f832a4a57a56f7a7c7fcbf37f",
};

const PLATFORM_HOSTS = {
  YouTube: ["youtube.com", "youtu.be"],
  Instagram: ["instagram.com"],
  Facebook: ["facebook.com", "fb.watch"],
  Loom: ["loom.com"],
};

function setStatus(message, tone = "neutral") {
  statusEl.textContent = message || "";
  statusEl.classList.remove("text-error", "text-ok");
  if (tone === "error") statusEl.classList.add("text-error");
  if (tone === "ok") statusEl.classList.add("text-ok");
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.classList.toggle("is-loading", isLoading);
}

function showStep(stepId) {
  stepInput.classList.add("hidden");
  stepLoading.classList.add("hidden");
  stepResult.classList.add("hidden");
  const step = document.getElementById(stepId);
  if (step) step.classList.remove("hidden");
}

function updateActivePill(platform) {
  document.querySelectorAll(".pill").forEach((pill) => {
    pill.classList.toggle("active", pill.dataset.platform === platform);
  });
}

function detectPlatform(url) {
  let host = "";
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  return (
    Object.entries(PLATFORM_HOSTS).find(([, roots]) =>
      roots.some((root) => host === root || host.endsWith(`.${root}`))
    )?.[0] || null
  );
}

function formatDuration(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function makePlaceholder(platform) {
  const label = `${platform || "Media"} Preview`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420"><rect width="100%" height="100%" fill="#1c1e23"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#5f6368" font-family="system-ui" font-size="24">${label}</text></svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function typeLabel(type) {
  const lookup = { video: "VIDEO", image: "IMAGE", audio: "AUDIO", file: "FILE" };
  return lookup[type] || "MEDIA";
}

function buildDownloadHref(url, index, formatId) {
  const params = new URLSearchParams({ url, index: String(index) });
  if (formatId && formatId !== "best") params.set("format_id", formatId);
  return `/api/download?${params.toString()}`;
}

function clearResults() {
  mediaGridEl.innerHTML = "";
  resultPlatformEl.textContent = "";
  resultTitleEl.textContent = "";
  resultSubtitleEl.textContent = "";
  resultCountEl.textContent = "";
}

function buildMediaCard(url, item, platform) {
  const card = document.createElement("article");
  card.className = "border border-line rounded-[10px] overflow-hidden bg-bg-elevated transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover";

  const thumb = document.createElement("img");
  thumb.className = "w-full h-[140px] object-cover block bg-line";
  thumb.src = item.thumbnail || makePlaceholder(platform);
  thumb.alt = item.title || `Media ${item.index}`;
  thumb.loading = "lazy";

  const body = document.createElement("div");
  body.className = "p-3 grid gap-2";

  const title = document.createElement("p");
  title.className = "m-0 text-sm leading-snug text-ink line-clamp-2";
  title.textContent = item.title || `Media ${item.index}`;

  const meta = document.createElement("p");
  meta.className = "m-0 text-xs text-ink-muted";
  const parts = [platform, typeLabel(item.type), `Item ${item.index}`];
  if (formatDuration(item.duration)) parts.push(formatDuration(item.duration));
  if (item.ext) parts.push(String(item.ext).toUpperCase());
  meta.textContent = parts.filter(Boolean).join(" | ");

  const controls = document.createElement("div");
  controls.className = "grid gap-2";

  const select = document.createElement("select");
  select.className = "w-full text-sm text-ink border border-line rounded-lg py-2 px-2.5 bg-bg-card focus:outline-none focus:border-accent";
  const rawOptions = Array.isArray(item.download_options) ? item.download_options : [];
  const formatOptions = rawOptions.length ? rawOptions : [{ value: "best", label: "Best available", mode: "auto" }];
  formatOptions.forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.value || "best";
    option.textContent = entry.label || "Best available";
    option.dataset.mode = entry.mode || "auto";
    select.appendChild(option);
  });

  const link = document.createElement("a");
  link.className = "inline-flex items-center justify-center py-2.5 px-3.5 rounded-lg border border-accent text-accent font-semibold text-sm no-underline cursor-pointer transition-colors hover:bg-accent/15 hover:text-accent-hover";
  link.textContent = "Download";
  link.href = buildDownloadHref(url, item.index, select.value);
  link.rel = "noopener";

  select.addEventListener("change", () => {
    const selected = select.selectedOptions[0];
    link.textContent = selected?.dataset?.mode === "audio" ? "Download Audio" : "Download";
    link.href = buildDownloadHref(url, item.index, select.value);
  });

  body.appendChild(title);
  body.appendChild(meta);
  controls.appendChild(select);
  controls.appendChild(link);
  body.appendChild(controls);
  card.appendChild(thumb);
  card.appendChild(body);
  return card;
}

async function fetchMedia(url) {
  const response = await fetch("/api/media", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback = response.status ? `Request failed (${response.status}).` : "Unable to fetch media details.";
    throw new Error(payload.error || fallback);
  }
  return payload;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) {
    setStatus("Paste a URL first.", "error");
    return;
  }

  setLoading(true);
  setStatus("");
  showStep("step-loading");

  try {
    const payload = await fetchMedia(url);
    const items = Array.isArray(payload.items) ? payload.items : [];

    if (!items.length) {
      showStep("step-input");
      setStatus("No downloadable media found for this URL.", "error");
      return;
    }

    const platform = payload.platform || detectPlatform(payload.url) || "Source";
    resultPlatformEl.textContent = platform;
    resultTitleEl.textContent = payload.title || `${platform} media`;
    resultSubtitleEl.textContent = payload.uploader ? `By ${payload.uploader}` : "";
    resultCountEl.textContent = `${items.length} item${items.length === 1 ? "" : "s"}`;
    updateActivePill(platform);

    clearResults();
    items.forEach((item) => {
      mediaGridEl.appendChild(buildMediaCard(payload.url, item, platform));
    });

    showStep("step-result");
    setStatus(
      payload.ffmpeg_available === false
        ? `${items.length} item(s) ready. FFmpeg not installed — some options are video-only.`
        : `${items.length} item(s) ready.`,
      "ok"
    );
  } catch (error) {
    showStep("step-input");
    const message =
      error instanceof TypeError && /failed to fetch/i.test(error.message)
        ? "Cannot reach server. Is the app running?"
        : error.message || "Something went wrong.";
    setStatus(message, "error");
  } finally {
    setLoading(false);
  }
});

backBtn.addEventListener("click", () => {
  showStep("step-input");
  clearResults();
  setStatus("");
  urlInput.value = "";
  urlInput.focus();
  updateActivePill(null);
});

urlInput.addEventListener("input", () => {
  const url = urlInput.value.trim();
  const platform = detectPlatform(url);
  updateActivePill(platform);
  if (!url) {
    setStatus("");
    return;
  }
  if (platform && stepResult.classList.contains("hidden")) {
    setStatus(`${platform} link detected. Click Analyze.`);
  }
});

document.querySelectorAll(".pill").forEach((pill) => {
  pill.addEventListener("click", () => {
    const platform = pill.dataset.platform;
    updateActivePill(platform);
    if (!urlInput.value.trim() && SAMPLE_LINKS[platform]) {
      urlInput.value = SAMPLE_LINKS[platform];
    }
    urlInput.focus();
    setStatus(`${platform} selected. Paste or edit a ${platform} link.`);
  });
});

// Viewer modal (if used elsewhere)
const viewerModal = document.getElementById("viewer-modal");
const viewerClose = document.getElementById("viewer-close");
const viewerBackdrop = document.getElementById("viewer-backdrop");
if (viewerClose) {
  viewerClose.addEventListener("click", () => {
    if (viewerModal) viewerModal.classList.add("hidden");
  });
}
if (viewerBackdrop) {
  viewerBackdrop.addEventListener("click", () => {
    if (viewerModal) viewerModal.classList.add("hidden");
  });
}
