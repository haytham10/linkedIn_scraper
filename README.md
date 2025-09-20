
# LinkedIn Lead Scraper & AI Refinement Tool

## 📜 Changelog

### 2025-09-20
- Added in-house Email Enrichment tool: `email_enricher.py`
  - Generates likely corporate emails from first/last names + website domain
  - Validates via MX lookup and safe SMTP RCPT (no emails are sent)
  - Processes only rows with Status = SCRAPED
  - Writes Email and Email Status with allowed values (all-caps):
    - DELIVERABLE, UNDELIVERABLE, CATCH_ALL, MX_UNVERIFIABLE, HEURISTIC (when SMTP disabled)
- Domain derivation now ignores “Company URL” (since it stores LinkedIn profile URLs); prefers Website, Company Website, Website URL
- Email pattern priority updated: first@, first.last@, flast@, firstlast@, …
- Documentation updates: README Email Enrichment section and `.env.example`
- Requirements updated: added `dnspython` and `tldextract`

### 2025-09-19
- v2 direct scraper added: `lead_scraper_v2.py` (no paid providers)
  - Uses undetected-chromedriver for lower bot detection
  - Reuses cookies (linkedin_cookies.json) to avoid frequent logins and 2FA
  - Gentle rate limiting with jitter/backoff and safer status flow (NEW → IN_PROGRESS → SCRAPED/FAILED)
  - Company data via linkedin_scraper.Company (website, industry, description) for reliability
  - Flexible header mapping, including Company URL → official website, and separate fields for LinkedIn company profile URL

### 2025-09-17
- Company name extraction improved: removes employment type (e.g., ' · Full-time')
- Person data extraction now infers title, company name, and company LinkedIn URL directly from experience

### 2025-09-16
- Initial professional code organization for GitHub publication
- Added Google Apps Script for AI-powered lead refinement
- Comprehensive README, .env.example, requirements.txt, and .gitignore added


A comprehensive solution for automated LinkedIn lead generation and AI-powered lead analysis. This tool scrapes LinkedIn profiles, extracts key information, and uses Google's Gemini AI to generate personalized outreach insights.

## 🚀 Features

### LinkedIn Scraper (Python)
- **Automated Profile Scraping**: Extract names, titles, companies, and descriptions
- **Company Data Extraction**: Get company websites, industries, and detailed descriptions  
- **Google Sheets Integration**: Automatically populate spreadsheets with scraped data
- **Smart Rate Limiting**: Human-like delays to avoid detection
- **Error Recovery**: Robust error handling and retry mechanisms
- **Stealth Mode**: Anti-detection measures for reliable scraping

Two flavors:
- v1: `lead_scraper.py` (Selenium + webdriver-manager)
- v2: `lead_scraper_v2.py` (undetected-chromedriver, cookie reuse, safer pacing)

### AI Lead Refinement (Google Apps Script)
- **Pain Point Analysis**: AI identifies likely business challenges
- **Project Type Classification**: Categorizes leads by automation opportunities
- **Personalized Openers**: Generates compelling email opening lines
- **Batch Processing**: Handles multiple leads efficiently
- **Progress Tracking**: Real-time status updates and error reporting

## 📋 Prerequisites

- Python 3.7+
- Google Chrome browser
- Google Cloud account with Sheets API enabled
- Google Gemini API key
- LinkedIn account

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/linkedin-lead-scraper.git
cd linkedin-lead-scraper
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```
This installs undetected-chromedriver for v2.

### 3. Set Up Environment Variables
Copy the example environment file and fill in your credentials:
```bash
cp .env.example .env
```

Edit `.env` with your information:
```env
YOUR_SHEET_NAME=Your Google Sheet Name
LINKEDIN_EMAIL=your.email@example.com
LINKEDIN_PASSWORD=your_password
HEADLESS=true  # optional, set to false to watch the browser
# CHROME_BINARY=C:\\Path\\to\\chrome.exe  # optional override if needed
```

### 4. Configure Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Sheets API
4. Create a service account and download the JSON key
5. Rename the key file to `credentials.json` and place it in the project directory
6. Share your Google Sheet with the service account email

### 5. Set Up Google Apps Script

1. Open your Google Sheet
2. Go to **Extensions > Apps Script**
3. Replace the default code with the contents of `lead_refinement.gs`
4. Go to **Project Settings** (gear icon)
5. Add a new **Script Property**:
   - Property: `GEMINI_API_KEY`
   - Value: Your Google Gemini API key
6. Save the project

## 📊 Google Sheet Setup

### Option 1: Use the Provided Template
We've included a ready-to-use template file: **`LinkedIn Lead Scraper Template.csv`**

1. Download and open the template file
2. Upload it to Google Sheets (File > Import)
3. Share the sheet with your Google service account email
4. Copy the Google Sheets URL and update your `.env` file

### Option 2: Create Your Own Sheet
Your Google Sheet must have these exact column headers:

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| LinkedIn URL | Status | Company | Company Website | Company Industry | Company Description | Name | Title | Pain (guess) | Project Type | Personalized Opener |

### Column Descriptions:
- **LinkedIn URL**: The LinkedIn profile URL to scrape
- **Status**: Processing status (NEW → SCRAPED → COMPLETE)
- **Company**: Company name (filled by scraper)
- **Company Website**: Company website URL (filled by scraper)
- **Company Industry**: Industry classification (filled by scraper)
- **Company Description**: Company about/description text (filled by scraper)
- **Name**: Person's full name (filled by scraper)
- **Title**: Job title (filled by scraper)
- **Pain (guess)**: AI-identified pain points (filled by AI)
- **Project Type**: Suggested automation project (filled by AI)
- **Personalized Opener**: AI-generated opening line (filled by AI)

Header aliases supported (case-insensitive):
- First Name/FirstName/firstName, Last Name/LastName/lastName
- Company/Company Name
- Company Website/Website/Website URL/Company URL → official company website
- Company Industry/Industry
- Company Description/Description
- Company LinkedIn URL/Company Linkedin URL/Company Profile → LinkedIn company profile URL

## 🎯 Usage

### Step 1: Prepare Your Data
1. Add LinkedIn profile URLs to column A
2. Set Status to "NEW" for profiles you want to scrape

### Step 2: Run the Scraper
```bash
# v1 (classic)
python lead_scraper.py

# v2 (direct, undetected-chromedriver + cookies)
python lead_scraper_v2.py
```

The scraper will:
- Process all rows with status "NEW"
- Set row to "IN_PROGRESS" during work (v2)
- Extract profile and company data
- Update the Google Sheet automatically
- Change status to "SCRAPED" when complete (or "FAILED" if nothing meaningful was extracted)

### Step 3: Refine with AI
1. In Google Sheets, go to **🤖 AI Lead Tools > Refine Scraped Leads**
2. The script will analyze all rows with status "SCRAPED"
3. AI will generate pain points, project types, and personalized openers
4. Status will change to "COMPLETE" when finished

## ✉️ Email Enrichment (In-house)

After scraping, run `email_enricher.py` to generate and validate likely corporate email addresses from first/last names plus the company website domain.

What it does
- Normalizes Website → domain (e.g., https://www.example.com → example.com)
- Generates common patterns: first.last@, f.last@, first@, last@, firstl@, l.first@
- Looks up MX records and performs a safe SMTP RCPT check (no email is sent)
- Updates your Google Sheet columns: Email and Email Status

Email Status values (all-caps to match sheet validation)
- DELIVERABLE: RCPT accepted (very likely valid)
- CATCH_ALL: server accepts any address (valid domain, mailbox unconfirmed)
- MX_UNVERIFIABLE: couldn’t reach/verify MX
- UNDELIVERABLE: candidate rejected; script moved to others
- HEURISTIC: SMTP checks disabled; best pattern chosen

Requirements
- `requirements.txt` includes dnspython and tldextract
- `credentials.json` service account has access to your sheet

Environment variables
- YOUR_SHEET_NAME: Required
- ENRICH_SMTP_ENABLED: Default true. Set to false to skip SMTP checks and pick the best heuristic.
- ENRICH_SMTP_TIMEOUT_S: Default 8
- ENRICH_MIN_DELAY_MS / ENRICH_MAX_DELAY_MS: Jitter between SMTP attempts

How to run
1) Ensure `.env` has YOUR_SHEET_NAME and dependencies are installed
2) Run the tool

Notes
- Social domains (linkedin.com, facebook.com, etc.) are ignored as email domains
- The tool prefers Website/Company Website columns; it won’t fall back to LinkedIn profile URLs

## ⚙️ Configuration Options

### Python Scraper Settings

Edit `lead_scraper.py` (v1) to customize:

```python
# Chrome options for different environments
chrome_options.add_argument("--headless")  # Run without browser window
chrome_options.add_argument("--window-size=1920,1080")  # Browser size

# Delay settings (seconds)
smart_delay(8, 15)  # Delay between profiles
smart_delay(3, 5)   # Delay for company pages
```

Edit `lead_scraper_v2.py` (v2) to customize:

```python
# Headless/browser
# Use HEADLESS=false in .env to watch the browser and complete 2FA when needed

# Rate limits
smart_delay(4.5, 9.0)  # post-row pacing

# Cookie persistence
# Cookies are stored in linkedin_cookies.json; delete it if you need to re-login
```

### AI Refinement Settings

Edit `lead_refinement.gs` to customize:

```javascript
// Available project types
PROJECT_TYPES: [
  'Automated Reporting',
  'CRM Data Sync', 
  'Lead Nurturing',
  'Client Onboarding',
  'Internal Process Automation'
]

// Execution time limit
MAX_EXECUTION_TIME: 4.5 * 60 * 1000 // 4.5 minutes
```

## 🔧 Troubleshooting

### Common Issues

#### LinkedIn Login Problems
- **Solution**: Use the browser window to complete 2FA/captcha manually
- **Prevention**: Use application passwords if available

For v2:
- If you’re stuck on login, set `HEADLESS=false` and try again; cookies will save once you reach the feed.
- Delete `linkedin_cookies.json` to force a fresh login.

#### Chrome Driver Issues
- **Error**: "chromedriver.exe not found"
- **Solution**: The script automatically downloads the correct driver
- **Alternative**: Ensure Chrome browser is installed and up to date

#### Google Sheets API Errors
- **Error**: "Insufficient permissions"
- **Solution**: Share your sheet with the service account email
- **Check**: Ensure Google Sheets API is enabled in Google Cloud Console

#### Rate Limiting
- **Error**: Too many requests
- **Solution**: Increase delays in `smart_delay()` functions
- **Recommendation**: Run smaller batches during off-peak hours
- **Tip (v2)**: Keep a steady trickle. The script already adds jitter and backs off; you can raise delays further if you see friction.

### Debugging

1. **Check Logs**: Review `scraper.log` for detailed error information
2. **Test Connection**: Verify Google Sheets and LinkedIn access manually
3. **Validate Data**: Ensure all required columns exist with exact names
4. **API Limits**: Monitor your Gemini API usage quotas

## 📈 Best Practices

### LinkedIn Scraping
- **Respectful Usage**: Don't scrape more than 50-100 profiles per session
- **Human-like Behavior**: Keep random delays between requests
- **Account Safety**: Use dedicated LinkedIn accounts for scraping
- **Legal Compliance**: Only scrape publicly available information

### Data Management
- **Regular Backups**: Export your Google Sheets regularly
- **Data Validation**: Review AI-generated insights before use
- **Privacy**: Don't store sensitive personal information unnecessarily
- **Compliance**: Follow GDPR and other data protection regulations

## 🔒 Security Notes

- **Environment Variables**: Never commit `.env` files to version control
- **API Keys**: Keep your Gemini API key secure and rotate regularly
- **Credentials**: Store Google service account keys safely
- **Access Control**: Limit Google Sheet sharing to necessary users only

## 📄 File Structure

```
linkedin-lead-scraper/
├── lead_scraper.py                   # v1 Python scraper
├── lead_scraper_v2.py                # v2 direct scraper (undetected-chromedriver, cookies)
├── lead_refinement.gs                # Google Apps Script for AI analysis
├── LinkedIn Lead Scraper Template.xlsx # Ready-to-use Google Sheets template
├── requirements.txt                  # Python dependencies
├── .env.example                     # Environment variables template
├── .env                            # Your environment variables (not in repo)
├── credentials.json                # Google service account key (not in repo)
├── .gitignore                      # Git ignore rules
├── scraper.log                     # v1 log file
├── scraper_v2.log                  # v2 log file
└── README.md                       # This file
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This tool is for educational and legitimate business purposes only. Users are responsible for:
- Complying with LinkedIn's Terms of Service
- Respecting robots.txt and rate limits
- Following applicable data protection laws
- Using scraped data ethically and legally

## 🆘 Support

If you encounter issues:

1. Check the [troubleshooting section](#troubleshooting)
2. Review the [issues page](https://github.com/yourusername/linkedin-lead-scraper/issues)
3. Create a new issue with detailed error information

## 🔄 Updates

- **v2.0**: Added AI refinement with Google Gemini
- **v1.5**: Improved error handling and logging
- **v1.0**: Initial release with basic scraping functionality

---

**Made with ❤️ for sales and marketing professionals**

---