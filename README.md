# scdl-web

A lightweight Flask web app that converts supported **SoundCloud** (and some YouTube) URLs into downloadable **MP3** files using `yt-dlp` and `ffmpeg`.

It provides a simple web interface, processes a single track per request, embeds metadata and artwork, and streams the final MP3 back to the user. Logs are written to `/logs` with rotation.

> ⚠️ This is a **self-hosted personal tool**, not intended as a public service.

---

## 📚 Table of Contents

- [✨ Features](#features)
- [📦 Installation](#installation)
  - [🚀 Quick Start (Docker)](#quick-start-docker)
  - [🐳 Docker Compose](#docker-compose)
  - [🛠 Manual Docker Build](#manual-docker-build)
  - [💻 Running Locally (Docker Recommended)](#running-locally-docker-recommended)
- [⚙️ Environment & Storage](#environment--storage)
- [🌐 Reverse Proxy](#reverse-proxy)
- [🧾 Logging](#logging)
- [⚠️ Usage Notes](#usage-notes)
- [🔒 Security Notes](#security-notes)
- [🛠 Troubleshooting](#troubleshooting)
- [📄 License](#license)

---

## ✨ Features

- Simple web UI for submitting track URLs
- Supports:
  - `soundcloud.com` (primary)
  - `youtube.com` (best effort via yt-dlp)
- Converts audio to MP3 with `ffmpeg`
- Embeds metadata + cover art
- Rejects playlists (single item only)
- Enforces limits:
  - max URL length: **300 chars**
  - max duration: **12 minutes**
  - max filesize: **40 MB**
- Rotating logs (`./logs/downloads.log`)
- Production-ready via **Gunicorn + Docker**

---

## 🧱 Stack

- Python 3.12
- Flask
- Gunicorn
- yt-dlp
- ffmpeg
- Docker / Docker Compose

---

## 📦 Installation

> ✅ **Docker is the intended and recommended way to run this project.**

---

### 🚀 Quick Start (Docker)

Run instantly using the prebuilt container:

```bash
docker pull ghcr.io/oliver-louis/scdl-web:latest
docker run -p 8000:8000 ghcr.io/oliver-louis/scdl-web:latest
```

Open in browser:

```
http://localhost:8000
```

---

### 🐳 Docker Compose

Clone the repo:

```bash
git clone https://github.com/oliver-louis/scdl-web.git
cd scdl-web
```

Start:

```bash
docker compose up --build -d
```

Stop:

```bash
docker compose down
```

**What this does:**
- Builds from `Dockerfile`
- Runs container (`sc-downloader`)
- Exposes port `8000`
- Mounts logs (`./logs → /logs`)
- Sets timezone (`Australia/Brisbane`)
- Restarts automatically

---

### 🛠 Manual Docker Build

Build:

```bash
docker build -t scdl-web .
```

Run:

```bash
docker run -d \
  --name scdl-web \
  -p 8000:8000 \
  -v "$(pwd)/logs:/logs" \
  -e TZ=Australia/Brisbane \
  scdl-web
```

Logs:

```bash
docker logs -f scdl-web
```

Cleanup:

```bash
docker stop scdl-web && docker rm scdl-web
```

---

### 💻 Running Locally (Docker Recommended)

> ⚠️ Not recommended for production.

Requirements:
- Python 3.12+
- `ffmpeg`

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run (production-style):

```bash
gunicorn -b 0.0.0.0:8000 app:app --workers 2 --threads 4 --timeout 300
```

Dev mode:

```bash
flask --app app run --host=0.0.0.0 --port=8000
```

---

## ⚙️ Environment & Storage

- `LOG_DIR` → defaults to `/logs`
- `TZ` → timezone (set via Docker)

Temporary files are created per request and automatically cleaned up.

---

## 🌐 Reverse Proxy

This app has **no built-in authentication**. Use a reverse proxy.

Recommended:
- Nginx
- Nginx Proxy Manager

Supports:
- `X-Forwarded-For` → client IP
- `X-Forwarded-User` / `Remote-User` → authenticated user

### Example

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-User $remote_user;
}
```

---

## 🧾 Logging

Logs are written to:

```
./logs/downloads.log
```

Rotation:
- ~2 MB per file
- 5 backups

Includes:
- successful downloads
- rejected requests
- errors

---

## ⚠️ Usage Notes

- Only HTTP/HTTPS URLs accepted
- Only supported hosts allowed
- Playlist-like URLs reduced to a single entry
- Some URLs may fail due to platform restrictions

---

## 🔒 Security Notes

This should be treated as a **private self-hosted service**.

If exposed publicly, consider:
- authentication (reverse proxy)
- rate limiting
- IP allowlisting
- abuse monitoring

---

## 🛠 Troubleshooting

### `ffmpeg not found`

Install `ffmpeg` (included in Docker image).

### Downloads fail

Possible causes:
- invalid URL
- geo restrictions
- platform changes
- outdated `yt-dlp`

### File too large / track too long

Expected — enforced limits.

### Logs missing

Ensure `./logs` exists and is writable.

---

## 📄 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.

---

## 🙏 Acknowledgements

- Flask  
- Gunicorn  
- yt-dlp  
- ffmpeg  
