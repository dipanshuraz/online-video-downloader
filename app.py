import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from flask import Flask, abort, after_this_request, jsonify, render_template, request, send_file


APP_DIR = Path(__file__).resolve().parent
TMP_DIR = APP_DIR / "tmp_downloads"
TMP_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_PLATFORMS = {
    "Instagram": ("instagram.com",),
    "YouTube": ("youtube.com", "youtu.be"),
    "Facebook": ("facebook.com", "fb.watch"),
    "Loom": ("loom.com",),
}

app = Flask(__name__)


class DownloaderError(Exception):
    """Raised when yt-dlp fails for a supported URL."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def is_certificate_verify_error(message: str) -> bool:
    text = message.lower()
    return "certificate_verify_failed" in text or "unable to get local issuer certificate" in text


def parse_web_url(url: str) -> tuple[ParseResult, str] | None:
    if not url:
        return None

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None

    host = parsed.netloc.lower().split(":")[0]
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    return parsed, host


def host_matches(host: str, root_domain: str) -> bool:
    return host == root_domain or host.endswith(f".{root_domain}")


def detect_platform(url: str) -> str | None:
    parsed_host = parse_web_url(url)
    if not parsed_host:
        return None

    _parsed, host = parsed_host
    for platform, domains in SUPPORTED_PLATFORMS.items():
        if any(host_matches(host, domain) for domain in domains):
            return platform
    return None


def detect_instagram_kind(url: str, item_count: int) -> str:
    parsed_host = parse_web_url(url)
    path = parsed_host[0].path.lower() if parsed_host else ""

    if "/stories/" in path:
        return "story"
    if "/reel/" in path or "/reels/" in path:
        return "reel"
    if "/p/" in path:
        return "carousel" if item_count > 1 else "post"
    if item_count > 1:
        return "carousel"
    return "post"


def yt_dlp_base_args() -> list[str]:
    args = ["yt-dlp", "--no-warnings"]
    cookies_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    if cookies_file:
        args.extend(["--cookies", cookies_file])
    return args


def run_yt_dlp_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return proc

    message = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
    if "--no-check-certificates" not in cmd and is_certificate_verify_error(message):
        retry_cmd = cmd.copy()
        retry_cmd.insert(1, "--no-check-certificates")
        retry_proc = subprocess.run(retry_cmd, capture_output=True, text=True, check=False)
        if retry_proc.returncode == 0:
            return retry_proc
        return retry_proc

    return proc


def run_yt_dlp_json(url: str) -> dict:
    cmd = yt_dlp_base_args() + ["--dump-single-json", "--skip-download", url]
    proc = run_yt_dlp_command(cmd)

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
        raise DownloaderError(msg)

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DownloaderError("Failed to parse media metadata from yt-dlp output.") from exc


def format_score(fmt: dict) -> float:
    tbr = float(fmt.get("tbr") or 0)
    fps = float(fmt.get("fps") or 0)
    return tbr + (fps / 1000)


def build_download_options(item: dict, has_ffmpeg: bool) -> tuple[list[dict], dict[str, str]]:
    options: list[dict] = [{"value": "best", "label": "Best available", "mode": "auto"}]
    selector_map: dict[str, str] = {"best": "bestvideo*+bestaudio/best" if has_ffmpeg else "best"}
    formats = item.get("formats")
    if not isinstance(formats, list):
        return options, selector_map

    seen_values = {"best"}

    video_by_height: dict[int, dict] = {}
    audio_candidates: list[dict] = []

    for fmt in formats:
        if not isinstance(fmt, dict):
            continue

        format_id = str(fmt.get("format_id") or "").strip()
        if not format_id:
            continue

        vcodec = str(fmt.get("vcodec") or "none")
        acodec = str(fmt.get("acodec") or "none")

        if vcodec != "none":
            try:
                height = int(fmt.get("height"))
            except (TypeError, ValueError):
                height = 0
            if height > 0:
                existing = video_by_height.get(height)
                if not existing or format_score(fmt) > format_score(existing):
                    video_by_height[height] = fmt

        if vcodec == "none" and acodec != "none":
            audio_candidates.append(fmt)

    for height in sorted(video_by_height.keys(), reverse=True)[:5]:
        fmt = video_by_height[height]
        format_id = str(fmt.get("format_id") or "").strip()
        if not format_id or format_id in seen_values:
            continue
        seen_values.add(format_id)

        ext = str(fmt.get("ext") or "").upper()
        acodec = str(fmt.get("acodec") or "none")
        has_audio = acodec != "none"

        if has_audio:
            selector_map[format_id] = format_id
            label = f"Video {height}p"
        elif has_ffmpeg:
            selector_map[format_id] = f"{format_id}+bestaudio/best"
            label = f"Video {height}p + audio"
        else:
            selector_map[format_id] = format_id
            label = f"Video {height}p"

        suffix_parts: list[str] = []
        if not has_audio and not has_ffmpeg:
            suffix_parts.append("video-only")
        if ext:
            suffix_parts.append(ext)
        if suffix_parts:
            label += f" ({', '.join(suffix_parts)})"
        options.append({"value": format_id, "label": label, "mode": "video"})

    audio_candidates.sort(key=format_score, reverse=True)
    for fmt in audio_candidates[:5]:
        format_id = str(fmt.get("format_id") or "").strip()
        if not format_id or format_id in seen_values:
            continue
        seen_values.add(format_id)

        try:
            abr = int(round(float(fmt.get("abr"))))
        except (TypeError, ValueError):
            abr = None
        ext = str(fmt.get("ext") or "").upper()

        label = "Audio"
        if abr:
            label += f" {abr} kbps"
        if ext:
            label += f" ({ext})"
        options.append({"value": format_id, "label": label, "mode": "audio"})
        selector_map[format_id] = format_id

    return options, selector_map


def select_preview_url(item: dict) -> str | None:
    direct_url = str(item.get("url") or "").strip()
    if direct_url:
        return direct_url

    formats = item.get("formats")
    if not isinstance(formats, list):
        return None

    progressive: list[dict] = []
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        url = str(fmt.get("url") or "").strip()
        if not url:
            continue
        vcodec = str(fmt.get("vcodec") or "none")
        acodec = str(fmt.get("acodec") or "none")
        if vcodec != "none" and acodec != "none":
            progressive.append(fmt)

    if not progressive:
        return None

    progressive.sort(
        key=lambda fmt: (
            int(fmt.get("height") or 0),
            float(fmt.get("tbr") or 0),
        ),
        reverse=True,
    )
    return str(progressive[0].get("url") or "").strip() or None


def flatten_entries(info: dict) -> list[dict]:
    entries = info.get("entries")
    if not entries:
        return [info]

    flat: list[dict] = []
    for entry in entries:
        if not entry:
            continue
        nested = entry.get("entries")
        if nested:
            flat.extend(item for item in nested if item)
        else:
            flat.append(entry)

    return flat or [info]


def infer_type(item: dict) -> str:
    vcodec = item.get("vcodec")
    acodec = item.get("acodec")
    ext = (item.get("ext") or "").lower()
    direct_url = (item.get("url") or "").lower()

    if vcodec and vcodec != "none":
        return "video"
    if acodec and acodec != "none":
        return "audio"
    if ext in {"jpg", "jpeg", "png", "webp"}:
        return "image"
    if ext in {"mp3", "m4a", "aac", "ogg", "wav"}:
        return "audio"
    if any(token in direct_url for token in [".mp4", ".mov", ".webm"]):
        return "video"
    return "file"


def normalize_title(raw: str, fallback: str) -> str:
    title = raw.strip() if raw else fallback
    title = re.sub(r"\s+", " ", title)
    return title[:100]


def to_media_payload(items: list[dict], platform: str, source_url: str) -> tuple[list[dict], str | None]:
    payload: list[dict] = []
    has_ffmpeg = ffmpeg_available()
    instagram_kind = detect_instagram_kind(source_url, len(items)) if platform == "Instagram" else None
    for idx, item in enumerate(items, start=1):
        media_type = infer_type(item)
        download_options, _selector_map = build_download_options(item, has_ffmpeg=has_ffmpeg)
        payload.append(
            {
                "index": idx,
                "platform": platform,
                "type": media_type,
                "instagram_kind": instagram_kind,
                "title": normalize_title(item.get("title", ""), f"media_{idx}"),
                "thumbnail": item.get("thumbnail"),
                "preview_url": select_preview_url(item) if platform == "Instagram" else None,
                "duration": item.get("duration"),
                "ext": item.get("ext"),
                "download_options": download_options,
            }
        )
    return payload, instagram_kind


def run_download(
    url: str,
    item_count: int,
    index: int | None,
    output_dir: Path,
    format_selector: str | None = None,
) -> Path:
    cmd = yt_dlp_base_args()
    cmd += ["--restrict-filenames", "-P", str(output_dir), "-o", "%(title).80s.%(ext)s"]
    if format_selector:
        cmd += ["-f", format_selector]

    if item_count > 1 and index is not None:
        cmd += ["--playlist-items", str(index)]
    elif item_count <= 1:
        cmd += ["--no-playlist"]

    cmd.append(url)

    proc = run_yt_dlp_command(cmd)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "Download failed").strip()
        raise DownloaderError(msg)

    files = [path for path in output_dir.rglob("*") if path.is_file() and not path.name.endswith(".part")]
    if not files:
        raise DownloaderError("Download finished but no file was produced.")

    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0]


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/media")
def media():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    platform = detect_platform(url)

    if not platform:
        supported = ", ".join(SUPPORTED_PLATFORMS.keys())
        return jsonify({"error": f"Enter a valid URL from: {supported}."}), 400

    try:
        info = run_yt_dlp_json(url)
        entries = flatten_entries(info)
        items, instagram_kind = to_media_payload(entries, platform=platform, source_url=url)
        has_ffmpeg = ffmpeg_available()
    except DownloaderError as err:
        return jsonify({"error": str(err)}), 400

    return jsonify(
        {
            "url": url,
            "platform": platform,
            "ffmpeg_available": has_ffmpeg,
            "instagram_kind": instagram_kind,
            "title": normalize_title(info.get("title", ""), f"{platform} media"),
            "uploader": info.get("uploader") or info.get("channel"),
            "items": items,
        }
    )


@app.get("/api/download")
def download():
    url = (request.args.get("url") or "").strip()
    index_raw = (request.args.get("index") or "").strip()
    format_id = (request.args.get("format_id") or "").strip()
    index = int(index_raw) if index_raw.isdigit() else None
    platform = detect_platform(url)

    if not platform:
        supported = ", ".join(SUPPORTED_PLATFORMS.keys())
        abort(400, f"Invalid URL. Supported platforms: {supported}.")

    try:
        info = run_yt_dlp_json(url)
        entries = flatten_entries(info)
        item_count = len(entries)

        if item_count > 1:
            if index is None:
                abort(400, "This URL has multiple items. Include ?index=1 (or another item number).")
            if index < 1 or index > item_count:
                abort(400, f"Index must be between 1 and {item_count}.")

        selected_item = entries[index - 1] if item_count > 1 and index else entries[0]
        _download_options, selector_map = build_download_options(selected_item, has_ffmpeg=ffmpeg_available())

        if not format_id:
            format_id = "best"

        if format_id not in selector_map:
            abort(400, "Selected format is not available for this media item.")

        format_selector = selector_map[format_id]

        job_dir = TMP_DIR / str(uuid.uuid4())
        job_dir.mkdir(parents=True, exist_ok=True)

        @after_this_request
        def cleanup(response):  # type: ignore[override]
            shutil.rmtree(job_dir, ignore_errors=True)
            return response

        downloaded_file = run_download(
            url=url,
            item_count=item_count,
            index=index,
            output_dir=job_dir,
            format_selector=format_selector or None,
        )
        return send_file(downloaded_file, as_attachment=True, download_name=downloaded_file.name)
    except DownloaderError as err:
        abort(400, str(err))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
