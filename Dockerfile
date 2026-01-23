FROM python:3.12-slim

# ffmpeg is required for yt-dlp postprocessors (mp3 conversion, metadata, thumbnail embed)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8000

# gunicorn is the “production” web server; NPM will reverse proxy to it
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app", "--workers", "2", "--threads", "4", "--timeout", "300"]
