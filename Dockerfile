FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Chromium and minimal dependencies for headless mode
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        libnss3 \
        libxss1 \
        libgbm1 \
        libasound2 \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Tell our scripts where Chromium lives
ENV CHROME_BINARY=/usr/bin/chromium
ENV HEADLESS=true

WORKDIR /app

# Install Python dependencies first (for better docker layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY . .

# Default command runs the v2 scraper; override with `email_enricher.py` as needed
CMD ["python", "lead_scraper_v2.py"]
