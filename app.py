import os
import re
import shutil
import tempfile
from flask import Flask, request, Response

from yt_dlp import YoutubeDL

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>SoundCloud MP3 Downloader</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; }
      input { width: 100%; padding: 12px; font-size: 16px; }
      button { padding: 12px 16px; font-size: 16px; margin-top: 10px; cursor: pointer; }
      .hint { color: #666; font-size: 14px; margin-top: 8px; }
      .err { color: #b00020; margin-top: 12px; }
    </style>
  </head>
  <body>
    <h1>SoundCloud → MP3</h1>
    <form method="post" action="/download">
      <input name="url" placeholder="Paste SoundCloud URL…" required />
      <button type="submit">Download MP3</button>
    </form>
    <p class="hint">Note: This will fetch and convert audio server-side, then your browser downloads the MP3.</p>
  </body>
</html>
"""

def safe_filename(name: str) -> str:
    # keep it simple + safe for headers/filesystems
    name = re.sub(r"[^\w\-. ()\[\]]+", "_", name).strip()
    return name[:180] if name else "download"

@app.get("/")
def index():
    return Response(HTML, mimetype="text/html")

@app.post("/download")
def download():
    url = request.form.get("url", "").strip()
    if not url:
        return Response("Missing URL", status=400)

    # per-request temp workspace
    workdir = tempfile.mkdtemp(prefix="scdl_")

    try:
        # Use a stable filename template; yt-dlp will fill title/ext for us
        outtmpl = os.path.join(workdir, "%(title).200s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "writethumbnail": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                },
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"},
            ],
            # helps avoid issues if title has weird chars
            "restrictfilenames": False,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = safe_filename(info.get("title", "download"))
        mp3_path = None

        # find the produced mp3 in the temp folder
        for fn in os.listdir(workdir):
            if fn.lower().endswith(".mp3"):
                mp3_path = os.path.join(workdir, fn)
                break

        if not mp3_path or not os.path.exists(mp3_path):
            return Response("Failed to produce MP3", status=500)

        # stream file back to client
        def generate():
            with open(mp3_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    yield chunk

        resp = Response(generate(), mimetype="audio/mpeg")
        resp.headers["Content-Disposition"] = f'attachment; filename="{title}.mp3"'

        # cleanup after response finishes
        @resp.call_on_close
        def _cleanup():
            shutil.rmtree(workdir, ignore_errors=True)

        return resp

    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        return Response(f"Error: {e}", status=500, mimetype="text/plain")
