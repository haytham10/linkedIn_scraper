#!/usr/bin/env python3

import os
import re
import time
import getpass
import logging
from datetime import datetime
from typing import Dict, Optional, List

# Third-party imports
import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from linkedin_scraper import Person, Company, actions
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ================================
# CONFIGURATION & SETUP
# ================================

# Load environment variables
load_dotenv()

# Configuration from environment
SHEET_NAME = os.getenv("YOUR_SHEET_NAME")
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

# Google Sheets configuration
GOOGLE_SHEETS_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================================
# UTILITY FUNCTIONS
# ================================

def validate_configuration() -> bool:
    """
    Validate that all required configuration variables are set.
    
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    missing_vars = []
    
    if not SHEET_NAME:
        missing_vars.append("YOUR_SHEET_NAME")
    if not LINKEDIN_EMAIL:
        missing_vars.append("LINKEDIN_EMAIL")
    if not LINKEDIN_PASSWORD:
        missing_vars.append("LINKEDIN_PASSWORD")
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please check your .env file")
        return False
    
    if not os.path.exists("credentials.json"):
        logger.error("Google Sheets credentials.json file not found")
        return False
    
    return True

def smart_delay(min_seconds: float = 2, max_seconds: float = 5) -> None:
    """
    Introduce a random delay to mimic human behavior.
    
    Args:
        min_seconds: Minimum delay time
        max_seconds: Maximum delay time
    """
    import random
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

# ================================
# CHROME DRIVER SETUP
# ================================

def initialize_chrome_driver() -> webdriver.Chrome:
    """
    Initialize Chrome WebDriver with optimized settings for LinkedIn scraping.
    
    Returns:
        webdriver.Chrome: Configured Chrome driver instance
    """
    logger.info("Initializing Chrome WebDriver...")
    
    chrome_options = Options()
    
    # Performance and stability options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"  # Adjust path
    
    # Stealth options to avoid detection
    # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    # chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Logging options
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    
    # Uncomment for headless mode (no browser window)
    # chrome_options.add_argument("--headless")
    
    try:
        # Use WebDriverManager for automatic driver management
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Remove webdriver property to avoid detection
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("Chrome WebDriver initialized successfully")
        return driver
        
    except Exception as e:
        logger.error(f"Failed to initialize Chrome WebDriver: {e}")
        raise

# ================================
# LINKEDIN AUTHENTICATION
# ================================

def login_to_linkedin(driver: webdriver.Chrome) -> None:
    """
    Handle LinkedIn authentication process.
    
    Args:
        driver: Chrome WebDriver instance
    """
    logger.info("Logging into LinkedIn...")
    
    email = LINKEDIN_EMAIL or input("Enter LinkedIn Email: ")
    password = LINKEDIN_PASSWORD or getpass.getpass("Enter LinkedIn Password: ")
    
    try:
        logger.info("Attempting login...")
        actions.login(driver, email, password)
        logger.info("Successfully logged into LinkedIn")
        
    except Exception as e:
        logger.error(f"LinkedIn login failed: {e}")
        logger.info("You may need to complete manual verification (2FA/Captcha)")
        input("Please complete any verification in the browser, then press Enter...")

# ================================
# DATA EXTRACTION FUNCTIONS
# ================================

def extract_person_data(person_url: str, driver: webdriver.Chrome) -> Dict[str, str]:
    """
    Extract comprehensive person data from LinkedIn profile.
    
    Args:
        person_url: LinkedIn profile URL
        driver: Chrome WebDriver instance
        
    Returns:
        Dict containing extracted person data
    """
    logger.info(f"Extracting person data from: {person_url}")
    
    try:
        smart_delay(2, 4)  # Respectful delay
        
        person = Person(person_url, driver=driver, scrape=True, close_on_complete=False)
        
        # Extract basic information
        name = getattr(person, 'name', 'N/A')
        title = getattr(person, 'title', None)
        company_name = getattr(person, 'company', 'N/A')
        company_linkedin_url = getattr(person, 'company_linkedin_url', None)
        
        # Enhanced title inference
        if not title or title.strip() == "":
            title = infer_title_from_experience(person, company_name)
            
        # Enhanced company URL construction
        if not company_linkedin_url or company_linkedin_url == "N/A":
            company_linkedin_url = infer_company_url_from_experience(person)
        
        logger.info(f"Extracted data for {name} at {company_name}")
        
        return {
            'name': name or 'N/A',
            'title': title or 'Title Not Found',
            'company_name': company_name or 'N/A',
            'company_linkedin_url': company_linkedin_url or 'N/A'
        }
        
    except Exception as e:
        logger.error(f"Failed to extract person data: {e}")
        return {
            'name': 'Extraction Failed',
            'title': 'Extraction Failed',
            'company_name': 'Extraction Failed',
            'company_linkedin_url': 'Extraction Failed'
        }

def infer_title_from_experience(person: Person, company_name: str) -> str:
    """
    Attempt to infer job title from experience data.
    
    Args:
        person: LinkedIn Person object
        company_name: Current company name
        
    Returns:
        Inferred title or default message
    """
    logger.info("Attempting to infer title from experience...")
    
    experiences = getattr(person, 'experiences', [])
    if not experiences:
        return "Title Not Found"
    
    current_exp = experiences[0]
    
    # Check if current experience matches company
    if getattr(current_exp, 'institution_name', '').lower() == company_name.lower():
        inferred_title = getattr(current_exp, 'position_title', None)
        
        if not inferred_title or inferred_title.strip() == "":
            # Try to extract from description
            desc = getattr(current_exp, 'description', '')
            if desc:
                inferred_title = desc.split('\n')[0].split('.')[0].strip()[:50] + "..."
            else:
                inferred_title = "Role Not Specified"
        
        logger.info(f"Inferred title: {inferred_title}")
        return inferred_title
    
    return "Title Not Found"

def infer_company_url_from_experience(person: Person) -> Optional[str]:
    """
    Attempt to infer company LinkedIn URL from experience data.
    
    Args:
        person: LinkedIn Person object
        
    Returns:
        Company LinkedIn URL or None
    """
    experiences = getattr(person, 'experiences', [])
    if not experiences:
        return None
    
    current_exp = experiences[0]
    exp_company_url = getattr(current_exp, 'linkedin_url', None)
    
    if exp_company_url:
        logger.info(f"Inferred company URL: {exp_company_url}")
        return exp_company_url.strip()
    
    return None

def extract_company_data(company_url: str, driver: webdriver.Chrome) -> Dict[str, str]:
    """
    Extract comprehensive company data from LinkedIn company page.
    
    Args:
        company_url: LinkedIn company page URL
        driver: Chrome WebDriver instance
        
    Returns:
        Dict containing extracted company data
    """
    if not company_url or company_url == "N/A":
        return {
            'website': 'No Company URL',
            'industry': 'No Company URL',
            'description': 'No Company URL'
        }
    
    logger.info(f"Extracting company data from: {company_url}")
    
    try:
        smart_delay(3, 5)  # Longer delay for company pages
        
        company = Company(
            company_url, 
            driver=driver, 
            get_employees=False, 
            scrape=True, 
            close_on_complete=False
        )
        
        # Extract and clean company data
        website = getattr(company, 'website', '') or 'Not Found'
        industry = getattr(company, 'industry', '') or 'Not Found'
        
        # Clean company description
        raw_description = getattr(company, 'about_us', '')
        description = clean_company_description(raw_description)
        
        logger.info("Company data extracted successfully")
        
        return {
            'website': website,
            'industry': industry,
            'description': description
        }
        
    except Exception as e:
        logger.warning(f"Company data extraction failed: {e}")
        return {
            'website': 'Extraction Failed',
            'industry': 'Extraction Failed',
            'description': 'Extraction Failed'
        }

def clean_company_description(raw_description: str) -> str:
    """
    Clean and format company description text.
    
    Args:
        raw_description: Raw description text from LinkedIn
        
    Returns:
        Cleaned description text
    """
    if not raw_description:
        return 'Not Found'
    
    # Remove HTML tags
    clean_desc = re.sub(r'<[^>]+>', '', raw_description)
    
    # Remove HTML entities
    clean_desc = re.sub(r'&[a-zA-Z]+;', '', clean_desc)
    
    # Normalize whitespace
    clean_desc = re.sub(r'\n+', '\n', clean_desc)
    
    # Trim and limit length
    clean_desc = clean_desc.strip()
    if len(clean_desc) > 500:
        clean_desc = clean_desc[:500] + "..."
    
    return clean_desc

# ================================
# GOOGLE SHEETS INTEGRATION
# ================================

def connect_to_google_sheets() -> gspread.Worksheet:
    """
    Establish connection to Google Sheets.
    
    Returns:
        Google Sheets worksheet object
    """
    logger.info("Connecting to Google Sheets...")
    
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "credentials.json", 
            GOOGLE_SHEETS_SCOPE
        )
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        
        logger.info("Successfully connected to Google Sheets")
        return sheet
        
    except Exception as e:
        logger.error(f"Failed to connect to Google Sheets: {e}")
        raise

def update_sheet_row(sheet: gspread.Worksheet, row_number: int, data: List[str]) -> None:
    """
    Update a specific row in the Google Sheet with extracted data.
    
    Args:
        sheet: Google Sheets worksheet object
        row_number: Row number to update (1-indexed)
        data: List of data to write to the row
    """
    try:
        # Update columns C through H with extracted data
        range_name = f"C{row_number}:H{row_number}"
        sheet.update(values=[data], range_name=range_name)
        
        # Update status to SCRAPED
        sheet.update_cell(row_number, 2, "SCRAPED")
        
        logger.info(f"Updated row {row_number} in Google Sheets")
        
    except Exception as e:
        logger.error(f"Failed to update sheet row {row_number}: {e}")
        # Mark as failed if we can't update
        try:
            sheet.update_cell(row_number, 2, "FAILED")
        except:
            pass
        raise

# ================================
# MAIN SCRAPING LOGIC
# ================================

def process_lead(row_data: Dict, row_number: int, driver: webdriver.Chrome, 
                sheet: gspread.Worksheet) -> bool:
    """
    Process a single lead from the spreadsheet.
    
    Args:
        row_data: Dictionary containing row data
        row_number: Row number in the sheet (1-indexed)
        driver: Chrome WebDriver instance
        sheet: Google Sheets worksheet object
        
    Returns:
        bool: True if successful, False otherwise
    """
    linkedin_url = row_data.get("LinkedIn URL", "").strip()
    
    if not linkedin_url:
        logger.warning(f"Row {row_number}: No LinkedIn URL found")
        return False
    
    logger.info(f"Processing lead #{row_number}: {linkedin_url}")
    
    try:
        # Extract person data
        person_data = extract_person_data(linkedin_url, driver)
        
        # Extract company data if company URL is available
        company_data = {}
        if person_data['company_linkedin_url'] not in ['N/A', 'Extraction Failed']:
            company_data = extract_company_data(
                person_data['company_linkedin_url'], 
                driver
            )
        else:
            logger.info("Skipping company extraction (no valid URL)")
            company_data = {
                'website': 'No Company URL',
                'industry': 'No Company URL',
                'description': 'No Company URL'
            }
        
        # Prepare data for sheet update
        update_data = [
            person_data['company_name'],
            company_data.get('website', 'Not Found'),
            company_data.get('industry', 'Not Found'),
            company_data.get('description', 'Not Found'),
            person_data['name'],
            person_data['title']
        ]
        
        # Update the sheet
        update_sheet_row(sheet, row_number, update_data)
        
        logger.info(f"Successfully processed: {person_data['name']} at {person_data['company_name']}")
        
        # Respectful delay before next profile
        smart_delay(8, 15)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to process lead {linkedin_url}: {e}")
        try:
            sheet.update_cell(row_number, 2, "FAILED")
        except:
            pass
        return False

def main() -> None:
    """
    Main function to orchestrate the LinkedIn scraping process.
    """
    logger.info("=== LinkedIn Lead Scraper Started ===")
    
    # Validate configuration
    if not validate_configuration():
        logger.error("Configuration validation failed. Exiting.")
        return
    
    driver = None
    processed_count = 0
    failed_count = 0
    
    try:
        # Connect to Google Sheets
        sheet = connect_to_google_sheets()
        
        # Initialize Chrome driver
        driver = initialize_chrome_driver()
        
        # Login to LinkedIn
        login_to_linkedin(driver)
        
        # Get all rows from the sheet
        rows = sheet.get_all_records()
        headers = sheet.row_values(1)
        
        logger.info(f"Found {len(rows)} rows in the sheet")
        
        # Process each row
        for i, row in enumerate(rows):
            row_number = i + 2  # Google Sheets is 1-indexed, plus header row
            status = row.get("Status", "").strip()
            
            # Only process rows with status "NEW"
            if status != "NEW":
                logger.info(f"Skipping row {row_number} (Status: {status})")
                continue
            
            # Process the lead
            if process_lead(row, row_number, driver, sheet):
                processed_count += 1
            else:
                failed_count += 1
        
        logger.info(f"Scraping complete! Processed: {processed_count}, Failed: {failed_count}")
        
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Chrome WebDriver closed")
            except:
                pass

# ================================
# SCRIPT ENTRY POINT
# ================================

if __name__ == "__main__":
    main()