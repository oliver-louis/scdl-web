# scdl-web

A small Flask web app that turns supported **SoundCloud** and **YouTube** track URLs into downloadable **MP3** files using `yt-dlp` and `ffmpeg`.

It serves a simple form at `/`, accepts a URL, downloads the best available audio, converts it to MP3, writes metadata, embeds thumbnail art, and streams the final file back to the browser. The app also keeps rotating download logs in `/logs`. 

Hobby project made for personal use, don't expect it to be too polished. Feel free to make your own changes. Pull requests appreciated.

## Features

- Simple web UI for submitting a track URL
- Intended for use with Soundcloud ``soundcloud.com``
- Also supports ``youtube.com`` however yt-dlp often has issues depending on content
- Converts audio to MP3 with `ffmpeg`
- Embeds metadata and cover art
- Rejects playlists and only handles a single item per request
- Enforces server-side limits:
  - max URL length: **300 chars**
  - max duration: **12 minutes**
  - max filesize: **40 MB**
- Writes rotating logs to `./logs/downloads.log`
- Runs cleanly in Docker with Gunicorn

## Stack

- Python 3.12
- Flask
- Gunicorn
- yt-dlp
- ffmpeg
- Docker / Docker Compose

## Project structure

```text
.
├── app.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
└── logs/
```

## Prerequisites

To run with Docker, you need:

- Docker
- Docker Compose

## Quick start with Docker Compose

Clone the repo:

```bash
git clone https://github.com/oliver-louis/scdl-web.git
cd scdl-web
```

Start the app:

```bash
docker compose up --build -d
```

Open it in your browser:

```text
http://localhost:8000
```

Stop it later with:

```bash
docker compose down
```

## What Docker Compose does

The included `docker-compose.yml`:

- builds the image from the local `Dockerfile`
- runs the container as `sc-downloader`
- restarts it automatically unless stopped manually
- exposes port `8000`
- mounts `./logs` on the host to `/logs` in the container
- sets `TZ=Australia/Brisbane`

## Build and run manually with Docker

Build the image:

```bash
docker build -t scdl-web .
```

Run the container:

```bash
docker run -d \
  --name scdl-web \
  -p 8000:8000 \
  -v "$(pwd)/logs:/logs" \
  -e TZ=Australia/Brisbane \
  scdl-web
```

View logs:

```bash
docker logs -f scdl-web
```

Stop and remove the container:

```bash
docker stop scdl-web && docker rm scdl-web
```

## Environment / storage

The app currently uses:

- `LOG_DIR` — defaults to `/logs`
- `TZ` — set in Compose to `Australia/Brisbane`

Downloaded files are created in a temporary working directory per request and cleaned up automatically after the response finishes.

## Running without Docker

You can also run it locally, but you will need **Python 3.12+** and **ffmpeg** installed.

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install `ffmpeg` if you do not already have it.

Then start the app with Gunicorn:

```bash
gunicorn -b 0.0.0.0:8000 app:app --workers 2 --threads 4 --timeout 300
```

Or for simple local development:

```bash
flask --app app run --host=0.0.0.0 --port=8000
```

## Reverse proxy notes

This app does not have any authentication built in. Authentication and user logging requires having a reverse proxy in front of the app.

I would recommend nginx or __Nginx Proxy Manager__ :
- it trusts `X-Forwarded-For` to record the client IP
- it reads `X-Forwarded-User` or `Remote-User` to log the authenticated user
- it serves Gunicorn on port `8000`

If you put it behind a proxy, make sure those headers are forwarded correctly for full functionality.

A minimal Nginx-style example:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-User $remote_user;
}
```

## Logging

The app writes structured log lines to:

```text
./logs/downloads.log
```

It uses a rotating file handler with:

- maximum size: about **2 MB** per log file
- backups kept: **5**

Events include successful downloads, rejections, and server errors.

## Usage notes

- Only HTTP/HTTPS URLs are accepted.
- Only supported SoundCloud and YouTube hosts are allowed.
- Playlist-like URLs are intentionally reduced to a single entry.
- If a track fails, try the main track URL rather than a playlist, set, or mixed page.

## Security / privacy notes

This is best treated as a **private self-hosted service**, not a public downloader.

Reasons:

- the homepage itself describes it as a private service
- it can trigger third-party downloads on behalf of users
- authentication is expected to happen at the reverse proxy layer rather than in Flask itself

If you deploy it publicly, consider adding:

- authentication at the proxy
- rate limiting
- request size / connection limits
- allowlisting or tighter access controls
- monitoring for abuse

## Troubleshooting

### `Error: ffmpeg not found`

Make sure `ffmpeg` is installed. The Docker image already installs it.

### Downloads fail for some URLs

This can happen if:

- the URL is not a direct track/video page
- the media is unavailable or geo-restricted
- the source site changed behavior
- `yt-dlp` needs an update

Updating `yt-dlp` in `requirements.txt` may help.

### `Track too long` or `File too large`

These are expected server-side limits enforced by the app.

### Nothing appears in `./logs`

Make sure the host `logs/` directory exists or Docker has permission to create and write to it.

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Acknowledgements

Built with:

- Flask
- Gunicorn
- yt-dlp
- ffmpeg
