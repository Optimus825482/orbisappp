# =============================================================================
# ORBIS Astrology - Flask Backend Dockerfile
# Coolify / Docker deployment için
# =============================================================================

FROM python:3.11-slim

# Çalışma dizini
WORKDIR /app

# System dependencies (pyswisseph için gerekli)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Application code
COPY . .

# Environment variables
ENV FLASK_APP=wsgi.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PORT=8005

# Expose port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8005/api/health || exit 1

# Start command with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8005", "--workers", "4", "--threads", "2", "--timeout", "120", "wsgi:app"]
