# scdl-web

A lightweight Flask web app that converts supported **SoundCloud** (and some YouTube) URLs into downloadable **MP3** files using `yt-dlp` and `ffmpeg`.

It provides a simple web interface, processes a single track per request, embeds metadata and artwork, and streams the final MP3 back to the user. Logs are written to `/logs` with rotation.

> ⚠️ This is a **self-hosted personal tool**, not intended as a public service.

---

## 📚 Table of Contents

- [✨ Features](#-features)
- [📦 Installation](#-installation)
  - [🚀 Quick Start (Docker)](#-quick-start-docker)
  - [🐳 Docker Compose](#-docker-compose)
  - [🛠 Manual Docker Build](#-manual-docker-build)
  - [💻 Running Locally (Docker Recommended)](#-running-locally-docker-recommended)
- [⚙️ Environment & Storage](#-environment--storage)
- [🔐 Authentication](#-authentication)
  - [Default: no built-in auth](#default-no-built-in-auth)
  - [Proxy header auth](#proxy-header-auth)
  - [Authentik / OpenID Connect](#authentik--openid-connect)
- [🌐 Reverse Proxy](#-reverse-proxy)
- [🧾 Logging](#-logging)
- [⚠️ Usage Notes](#-usage-notes)
- [🔒 Security Notes](#-security-notes)
- [🛠 Troubleshooting](#-troubleshooting)
- [📄 License](#-license)

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
- Optional authentication modes:
  - no built-in auth
  - reverse-proxy forwarded user headers
  - Authentik / OpenID Connect
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
- `AUTH_MODE` → auth mode, defaults to `none`

Temporary files are created per request and automatically cleaned up.

Copy `.env.example` to your deployment environment or pass equivalent variables through Docker Compose, Unraid, or your container manager. Do not commit real secrets.

---

## 🔐 Authentication

The app supports three auth modes:

| Mode | Description |
| --- | --- |
| `none` | Default. No built-in authentication. Use only on a trusted private network or behind another access control layer. |
| `proxy` | Requires a trusted reverse proxy to send `X-Forwarded-User` or `Remote-User`. |
| `oidc` | Uses Authentik / OpenID Connect with a server-side authorization-code flow. |

### Default: no built-in auth

By default, Docker Compose runs with:

```env
AUTH_MODE=none
```

This preserves the original behavior. Anyone who can reach the app can use it.

### Proxy header auth

Use this if another trusted service authenticates users before requests reach this app:

```env
AUTH_MODE=proxy
```

Authenticated requests must include one of:

```txt
X-Forwarded-User
Remote-User
```

Optional headers used for logging/user metadata:

```txt
X-Forwarded-Email
X-Forwarded-Groups
```

Only enable this mode when the app is reachable exclusively through a proxy that strips untrusted incoming auth headers.

### Authentik / OpenID Connect

Use this mode for direct OIDC login through Authentik:

```env
AUTH_MODE=oidc
SECRET_KEY=replace-with-a-long-random-value
PUBLIC_BASE_URL=https://scdl.example.com
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Lax

OIDC_CLIENT_ID=scdl-web
OIDC_CLIENT_SECRET=replace-with-authentik-client-secret
OIDC_DISCOVERY_URL=https://auth.example.com/application/o/scdl-web/.well-known/openid-configuration
OIDC_SCOPES=openid profile email
OIDC_ALLOWED_GROUPS=
OIDC_GROUPS_CLAIM=groups
OIDC_USERNAME_CLAIM=preferred_username
OIDC_SESSION_MAX_AGE_SECONDS=28800
OIDC_END_SESSION_URL=https://auth.example.com/application/o/scdl-web/end-session/
```

For local testing over plain HTTP:

```env
PUBLIC_BASE_URL=http://localhost:8000
SESSION_COOKIE_SECURE=false
```

#### Authentik provider setup

Create an **OAuth2/OpenID Provider** in Authentik:

- Client type: `Confidential`
- Authorization flow: explicit or implicit consent provider flow
- Redirect URI for local testing: `http://localhost:8000/auth/callback`
- Redirect URI for deployment: `https://scdl.example.com/auth/callback`
- Scopes/property mappings: `openid`, `profile`, `email`

The app uses the OAuth2 authorization-code flow. Authentik's explicit/implicit consent provider-flow setting only controls whether users see a consent screen; it is not the legacy OAuth implicit grant.

After login, the app keeps its own Flask session. This is separate from the user's Authentik browser session, so changing Authentik consent/session duration does not automatically expire an already-authenticated app session.

By default, OIDC app sessions expire **8 hours** after login:

```env
OIDC_SESSION_MAX_AGE_SECONDS=28800
```

Set it to `0` to disable app-side session expiry and keep the old browser-session-cookie behavior:

```env
OIDC_SESSION_MAX_AGE_SECONDS=0
```

Use Authentik application policies/groups if you want Authentik-only access control. In that case, leave:

```env
OIDC_ALLOWED_GROUPS=
```

If you also want the Flask app to enforce group membership, set a comma-separated allowlist:

```env
OIDC_ALLOWED_GROUPS=scdl-users,admins
```

---

## 🌐 Reverse Proxy

Use a reverse proxy for TLS termination and production routing.

Recommended:
- Nginx
- Nginx Proxy Manager

Supports:
- `X-Forwarded-For` → client IP
- `X-Forwarded-Proto` / `X-Forwarded-Host` → public URL generation
- `X-Forwarded-User` / `Remote-User` → authenticated user when `AUTH_MODE=proxy`

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
- `AUTH_MODE=oidc` with Authentik or another trusted OIDC provider
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
