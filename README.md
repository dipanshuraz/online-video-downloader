# Multi-Source Video and Image Downloader

Simple Flask app with a minimalist interactive UI that downloads media from:
- YouTube
- Instagram
- Facebook
- Loom

It uses `yt-dlp` under the hood.

## Requirements

- Python 3.10+
- `pip`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open:

`http://127.0.0.1:5000`

For production process manager locally:

```bash
gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:5000 app:app
```

## How to use

1. Paste a supported URL (YouTube/Instagram/Facebook/Loom).
2. Click **Analyze**.
3. Click **Download** on any media item.

## Private/restricted content

Some links (especially Instagram/Facebook) require authentication.  
If needed, provide a cookies file for `yt-dlp`:

```bash
export YTDLP_COOKIES_FILE=/absolute/path/to/cookies.txt
python app.py
```

## High quality video + audio

Many YouTube 720p/1080p formats are separate video/audio streams.  
For merged high-quality downloads with audio, install `ffmpeg`.

- macOS (Homebrew): `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`

## Deploy (Docker, recommended)

This repo includes:
- `Dockerfile` (installs `ffmpeg` + app deps)
- `Procfile` (gunicorn web command)
- `render.yaml` (Render blueprint)

Build and run locally with Docker:

```bash
docker build -t ai-insta-download .
docker run --rm -p 5000:5000 ai-insta-download
```

Open:

`http://127.0.0.1:5000`

## Deploy on Render

1. Push this project to GitHub.
2. In Render, click **New +** -> **Blueprint**.
3. Select your repo (Render reads `render.yaml`).
4. Deploy.

Render will build from the included `Dockerfile`, so ffmpeg is available in production.

### Instagram on Render (login/rate limit fix)

Instagram often blocks anonymous requests from datacenter IPs (including cloud hosts).
For Instagram links, configure cookies in Render:

1. Export `cookies.txt` from a browser where you are logged into Instagram.
2. Base64-encode it:

```bash
base64 < cookies.txt | tr -d '\n'
```

3. In Render -> Service -> Environment, add:
   - `YTDLP_COOKIES_B64` = `<that-base64-string>`
4. Redeploy the service.

Supported cookie env vars in this app:
- `YTDLP_COOKIES_B64` (recommended for cloud)
- `YTDLP_COOKIES_FILE` (path on disk)
- `YTDLP_COOKIES_TEXT` (raw cookies.txt content)

## Deploy on Railway

1. Push this project to GitHub.
2. Create a new Railway project from the repo.
3. Railway auto-detects the `Dockerfile` and builds it.
4. Expose the generated domain.

## Notes

- Download only content you own or have permission to use.
- If platform websites/API behavior changes, you may need to update `yt-dlp`.
