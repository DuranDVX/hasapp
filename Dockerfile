FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the speech model into the image so the first voice note is not slow.
ENV HF_HOME=/opt/hf
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

COPY app ./app
COPY web ./web

# Files (photos, signatures, documents) live on the Railway volume at /data.
# The database is Postgres (DATABASE_URL), or SQLite on the volume if unset.
ENV HAS_DATA=/data PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
