import os
import re
import shutil
import tempfile
from urllib.parse import urlparse

import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from flask import Flask, request, Response
from yt_dlp import YoutubeDL

app = Flask(__name__)

LOG_DIR = os.getenv("LOG_DIR", "/logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("downloads")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "downloads.log"),
    maxBytes=2_000_000,   # ~2MB per file
    backupCount=5         # keep last 5 files
)
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)

def now_iso():
    # Use UTC to be consistent across systems (you can change to local if you prefer)
    return datetime.now(timezone.utc).isoformat()

def log_event(event: str, **fields):
    # lightweight key=value log line
    parts = [f"ts={now_iso()}", f"event={event}"]
    for k, v in fields.items():
        if v is None:
            continue
        s = str(v).replace("\n", " ").replace("\r", " ").strip()
        parts.append(f"{k}={s}")
    logger.info(" ".join(parts))

def get_auth_user():
    """
    Return the username forwarded by NPM, if present.
    """
    return (
        request.headers.get("X-Forwarded-User")
        or request.headers.get("Remote-User")
        or "unknown"
    )

def get_client_ip():
    xf = request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip()
    return request.remote_addr


# ---- Limits / validation ----
ALLOWED_HOSTS = {
    # SoundCloud
    "soundcloud.com", "www.soundcloud.com", "m.soundcloud.com",
    # YouTube
    "youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com",
    "youtu.be",
}

MAX_URL_LEN = 300
MAX_DURATION_SEC = 12 * 60            # 12 minutes
MAX_FILESIZE_BYTES = 40 * 1024 * 1024 # 40 MB (approx)

HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SoundCloud / YouTube → MP3</title>
    <meta name="color-scheme" content="dark" />
    <style>
      :root{
        --bg0:#0b0f17;
        --bg1:#0f172a;
        --card: rgba(255,255,255,0.06);
        --card2: rgba(255,255,255,0.08);
        --border: rgba(255,255,255,0.12);
        --text:#e6e8ee;
        --muted:#a6adbb;
        --accent:#7c3aed;
        --accent2:#22c55e;
        --danger:#ef4444;
        --shadow: 0 10px 30px rgba(0,0,0,0.45);
        --radius: 18px;
      }

      * { box-sizing: border-box; }
      html, body { height: 100%; }
      body {
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
        color: var(--text);
        background:
          radial-gradient(1200px 800px at 20% 10%, rgba(124,58,237,0.22), transparent 55%),
          radial-gradient(1000px 700px at 80% 30%, rgba(34,197,94,0.14), transparent 55%),
          linear-gradient(180deg, var(--bg0), var(--bg1));
        display: grid;
        place-items: center;
        padding: 22px;
      }

      .wrap {
        width: 100%;
        max-width: 520px;
      }

      .card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        overflow: hidden;
      }

      header {
        padding: 22px 20px 14px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
      }

      .title {
        display: flex;
        gap: 10px;
        align-items: center;
        margin: 0;
        font-weight: 700;
        letter-spacing: -0.02em;
        font-size: 20px;
      }

      .badge {
        font-size: 12px;
        color: rgba(255,255,255,0.85);
        background: rgba(124,58,237,0.18);
        border: 1px solid rgba(124,58,237,0.35);
        padding: 4px 10px;
        border-radius: 999px;
        white-space: nowrap;
      }

      .sub {
        margin: 10px 0 0;
        color: var(--muted);
        font-size: 14px;
        line-height: 1.4;
      }

      main {
        padding: 18px 20px 20px;
      }

      form { margin: 0; }

      label {
        display: block;
        font-size: 13px;
        color: var(--muted);
        margin-bottom: 8px;
      }

      .row {
        display: grid;
        gap: 12px;
      }

      input[type="url"]{
        width: 100%;
        padding: 14px 14px;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.14);
        background: rgba(0,0,0,0.22);
        color: var(--text);
        font-size: 16px; /* keep >=16px so iOS doesn't auto-zoom */
        outline: none;
        transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
      }

      input[type="url"]::placeholder { color: rgba(166,173,187,0.7); }

      input[type="url"]:focus{
        border-color: rgba(124,58,237,0.6);
        box-shadow: 0 0 0 4px rgba(124,58,237,0.18);
        background: rgba(0,0,0,0.30);
      }

      .btn {
        width: 100%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        border: 0;
        padding: 14px 14px;
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(124,58,237,0.95), rgba(34,197,94,0.78));
        color: white;
        font-size: 16px;
        font-weight: 700;
        cursor: pointer;
        transition: transform .08s ease, filter .15s ease;
      }

      .btn:hover { filter: brightness(1.05); }
      .btn:active { transform: translateY(1px); }

      .foot {
        margin-top: 14px;
        display: grid;
        gap: 10px;
        color: var(--muted);
        font-size: 13px;
        line-height: 1.45;
      }

      .hintbox {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
        padding: 12px 12px;
      }

      .small {
        opacity: 0.95;
      }

      /* Lightweight "loading" state (no JS needed) */
      form:has(button.loading) .spinner { display: inline-block; }
      .spinner {
        display: none;
        width: 14px; height: 14px;
        border-radius: 999px;
        border: 2px solid rgba(255,255,255,0.45);
        border-top-color: rgba(255,255,255,0.95);
        animation: spin 0.9s linear infinite;
      }
      @keyframes spin { to { transform: rotate(360deg); } }

      /* Mobile polish */
      @media (max-width: 420px) {
        header { padding: 18px 16px 12px; }
        main { padding: 16px 16px 18px; }
        .title { font-size: 18px; }
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <header>
          <h1 class="title">
            SoundCloud / YouTube → MP3 
          </h1>
          <p class="sub">Paste a track URL. The server will fetch it, convert to MP3, embed metadata/cover art, then your browser will download it.</p>
        </header>

        <main>
          <form method="post" action="/download" target="_blank">
            <div class="row">
              <div>
                <label for="url">Track URL</label>
                <input id="url" name="url" type="url" inputmode="url" autocomplete="off"
                       placeholder="https://soundcloud.com/… or https://youtu.be/…" required />
              </div>

              <button id="btn" class="btn" type="submit">
                <span class="spinner"></span>
                <span id="btnText">Download MP3</span>
              </button>
            </div>

            <div class="foot">
              <div class="hintbox">
                <div class="small"><strong>Limits:</strong> max duration and filesize are enforced server-side.</div>
                <div class="small"><strong>Private service:</strong> - access limited to users only.</div>
                <div class="small"><strong>Do not share this link publicly.</strong></div>

                <div class="small">Tip: If a link fails, try the main track URL (not a set/playlist).</div>
              </div>
            </div>
          </form>
        </main>
      </div>
    </div>
  </body>
</html>
"""


def safe_filename(name: str) -> str:
    # keep it simple + safe for headers/filesystems
    name = re.sub(r"[^\w\-. ()\[\]]+", "_", name).strip()
    return name[:180] if name else "download"

def validate_url(raw: str) -> str:
    if not raw:
        raise ValueError("Missing URL")
    raw = raw.strip()
    if len(raw) > MAX_URL_LEN:
        raise ValueError("URL too long")

    u = urlparse(raw)
    if u.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")

    host = (u.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError("Only SoundCloud or YouTube URLs are allowed")

    return raw

def format_bytes(n: int) -> str:
    # small helper for friendly errors
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n/1024:.1f}{unit}" if unit != "B" else f"{n}{unit}"
        n /= 1024
    return f"{n:.1f}GB"

@app.get("/")
def index():
    return Response(HTML, mimetype="text/html")

@app.post("/download")
def download():
    try:
        url = validate_url(request.form.get("url", ""))
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        # If behind NPM, X-Forwarded-For may be "client, proxy"; keep first:
        if client_ip and "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

    except ValueError as ve:
        log_event("reject", ip=client_ip, reason=str(ve), url=request.form.get("url", ""))
        return Response(str(ve), status=400)

    # per-request temp workspace
    workdir = tempfile.mkdtemp(prefix="scdl_")

    try:
        outtmpl = os.path.join(workdir, "%(title).200s.%(ext)s")

        # Base options shared between probe + download
        base_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "restrictfilenames": False,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "retries": 2,
        }

        # ---- 1) Probe metadata without downloading ----
        with YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # yt-dlp may return a playlist-like structure even with noplaylist; handle defensively
        if isinstance(info, dict) and info.get("_type") == "playlist" and info.get("entries"):
            # Take the first entry only
            first = next((e for e in info["entries"] if e), None)
            if not first:
                return Response("Could not read media info.", status=400)
            info = first

        duration = int(info.get("duration") or 0)
        if duration and duration > MAX_DURATION_SEC:
            log_event("reject", ip=client_ip, reason="too_long", url=url, title=info.get("title"), duration=duration)
            return Response(
                f"Track too long (max {MAX_DURATION_SEC//60} minutes).",
                status=400
            )

        size = info.get("filesize") or info.get("filesize_approx") or 0
        try:
            size = int(size)
        except Exception:
            size = 0

        if size and size > MAX_FILESIZE_BYTES:
            log_event("reject", ip=client_ip, reason="too_big", url=url, title=info.get("title"), bytes=size)
            return Response(
                f"File too large (max {MAX_FILESIZE_BYTES // (1024*1024)}MB).",
                status=400
            )

        # ---- 2) Download + postprocess with hard limits too ----
        ydl_opts = {
            **base_opts,
            "writethumbnail": True,
            "max_filesize": MAX_FILESIZE_BYTES,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                },
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"},
            ],
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = safe_filename(info.get("title", "download"))
        mp3_path = None

        for fn in os.listdir(workdir):
            if fn.lower().endswith(".mp3"):
                mp3_path = os.path.join(workdir, fn)
                break

        if not mp3_path or not os.path.exists(mp3_path):
            return Response("Failed to produce MP3", status=500)

        # Extra safety: refuse serving if the produced file is too big
        produced_size = os.path.getsize(mp3_path)
        log_event(
        "download_ok",
            user=get_auth_user(),
            ip=client_ip,
            site=(info.get("extractor_key") or info.get("extractor")),
            title=info.get("title"),
            uploader=(info.get("uploader") or info.get("channel")),
            duration=(info.get("duration") or duration),
            bytes=produced_size,
            url=url
        )

        if produced_size > MAX_FILESIZE_BYTES:
            return Response(
                f"Output too large ({produced_size // (1024*1024)}MB).",
                status=400
            )

        def generate():
            with open(mp3_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk

        resp = Response(generate(), mimetype="audio/mpeg")
        resp.headers["Content-Disposition"] = f'attachment; filename="{title}.mp3"'

        @resp.call_on_close
        def _cleanup():
            shutil.rmtree(workdir, ignore_errors=True)

        return resp

    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        log_event("error", ip=client_ip, url=url if "url" in locals() else None, err=repr(e))
        return Response(f"Error: {e}", status=500, mimetype="text/plain")
