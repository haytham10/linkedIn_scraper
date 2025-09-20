#!/usr/bin/env python3

"""
Email Enricher

Generates likely corporate email addresses for each lead using first/last name and the
company website domain. Validates candidates via MX lookup and smart SMTP handshake
without sending email (VRFY is avoided; perform RCPT TO on a null transaction).

- Input: Google Sheet referenced by YOUR_SHEET_NAME with headers like:
  First Name, Last Name, Website (or Company URL/Website URL), Email, Email Status
- Output: Fills Email and Email Status with best match and notes.

Validation strategy:
 1) Normalize website to apex domain.
 2) Generate permutations: first.last, f.last, firstl, first, last, etc.
 3) MX lookup; if no MX, fall back to A record domain.
 4) For each candidate, try SMTP RCPT TO on top MX hosts with a short timeout.
    Cache MX results per domain to minimize DNS/SMTP traffic.
 5) Pick the first positive RCPT; otherwise mark as uncertain and record best heuristic.

Notes:
 - Some providers (Google, Microsoft) accept any RCPT (catch-all) → result = uncertain_catch_all.
 - Some providers hard deny SMTP probing; we'll mark mx_unverifiable and keep the top candidate.
 - Respect rate limiting between SMTP attempts.

Env vars:
  - YOUR_SHEET_NAME (required)
  - ENRICH_EMAIL_CONCURRENCY (optional, default 1)
  - ENRICH_SMTP_TIMEOUT_S (optional, default 8)
  - ENRICH_MIN_DELAY_MS (optional, default 400)
  - ENRICH_MAX_DELAY_MS (optional, default 1100)

Requires credentials.json in project root.
"""

import os
import re
import ssl
import time
import socket
import random
import smtplib
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

import dns.resolver
import tldextract

load_dotenv()

SHEET_NAME = os.getenv("YOUR_SHEET_NAME")
CONCURRENCY = int(os.getenv("ENRICH_EMAIL_CONCURRENCY", "1"))
SMTP_TIMEOUT = int(os.getenv("ENRICH_SMTP_TIMEOUT_S", "8"))
SMTP_ENABLED = os.getenv("ENRICH_SMTP_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
MIN_DELAY_MS = int(os.getenv("ENRICH_MIN_DELAY_MS", "400"))
MAX_DELAY_MS = int(os.getenv("ENRICH_MAX_DELAY_MS", "1100"))

GOOGLE_SHEETS_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_enricher.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class Lead:
    row_number: int
    first: str
    last: str
    website: str
    current_email: str


SOCIAL_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "tiktok.com", "medium.com", "github.com"
}


def normalize_domain(website: str) -> Optional[str]:
    if not website:
        return None
    website = website.strip()
    if not website:
        return None
    if not re.match(r'^https?://', website, flags=re.I):
        website_url = f"http://{website}"
    else:
        website_url = website
    try:
        ext = tldextract.extract(website_url)
        if not ext.domain:
            return None
        domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        domain = (domain or "").lower()
        if domain in SOCIAL_DOMAINS:
            return None
        return domain
    except Exception:
        return None


def connect_to_google_sheets() -> gspread.Worksheet:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", GOOGLE_SHEETS_SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet


def map_headers(sheet: gspread.Worksheet) -> Dict[str, int]:
    headers = [h.strip() for h in sheet.row_values(1)]
    return {h.lower(): idx for idx, h in enumerate(headers, start=1)}


def find_col(header_map: Dict[str, int], names: List[str]) -> Optional[int]:
    for n in names:
        idx = header_map.get(n.strip().lower())
        if idx:
            return idx
    return None


def smart_delay():
    time.sleep(random.uniform(MIN_DELAY_MS/1000.0, MAX_DELAY_MS/1000.0))


def generate_candidates(first: str, last: str, domain: str) -> List[str]:
    first_clean = re.sub(r"[^a-z]", "", (first or "").lower())
    last_clean = re.sub(r"[^a-z]", "", (last or "").lower())
    if not first_clean and not last_clean:
        return []
    f = first_clean
    l = last_clean
    fl = (f[:1] + l) if f else ""
    lf = (l[:1] + f) if l else ""
    combos = []
    pieces = [
        f,                             # first@
        f and l and f"{f}.{l}",      # first.last@
        f and l and fl,               # flast@
        f and l and f"{f}{l}",       # firstlast@
        f and l and f"{f}_{l}",
        f and l and f"{f}-{l}",
        f and l and f"{f[0]}{l}",    # f + last
        f and l and f"{f[0]}.{l}",
        f and l and f"{f}{l[0]}",
        f and l and f"{f}.{l[0]}",
        l,
        lf,                            # lfirst
    ]
    for p in pieces:
        if p:
            combos.append(f"{p}@{domain}")
    # If no personal combinations available (e.g., missing names), add generic inbox fallbacks
    if not combos:
        for alias in ["hello", "contact", "info", "hi", "team", "support", "sales", "admin"]:
            combos.append(f"{alias}@{domain}")
    # de-dupe preserving order
    seen = set()
    result = []
    for c in combos:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


_mx_cache: Dict[str, List[str]] = {}


def get_mx_hosts(domain: str) -> List[str]:
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=5.0)
        hosts = sorted([str(r.exchange).rstrip('.') for r in answers], key=lambda h: h)
        _mx_cache[domain] = hosts
        return hosts
    except Exception:
        # try A record fallback
        try:
            socket.gethostbyname(domain)
            _mx_cache[domain] = [domain]
            return [domain]
        except Exception:
            _mx_cache[domain] = []
            return []


def smtp_rcpt_check(email: str, mx_hosts: List[str]) -> Tuple[str, str]:
    """
    Attempt RCPT TO for given email on the list of MX hosts.
    Returns tuple(status, detail), where status in:
      - deliverable
      - undeliverable
      - catch_all
      - mx_unverifiable
    """
    if not mx_hosts:
        return ("MX_UNVERIFIABLE", "no_mx")

    from_address = "<>"  # null reverse-path avoids bounces
    for host in mx_hosts:
        smart_delay()
        try:
            server = smtplib.SMTP(host=host, port=25, timeout=SMTP_TIMEOUT)
            server.ehlo_or_helo_if_needed()
            try:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            except Exception:
                pass  # not all servers support TLS on 25
            code, _ = server.mail(from_address)
            if code >= 400:
                server.quit()
                continue
            code, _ = server.rcpt(email)
            server.quit()
            if 200 <= code < 300:
                # Might also be catch-all; we try a fake address next to detect
                fake = f"noone-{int(time.time()*1000)}@{email.split('@')[1]}"
                try:
                    server = smtplib.SMTP(host=host, port=25, timeout=SMTP_TIMEOUT)
                    server.ehlo_or_helo_if_needed()
                    try:
                        server.starttls(context=ssl.create_default_context())
                        server.ehlo()
                    except Exception:
                        pass
                    server.mail(from_address)
                    code_fake, _ = server.rcpt(fake)
                    server.quit()
                    if 200 <= code_fake < 300:
                        return ("CATCH_ALL", host)
                    else:
                        return ("DELIVERABLE", host)
                except Exception as e:
                    return ("DELIVERABLE", host)  # can't re-validate; assume deliverable for now
            elif 500 <= code < 600:
                return ("UNDELIVERABLE", host)
            else:
                # 400s or unknown, try next host
                continue
        except (socket.timeout, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, smtplib.SMTPHeloError, smtplib.SMTPDataError, smtplib.SMTPRecipientsRefused, OSError) as e:
            continue
        except Exception as e:
            continue
    return ("MX_UNVERIFIABLE", "all_failed")


def choose_best(candidates: List[str], mx_hosts: List[str]) -> Tuple[str, str]:
    for email in candidates:
        status, detail = smtp_rcpt_check(email, mx_hosts)
        if status == "DELIVERABLE":
            return email, "DELIVERABLE"
        if status == "CATCH_ALL":
            return email, "CATCH_ALL"
        if status == "UNDELIVERABLE":
            continue
        # mx_unverifiable: try next candidate but remember we couldn't verify
    return (candidates[0] if candidates else "", "MX_UNVERIFIABLE")


def update_sheet(sheet: gspread.Worksheet, row_number: int, email: str, status: str) -> None:
    headers = [h.strip() for h in sheet.row_values(1)]
    header_map = {h.lower(): idx for idx, h in enumerate(headers, start=1)}
    email_idx = header_map.get("email")
    status_idx = header_map.get("email status") or header_map.get("email_status") or header_map.get("emailstatus")
    if email_idx:
        sheet.update_cell(row_number, email_idx, email)
    if status_idx:
        sheet.update_cell(row_number, status_idx, status)


def main() -> None:
    if not SHEET_NAME:
        logger.error("YOUR_SHEET_NAME env var is required")
        return
    sheet = connect_to_google_sheets()
    rows = sheet.get_all_records()
    hdr = [h.strip() for h in sheet.row_values(1)]
    header_map = {h.lower(): i for i, h in enumerate(hdr, start=1)}

    # We'll try to derive an official website-like domain; avoid social/linkedin domains.
    # Do NOT use 'Company URL' since in this sheet it stores LinkedIn company profile URLs.
    website_headers_preferred = ["Website", "Company Website", "Website URL"]

    first_idx = header_map.get("first name") or header_map.get("firstname") or header_map.get("firstname")
    last_idx = header_map.get("last name") or header_map.get("lastname") or header_map.get("lastname")
    email_idx = header_map.get("email")
    status_idx_present = header_map.get("status") is not None

    if not first_idx or not last_idx:
        logger.error("First Name and Last Name columns are required.")
        return
    if not status_idx_present:
        logger.error("Status column is required. Email enrichment only processes rows with Status = 'SCRAPED'.")
        return

    processed = 0
    for i, row in enumerate(rows):
        row_number = i + 2
        status_val = (row.get('Status') or '').strip().upper()
        if status_val != 'SCRAPED':
            continue
        first = (row.get('First Name') or row.get('FirstName') or row.get('firstName') or '').strip()
        last = (row.get('Last Name') or row.get('LastName') or row.get('lastName') or '').strip()
        # Try multiple headers for website; prefer official website fields (never use Company URL)
        website = ''
        for h in website_headers_preferred:
            v = row.get(h)
            if v and str(v).strip():
                website = str(v).strip()
                break
        current_email = (row.get('Email') or '').strip()
        if current_email:
            continue  # skip rows with existing email
        domain = normalize_domain(website)
        if not domain:
            logger.info(f"Row {row_number}: no domain derivable; skipping")
            continue
        candidates = generate_candidates(first, last, domain)
        if not candidates:
            logger.info(f"Row {row_number}: no candidates; skipping")
            continue
        if SMTP_ENABLED:
            mx_hosts = get_mx_hosts(domain)
            best_email, status = choose_best(candidates, mx_hosts)
        else:
            # SMTP checks disabled → pick best heuristic and mark status accordingly
            best_email, status = ((candidates[0], "HEURISTIC") if candidates else ("", "HEURISTIC"))
        update_sheet(sheet, row_number, best_email, status)
        processed += 1
        logger.info(f"Row {row_number}: {best_email} [{status}] from {domain}")
        smart_delay()

    logger.info(f"Done. Updated {processed} rows.")


if __name__ == "__main__":
    main()
