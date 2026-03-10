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
  statusEl.className = "inline-block py-2.5 px-6 rounded-full text-sm font-semibold transition-all duration-300 transform shadow-lg";

  if (!message) {
    statusEl.classList.add("opacity-0", "scale-95", "pointer-events-none");
    return;
  }

  statusEl.classList.add("opacity-100", "scale-100");

  if (tone === "error") {
    statusEl.classList.add("bg-error/10", "text-error", "border", "border-error/20");
  } else if (tone === "ok") {
    statusEl.classList.add("bg-ok/10", "text-ok", "border", "border-ok/20");
  } else {
    statusEl.classList.add("bg-bg-elevated", "text-white", "border", "border-line");
  }
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
  if (step) {
    step.classList.remove("hidden");
  }
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
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420"><defs><linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1e1e2e" /><stop offset="100%" stop-color="#12121c" /></linearGradient></defs><rect width="100%" height="100%" fill="url(#grad)"/><circle cx="50%" cy="40%" r="40" fill="#2d3139" opacity="0.6"/><text x="50%" y="65%" dominant-baseline="middle" text-anchor="middle" fill="#5f6368" font-family="system-ui" font-size="20" font-weight="600">${label}</text></svg>`;
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
  card.className = "flex flex-col h-full glass-panel glass-panel-hover rounded-[20px] overflow-hidden group";

  const thumbWrapper = document.createElement("div");
  thumbWrapper.className = "relative w-full aspect-video overflow-hidden bg-bg-dark border-b border-line";

  const thumb = document.createElement("img");
  thumb.className = "w-full h-full object-cover transition-transform duration-700 group-hover:scale-105";
  thumb.src = item.thumbnail || makePlaceholder(platform);
  thumb.alt = item.title || `Media ${item.index}`;
  thumb.loading = "lazy";

  // Overlay gradient to make text legible if any
  const overlay = document.createElement("div");
  overlay.className = "absolute inset-0 bg-gradient-to-t from-bg-card/90 via-transparent to-transparent opacity-80 pointer-events-none";

  // Type badge
  const badge = document.createElement("span");
  badge.className = "absolute top-3 left-3 bg-bg-card/80 backdrop-blur-md text-white text-[10px] uppercase font-bold tracking-wider py-1 px-2.5 rounded-md border border-line";
  badge.textContent = typeLabel(item.type);

  // Duration
  const duration = formatDuration(item.duration);
  if (duration) {
    const durBadge = document.createElement("span");
    durBadge.className = "absolute bottom-3 right-3 bg-black/70 backdrop-blur-md text-white text-xs font-semibold py-1 px-2 rounded tracking-wide";
    durBadge.textContent = duration;
    thumbWrapper.appendChild(durBadge);
  }

  thumbWrapper.appendChild(thumb);
  thumbWrapper.appendChild(overlay);
  thumbWrapper.appendChild(badge);

  const body = document.createElement("div");
  body.className = "p-5 flex flex-col flex-grow w-full"; // ensure it takes full width

  const headLayout = document.createElement("div");
  headLayout.className = "mb-4 flex-grow";

  const title = document.createElement("h3");
  title.className = "m-0 font-bold text-base leading-snug text-white line-clamp-2 mb-1.5";
  title.textContent = item.title || `Media ${item.index}`;

  const meta = document.createElement("p");
  meta.className = "m-0 text-[0.8rem] text-ink-muted flex flex-wrap gap-1.5 items-center";

  const parts = [platform, `Item ${item.index}`];
  if (item.ext) parts.push(String(item.ext).toUpperCase());

  parts.forEach((part, i) => {
    const span = document.createElement("span");
    span.textContent = part;
    meta.appendChild(span);
    if (i < parts.length - 1) {
      const dot = document.createElement("span");
      dot.className = "w-1 h-1 rounded-full bg-line-light";
      meta.appendChild(dot);
    }
  });

  headLayout.appendChild(title);
  headLayout.appendChild(meta);

  const controls = document.createElement("div");
  controls.className = "grid gap-3 pt-4 border-t border-line mt-auto";

  const selectWrapper = document.createElement("div");
  selectWrapper.className = "relative";

  const selectIcon = document.createElement("div");
  selectIcon.className = "absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-ink-muted";
  selectIcon.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;

  const select = document.createElement("select");
  select.className = "w-full appearance-none text-sm font-medium text-white border border-line rounded-[12px] py-3 pl-4 pr-10 bg-bg-elevated/50 backdrop-blur-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-colors cursor-pointer hover:bg-bg-elevated";

  const rawOptions = Array.isArray(item.download_options) ? item.download_options : [];
  const formatOptions = rawOptions.length ? rawOptions : [{ value: "best", label: "Best available", mode: "auto" }];
  formatOptions.forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.value || "best";
    option.textContent = entry.label || "Best available";
    option.dataset.mode = entry.mode || "auto";
    select.appendChild(option);
  });

  selectWrapper.appendChild(select);
  selectWrapper.appendChild(selectIcon);

  const link = document.createElement("a");
  link.className = "btn w-full inline-flex items-center justify-center py-3 px-4 rounded-[12px] border border-accent text-accent font-bold text-sm tracking-wide no-underline cursor-pointer transition-all hover:bg-accent hover:text-bg-dark";
  link.innerHTML = `<span class="flex items-center gap-2"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download</span>`;
  link.href = buildDownloadHref(url, item.index, select.value);
  link.rel = "noopener";

  select.addEventListener("change", () => {
    const selected = select.selectedOptions[0];
    const isAudio = selected?.dataset?.mode === "audio";
    link.innerHTML = `<span class="flex items-center gap-2"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${isAudio ? '<path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle>' : '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>'}</svg> ${isAudio ? 'Download Audio' : 'Download'}</span>`;
    link.href = buildDownloadHref(url, item.index, select.value);
  });

  body.appendChild(headLayout);
  controls.appendChild(selectWrapper);
  controls.appendChild(link);
  body.appendChild(controls);

  card.appendChild(thumbWrapper);
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
