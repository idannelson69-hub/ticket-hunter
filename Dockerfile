# שלב 1: בניית הממשק (Next.js → קבצים סטטיים)
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# שלב 2: השרת (FastAPI + מנוע הניטור) מגיש גם את הממשק
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static DATABASE_URL=sqlite:////data/tickets.db
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/out ./static
RUN useradd --uid 10001 --no-create-home appuser && mkdir -p /data && chown appuser /data
USER appuser
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
