import base64
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from flask import Flask, abort, after_this_request, jsonify, make_response, render_template, request, send_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


APP_DIR = Path(__file__).resolve().parent
TMP_DIR = APP_DIR / "tmp_downloads"
TMP_DIR.mkdir(parents=True, exist_ok=True)
ENV_COOKIES_FILE = TMP_DIR / "cookies_from_env.txt"

SUPPORTED_PLATFORMS = {
    "Instagram": ("instagram.com",),
    "YouTube": ("youtube.com", "youtu.be"),
    "Facebook": ("facebook.com", "fb.watch"),
    "Loom": ("loom.com",),
}

app = Flask(__name__)


def youtube_enabled() -> bool:
    """YouTube is allowed only in non-prod (local/dev). Set ENABLE_YOUTUBE=1 to allow in prod."""
    if os.getenv("ENABLE_YOUTUBE", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.getenv("FLASK_DEBUG", "0") == "1":
        return True
    return False


def enabled_platforms() -> list[str]:
    """Platforms available in this environment (YouTube excluded in prod unless opted in)."""
    return [
        name
        for name in SUPPORTED_PLATFORMS
        if name != "YouTube" or youtube_enabled()
    ]


class DownloaderError(Exception):
    """Raised when yt-dlp fails for a supported URL."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def cookies_configured() -> bool:
    return bool(
        os.getenv("YTDLP_COOKIES_FILE", "").strip()
        or os.getenv("YTDLP_COOKIES_B64", "").strip()
        or os.getenv("YTDLP_COOKIES_TEXT", "").strip()
    )


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


def cookies_file_from_env() -> str | None:
    explicit_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    if explicit_file:
        return explicit_file

    cookies_b64 = os.getenv("YTDLP_COOKIES_B64", "").strip()
    # Allow base64 with newlines (e.g. from copy-paste or multiline env)
    cookies_b64 = "".join(cookies_b64.split())
    cookies_text = os.getenv("YTDLP_COOKIES_TEXT", "")
    if not cookies_b64 and not cookies_text:
        return None

    try:
        content = (
            base64.b64decode(cookies_b64.encode("utf-8")).decode("utf-8")
            if cookies_b64
            else cookies_text
        )
    except Exception as exc:
        raise DownloaderError("Invalid YTDLP_COOKIES_B64 value. Expected base64-encoded cookies.txt.") from exc

    if "Netscape HTTP Cookie File" not in content:
        raise DownloaderError("Cookies must be in Netscape cookies.txt format.")

    ENV_COOKIES_FILE.write_text(content, encoding="utf-8")
    os.chmod(ENV_COOKIES_FILE, 0o600)
    return str(ENV_COOKIES_FILE)


def yt_dlp_base_args() -> list[str]:
    args = ["yt-dlp", "--no-warnings"]
    cookies_file = cookies_file_from_env()
    if cookies_file:
        args.extend(["--cookies", cookies_file])
    extractor_args = os.getenv("YTDLP_EXTRACTOR_ARGS", "").strip()
    if extractor_args:
        args.extend(["--extractor-args", extractor_args])
    return args


def is_instagram_auth_error(message: str) -> bool:
    text = message.lower()
    return any(
        key in text
        for key in [
            "login required",
            "rate-limit reached",
            "requested content is not available",
            "use --cookies-from-browser or --cookies",
            "please wait a few minutes",
            "challenge_required",
        ]
    )


def is_youtube_auth_error(message: str) -> bool:
    text = message.lower()
    return any(
        key in text
        for key in [
            "sign in to confirm",
            "not a bot",
            "use --cookies-from-browser or --cookies",
            "this video may be inappropriate for some users",
            "age-restricted",
        ]
    )


def humanize_downloader_error(message: str, platform: str | None) -> str:
    if platform == "Instagram" and is_instagram_auth_error(message):
        if cookies_configured():
            return (
                "Instagram denied this request (rate limit or account restriction). "
                "Your server IP may be blocked. Try again later or use a different server IP."
            )
        return (
            "Instagram requires login cookies for this URL (or your server IP is rate-limited). "
            "Set Render env var YTDLP_COOKIES_B64 with a base64-encoded cookies.txt from an Instagram-logged-in browser."
        )
    if platform == "YouTube" and is_youtube_auth_error(message):
        if cookies_configured():
            return (
                "YouTube denied this request (bot check) even with cookies. "
                "Refresh cookies and, if needed, use a different server IP/proxy."
            )
        return (
            "YouTube requires authenticated cookies on this server/IP. "
            "Fix: (1) Export cookies.txt from a browser where you're logged into YouTube (use a 'cookies.txt' extension, Netscape format). "
            "(2) Run: base64 < cookies.txt | tr -d '\\n' "
            "(3) In Render → Service → Environment, add YTDLP_COOKIES_B64 = that base64 string, then redeploy."
        )
    return message


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
    try:
        proc = run_yt_dlp_command(cmd)
    except OSError as exc:
        raise DownloaderError("yt-dlp is not installed or not available in PATH. Install it and try again.") from exc

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
        raise DownloaderError(msg)

    if not (proc.stdout and proc.stdout.strip()):
        raise DownloaderError("No metadata returned for this URL. The link may be private or unsupported.")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DownloaderError("Failed to parse media metadata from this source.") from exc

    if not isinstance(data, dict):
        raise DownloaderError("Unexpected response format from this source.")
    return data


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
    if not info or not isinstance(info, dict):
        return []
    entries = info.get("entries")
    if not entries or not isinstance(entries, list):
        return [info]

    flat: list[dict] = []
    for entry in entries:
        if not entry or not isinstance(entry, dict):
            continue
        nested = entry.get("entries")
        if nested and isinstance(nested, list):
            flat.extend(item for item in nested if item and isinstance(item, dict))
        else:
            flat.append(entry)

    return flat if flat else [info]


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


def normalize_title(raw: str | None, fallback: str) -> str:
    try:
        title = (raw.strip() if raw else fallback) or fallback
    except (AttributeError, TypeError):
        title = fallback
    title = re.sub(r"\s+", " ", str(title))
    return title[:100]


def to_media_payload(items: list[dict], platform: str, source_url: str) -> tuple[list[dict], str | None]:
    payload: list[dict] = []
    has_ffmpeg = ffmpeg_available()
    instagram_kind = detect_instagram_kind(source_url, len(items)) if platform == "Instagram" else None
    for idx, item in enumerate(items, start=1):
        if not item or not isinstance(item, dict):
            continue
        try:
            media_type = infer_type(item)
            download_options, _selector_map = build_download_options(item, has_ffmpeg=has_ffmpeg)
            thumb = item.get("thumbnail")
            if isinstance(thumb, list) and thumb:
                thumb = thumb[0] if isinstance(thumb[0], str) else None
            if thumb is not None and not isinstance(thumb, str):
                thumb = str(thumb)
            duration = item.get("duration")
            if duration is not None and not isinstance(duration, (int, float)):
                try:
                    duration = float(duration)
                except (TypeError, ValueError):
                    duration = None
            ext = item.get("ext")
            if ext is not None and not isinstance(ext, str):
                ext = str(ext)
            payload.append(
                {
                    "index": len(payload) + 1,
                    "platform": platform,
                    "type": media_type,
                    "instagram_kind": instagram_kind,
                    "title": normalize_title(item.get("title"), f"media_{len(payload) + 1}"),
                    "thumbnail": thumb,
                    "preview_url": select_preview_url(item) if platform == "Instagram" else None,
                    "duration": duration,
                    "ext": ext,
                    "download_options": download_options,
                }
            )
        except Exception:
            logger.exception("Skipping malformed item from source")
            continue
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
    return render_template("index.html", enabled_platforms=enabled_platforms())


@app.get("/favicon.ico")
def favicon():
    """Return a minimal favicon to avoid 404 in browser tab."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<rect width="32" height="32" rx="6" fill="#16181c"/>'
        b'<path fill="#8ab4f8" d="M10 8h12v3l-6 5-6-5V8zm0 6h6v10h-6V14zm8 0h6v10h-6V14z"/>'
        b"</svg>"
    )
    resp = make_response(svg, 200)
    resp.headers["Content-Type"] = "image/svg+xml"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.post("/api/media")
def media():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    platform = detect_platform(url)

    if not platform:
        supported = ", ".join(SUPPORTED_PLATFORMS.keys())
        return jsonify({"error": f"Enter a valid URL from: {supported}."}), 400

    if platform == "YouTube" and not youtube_enabled():
        return (
            jsonify(
                {
                    "error": "YouTube downloads are disabled in production. Use locally (FLASK_DEBUG=1) or set ENABLE_YOUTUBE=1 to enable."
                }
            ),
            400,
        )

    try:
        info = run_yt_dlp_json(url)
        entries = flatten_entries(info)
        if not entries:
            return jsonify({"error": "No playable media found for this link."}), 400
        items, instagram_kind = to_media_payload(entries, platform=platform, source_url=url)
        if not items:
            return jsonify({"error": "Could not read media formats for this link. It may be private or unsupported."}), 400
        has_ffmpeg = ffmpeg_available()
    except DownloaderError as err:
        return jsonify({"error": humanize_downloader_error(str(err), platform)}), 400
    except Exception as err:
        logger.exception("Unexpected error in /api/media")
        return (
            jsonify(
                {
                    "error": "Could not process this link. It may be private, region-restricted, or the source may be temporarily unavailable."
                }
            ),
            400,
        )

    try:
        uploader = info.get("uploader") or info.get("channel")
        if uploader is not None and not isinstance(uploader, str):
            uploader = str(uploader)
        return jsonify(
            {
                "url": url,
                "platform": platform,
                "ffmpeg_available": has_ffmpeg,
                "instagram_kind": instagram_kind,
                "title": normalize_title(info.get("title"), f"{platform} media"),
                "uploader": uploader or "",
                "items": items,
            }
        )
    except Exception:
        logger.exception("Response serialization failed in /api/media")
        return (
            jsonify(
                {"error": "Could not process this link. The source returned unexpected data."}
            ),
            400,
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

    if platform == "YouTube" and not youtube_enabled():
        abort(
            400,
            "YouTube downloads are disabled in production. Use locally or set ENABLE_YOUTUBE=1.",
        )

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
        abort(400, humanize_downloader_error(str(err), platform))
    except Exception:
        logger.exception("Unexpected error in /api/download")
        abort(400, "Download failed. The link may be invalid or the source may be temporarily unavailable.")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5001")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
