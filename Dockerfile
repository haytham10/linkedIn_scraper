FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Google Chrome (stable) and runtime deps using signed repo (no apt-key)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        gpg \
        ca-certificates && \
    wget -O /tmp/chrome-signing-key.gpg https://dl.google.com/linux/linux_signing_key.pub && \
    gpg --dearmor -o /usr/share/keyrings/chrome-keyring.gpg /tmp/chrome-signing-key.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        google-chrome-stable \
        fonts-liberation \
        libnss3 \
        libxss1 \
        libgbm1 \
        libasound2 \
        libu2f-udev \
        libvulkan1 \
        xdg-utils && \
    rm -rf /var/lib/apt/lists/* /tmp/chrome-signing-key.gpg

ENV CHROME_BINARY=/usr/bin/google-chrome
ENV HEADLESS=true

WORKDIR /app

# Install Python dependencies first (for better docker layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY . .

# Default command runs the v2 scraper; override with `email_enricher.py` as needed
CMD ["python", "lead_scraper_v2.py"]
