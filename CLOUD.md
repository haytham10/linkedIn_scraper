# Run the LinkedIn Scraper in the Cloud

This guide shows simple ways to run the scraper (and the email enricher) on a cloud VM or container platform.

## Option A: Docker on a VM (recommended)

Requirements:
- A Linux VM with Docker installed (e.g., AWS EC2, GCP Compute Engine, Azure VM, Hetzner)
- Your service account `credentials.json`
- Your `.env` values (we'll pass as compose env)

Steps:
1. Copy the repo to the VM (git clone or upload) and place `credentials.json` in the project root.
2. Build the image:
   ```bash
   docker compose build
   ```
3. Run the v2 scraper:
   ```bash
   # ensure env vars are exported in your shell or a .env file in this folder
   docker compose run --rm scraper
   ```
4. Run the email enricher:
   ```bash
   docker compose run --rm enricher
   ```

Notes:
- Cookies persist via the bind mount `linkedin_cookies.json` on the host; the first run may require HEADLESS=false locally to pass 2FA, then reuse cookies in the cloud.
- Chromium is installed in the image and referenced via CHROME_BINARY=/usr/bin/chromium.

## Option B: GitHub Actions (manual trigger)
- Create repository secrets for YOUR_SHEET_NAME, LINKEDIN_EMAIL, LINKEDIN_PASSWORD, and base64-encode your `credentials.json` (or use cloud storage and mount at runtime).
- Define a workflow that builds and runs the container on a self-hosted runner (safer for Chrome).

## Option C: Serverless/Containers (Cloud Run, ECS, etc.)
- Use the provided Dockerfile to build and push an image.
- Provide env vars and mount `credentials.json` via a secret/volume.
- Ensure the service allows outbound access for Google Sheets and LinkedIn.

## Troubleshooting
- Chrome headless issues: ensure CHROME_BINARY=/usr/bin/chromium and keep HEADLESS=true.
- 2FA login: generate cookies locally (HEADLESS=false), then copy `linkedin_cookies.json` into the container volume.
- Sheets permissions: share the Google Sheet with the service account in `credentials.json`.