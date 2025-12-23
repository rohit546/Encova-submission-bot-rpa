"""
Configuration file for Encova automation system
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).parent

# Encova Portal URLs
ENCOVA_LOGIN_URL = "https://agent.encova.com"
ENCOVA_AUTH_URL = "https://auth.encova.com"
ENCOVA_NEW_QUOTE_URL = "https://agent.encova.com/gpa/html/new-quote-account-search"

# Webhook Configuration
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
WEBHOOK_PATH = "/webhook"

# Credentials (to be set via environment variables or config file)
ENCOVA_USERNAME = os.getenv("ENCOVA_USERNAME", "")
ENCOVA_PASSWORD = os.getenv("ENCOVA_PASSWORD", "")

# Browser Configuration (default to headless for production)
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "True").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))  # milliseconds
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Playwright Tracing Configuration
ENABLE_TRACING = os.getenv("ENABLE_TRACING", "True").lower() == "true"
TRACE_DIR = BASE_DIR / "traces"
TRACE_DIR.mkdir(exist_ok=True)

# Timing Constants (seconds)
WAIT_SHORT = 0.3
WAIT_MEDIUM = 0.5
WAIT_LONG = 1.0
WAIT_DROPDOWN_OPEN = 1.5
WAIT_PAGE_LOAD = 2.0
WAIT_WIDGET_LOAD = 3.0
WAIT_LOGIN_COMPLETE = 4.0
WAIT_OKTA_PROCESS = 4.0
WAIT_FORM_APPEAR = 0.5
WAIT_MODAL_APPEAR = 2.0

# Timeout Constants (milliseconds)
TIMEOUT_SHORT = 2000
TIMEOUT_MEDIUM = 5000
TIMEOUT_LONG = 10000
TIMEOUT_LOGIN = 15000
TIMEOUT_WIDGET = 20000
TIMEOUT_PAGE = 90000  # Increased for slow-loading pages and containerized environments

# Session/Cookie storage
SESSION_DIR = BASE_DIR / "sessions"
SESSION_DIR.mkdir(exist_ok=True)

# Logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Coversheet webhook callback URL
COVERSHEET_WEBHOOK_URL = os.getenv(
    'COVERSHEET_WEBHOOK_URL',
    'https://carrier-submission-tracker-system-for-insurance-production.up.railway.app/api/webhooks/rpa-complete'
).strip()

