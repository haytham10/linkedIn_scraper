#!/usr/bin/env python3

"""
LinkedIn Lead Scraper v2 (Direct, no paid providers)

Smarter Selenium-based scraper with:
- undetected-chromedriver for lower bot detection
- Cookie reuse (persist session) to avoid frequent logins
- Gentle rate limiting with jitter and backoff
- Flexible header mapping and robust Google Sheets updates
- Minimal DOM dependency: use linkedin_scraper.Person for people; manual company About parsing

Environment variables required:
  - YOUR_SHEET_NAME
  - LINKEDIN_EMAIL
  - LINKEDIN_PASSWORD

Optional env:
  - HEADLESS=true|false (default true)
  - CHROME_BINARY=path to chrome.exe (optional)

Requires credentials.json for Google Sheets service account.
"""

import os
import re
import json
import time
import logging
from typing import Dict, Optional, Tuple, List

import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# Selenium and anti-detection
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from linkedin_scraper import Person, Company  # use library for profile and company parsing


# ================================
# CONFIGURATION & SETUP
# ================================

load_dotenv()

SHEET_NAME = os.getenv("YOUR_SHEET_NAME")
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() in {"1", "true", "yes"}
CHROME_BINARY = os.getenv("CHROME_BINARY")

GOOGLE_SHEETS_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_v2.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ================================
# UTILITIES
# ================================

def smart_delay(min_s: float = 0.8, max_s: float = 2.5) -> None:
    import random
    time.sleep(random.uniform(min_s, max_s))


def backoff_sleep(base: float, attempt: int, jitter: float = 0.4):
    import random
    time.sleep(base * (1.5 ** attempt) + random.uniform(0, jitter))


def parse_name(full_name: str) -> Tuple[str, str]:
    if not full_name:
        return ("", "")
    name = full_name.strip()
    if "," in name:
        name = name.split(",", 1)[0].strip()
    name = re.sub(r"\(.*?\)", "", name).strip()
    parts = [p for p in name.split() if p]
    honorifics = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "madam"}
    parts = [p for p in parts if p.lower().strip('.') not in honorifics]
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    if len(parts) >= 3 and len(parts[1].rstrip('.')) == 1:
        parts = [parts[0]] + parts[2:]
    particles = {"von", "van", "der", "de", "da", "di", "del", "du", "la", "le", "bin", "al"}
    if len(parts) >= 3 and parts[-2].lower() in particles:
        return (parts[0].strip(), f"{parts[-2]} {parts[-1]}".strip())
    return (parts[0].strip(), parts[-1].strip())


def validate_configuration() -> bool:
    missing = []
    if not SHEET_NAME:
        missing.append("YOUR_SHEET_NAME")
    if not LINKEDIN_EMAIL:
        missing.append("LINKEDIN_EMAIL")
    if not LINKEDIN_PASSWORD:
        missing.append("LINKEDIN_PASSWORD")
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}")
        return False
    if not os.path.exists("credentials.json"):
        logger.error("Google Sheets credentials.json not found in project root")
        return False
    return True


# ================================
# DRIVER & AUTH
# ================================

COOKIES_PATH = "linkedin_cookies.json"


def init_driver():
    chrome_opts = uc.ChromeOptions()
    if HEADLESS:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--disable-features=VizDisplayCompositor")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_argument("--lang=en-US,en")
    if CHROME_BINARY:
        chrome_opts.binary_location = CHROME_BINARY
    driver = uc.Chrome(options=chrome_opts)
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(45)
    return driver


def save_cookies(driver) -> None:
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(cookies, f)
    except Exception as e:
        logger.debug(f"Could not save cookies: {e}")


def load_cookies(driver) -> bool:
    if not os.path.exists(COOKIES_PATH):
        return False
    try:
        driver.get("https://www.linkedin.com/")
        with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        for c in cookies:
            # Selenium expects 'expiry' as int not float
            if 'expiry' in c and isinstance(c['expiry'], float):
                c['expiry'] = int(c['expiry'])
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.get("https://www.linkedin.com/feed/")
        smart_delay(1.2, 2.2)
        return True
    except Exception as e:
        logger.debug(f"Could not load cookies: {e}")
        return False


def is_logged_in(driver) -> bool:
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='me/']"))
        )
        return True
    except TimeoutException:
        return False


def login(driver) -> None:
    # Try cookies first
    if load_cookies(driver) and is_logged_in(driver):
        logger.info("Logged in via persisted cookies")
        return

    logger.info("Logging into LinkedIn with credentials...")
    driver.get("https://www.linkedin.com/login")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(LINKEDIN_EMAIL)
        driver.find_element(By.ID, "password").send_keys(LINKEDIN_PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(driver, 20).until(EC.url_contains("/feed"))
        smart_delay(1.0, 2.0)
        save_cookies(driver)
        logger.info("Login successful")
    except Exception as e:
        logger.warning(f"Login flow encountered an issue: {e}. If there's 2FA/Captcha, please solve it in the browser.")
        try:
            WebDriverWait(driver, 120).until(EC.url_contains("/feed"))
            save_cookies(driver)
            logger.info("Login completed after manual step")
        except TimeoutException:
            raise RuntimeError("Login failed or timed out")


# ================================
# SCRAPERS
# ================================

def scrape_person(driver, profile_url: str) -> Dict[str, str]:
    """Use linkedin_scraper.Person to parse minimal data reliably."""
    try:
        smart_delay(1.2, 2.2)
        person = Person(profile_url, driver=driver, scrape=True, close_on_complete=False)
        full_name = getattr(person, 'name', '') or ''
        first, last = parse_name(full_name)
        experiences = getattr(person, 'experiences', []) or []
        title = ''
        company_name = ''
        company_url = ''
        if experiences:
            exp0 = experiences[0]
            title = (getattr(exp0, 'position_title', '') or '').strip()
            raw_comp = (getattr(exp0, 'institution_name', '') or '').strip()
            company_name = raw_comp.split(' · ', 1)[0].strip() if ' · ' in raw_comp else raw_comp
            company_url = (getattr(exp0, 'linkedin_url', '') or '').strip()
        return {
            'first_name': first,
            'last_name': last,
            'title': title or 'Title Not Found',
            'company_name': company_name or 'Company Not Found',
            'company_linkedin_url': company_url or '',
        }
    except Exception as e:
        logger.warning(f"Person scrape failed: {e}")
        return {
            'first_name': '',
            'last_name': '',
            'title': 'Extraction Failed',
            'company_name': 'Extraction Failed',
            'company_linkedin_url': ''
        }


def clean_company_description(raw_description: str) -> str:
    if not raw_description:
        return 'Not Found'
    # Remove HTML tags
    clean_desc = re.sub(r'<[^>]+>', '', raw_description)
    # Remove HTML entities
    clean_desc = re.sub(r'&[a-zA-Z]+;', '', clean_desc)
    # Normalize whitespace
    clean_desc = re.sub(r'\n+', '\n', clean_desc)
    clean_desc = clean_desc.strip()
    if len(clean_desc) > 500:
        clean_desc = clean_desc[:500] + '...'
    return clean_desc


def scrape_company_about(driver, company_url: str) -> Dict[str, str]:
    if not company_url:
        return {'website': 'No Company URL', 'industry': 'No Company URL', 'description': 'No Company URL'}
    try:
        smart_delay(1.5, 3.0)
        company = Company(
            company_url,
            driver=driver,
            get_employees=False,
            scrape=True,
            close_on_complete=False,
        )
        website = getattr(company, 'website', '') or 'Not Found'
        industry = getattr(company, 'industry', '') or 'Not Found'
        raw_desc = getattr(company, 'about_us', '')
        description = clean_company_description(raw_desc)
        return {
            'website': website,
            'industry': industry,
            'description': description,
        }
    except Exception as e:
        logger.warning(f"Company scrape failed: {e}")
        return {'website': 'Extraction Failed', 'industry': 'Extraction Failed', 'description': 'Extraction Failed'}


# ================================
# GOOGLE SHEETS
# ================================

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


def update_row_by_headers(sheet: gspread.Worksheet, row_number: int, values_by_header: Dict[str, str]) -> None:
    headers = [h.strip() for h in sheet.row_values(1)]
    header_map = {h.lower(): idx for idx, h in enumerate(headers, start=1)}
    requests = []
    for key, val in values_by_header.items():
        idx = header_map.get(key.strip().lower())
        if idx:
            a1 = gspread.utils.rowcol_to_a1(row_number, idx)
            requests.append({"range": a1, "values": [[val]]})
    # fallback to per-cell if batch_update not straightforward
    for req in requests:
        sheet.update(req["values"], req["range"])  # pass values first, then range_name


# ================================
# MAIN
# ================================

def process_row(row: Dict[str, str], row_number: int, sheet: gspread.Worksheet, driver) -> bool:
    header_map = map_headers(sheet)
    url_idx = find_col(header_map, ["LinkedIn URL", "LinkedIn", "Profile", "LinkedInProfile", "Profile URL"])
    if not url_idx:
        logger.error("No LinkedIn URL column found")
        return False
    linkedin_url = (row.get('LinkedIn URL') or row.get('LinkedIn') or row.get('Profile') or row.get('LinkedInProfile') or row.get('Profile URL') or '').strip()
    if not linkedin_url:
        # Try reading raw cell if keys are inconsistent
        try:
            cell_val = sheet.cell(row_number, url_idx).value
            linkedin_url = (cell_val or '').strip()
        except Exception:
            pass
    if not linkedin_url:
        logger.warning(f"Row {row_number}: No LinkedIn URL")
        return False

    # Mark IN_PROGRESS if Status exists
    status_idx = find_col(header_map, ["Status"])
    if status_idx:
        try:
            sheet.update_cell(row_number, status_idx, "IN_PROGRESS")
        except Exception:
            pass

    # Person
    person = scrape_person(driver, linkedin_url)
    smart_delay(1.0, 2.0)

    # Company
    if person.get('company_linkedin_url'):
        company = scrape_company_about(driver, person['company_linkedin_url'])
    else:
        company = {'website': 'No Company URL', 'industry': 'No Company URL', 'description': 'No Company URL'}

    values = {
        'First Name': person.get('first_name', ''),
        'FirstName': person.get('first_name', ''),
        'firstName': person.get('first_name', ''),
        'Last Name': person.get('last_name', ''),
        'LastName': person.get('last_name', ''),
        'lastName': person.get('last_name', ''),
        'Title': person.get('title', ''),
        'Company': person.get('company_name', ''),
        'Company Name': person.get('company_name', ''),
        'Company URL': person.get('company_linkedin_url', ''),
        'Company LinkedIn URL': person.get('company_linkedin_url', ''),
        'Company Linkedin URL': person.get('company_linkedin_url', ''),
        'Company Profile': person.get('company_linkedin_url', ''),
        'Website': company.get('website', ''),
        'Industry': company.get('industry', ''),
        'Company Industry': company.get('industry', ''),
        'Description': company.get('description', ''),
        'Company Description': company.get('description', ''),
    }
    present = set([h.strip().lower() for h in sheet.row_values(1)])
    filtered = {k: v for k, v in values.items() if k.strip().lower() in present}

    # Decide success
    has_person = any([
        person.get('first_name'), person.get('last_name'), person.get('title'), person.get('company_name')
    ])
    has_company = any([
        company.get('website') and company['website'] not in ('', 'Not Found', 'No Company URL', 'Extraction Failed'),
        company.get('industry') and company['industry'] not in ('', 'Not Found', 'No Company URL', 'Extraction Failed'),
        company.get('description') and company['description'] not in ('', 'Not Found', 'No Company URL', 'Extraction Failed'),
    ])

    if has_person or has_company:
        update_row_by_headers(sheet, row_number, filtered)
        if status_idx:
            try:
                sheet.update_cell(row_number, status_idx, 'SCRAPED')
            except Exception:
                pass
        logger.info(f"Row {row_number}: SCRAPED {person.get('first_name','')} {person.get('last_name','')} @ {person.get('company_name','')}")
        smart_delay(4.5, 9.0)  # Be gentle
        return True
    else:
        if status_idx:
            try:
                sheet.update_cell(row_number, status_idx, 'FAILED')
            except Exception:
                pass
        logger.warning(f"Row {row_number}: No data extracted; marked FAILED")
        smart_delay(2.0, 4.0)
        return False


def main() -> None:
    logger.info("=== LinkedIn Lead Scraper v2 (Direct) ===")
    if not validate_configuration():
        logger.error("Invalid configuration; exiting")
        return

    # Sheets
    sheet = connect_to_google_sheets()
    rows = sheet.get_all_records()
    logger.info(f"Loaded {len(rows)} rows from sheet '{SHEET_NAME}'")

    # Driver
    driver = init_driver()
    try:
        login(driver)

        processed = 0
        failed = 0
        for i, row in enumerate(rows):
            row_number = i + 2
            status = (row.get('Status') or '').strip()
            if status and status != 'NEW':
                continue
            try:
                ok = process_row(row, row_number, sheet, driver)
                if ok:
                    processed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.exception(f"Row {row_number} crashed: {e}")
                failed += 1
                # backoff a bit to cool down
                backoff_sleep(1.0, 1)

        logger.info(f"Done. Processed: {processed}, Failed: {failed}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
