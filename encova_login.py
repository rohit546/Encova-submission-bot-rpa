"""
Encova Portal Login Automation
Handles both first-time login and auto-login scenarios
"""
import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page
from config import (
    ENCOVA_LOGIN_URL,
    ENCOVA_NEW_QUOTE_URL,
    ENCOVA_USERNAME,
    ENCOVA_PASSWORD,
    BROWSER_HEADLESS,
    BROWSER_TIMEOUT,
    BROWSER_USER_AGENT,
    SESSION_DIR,
    LOG_DIR,
    WAIT_SHORT,
    WAIT_MEDIUM,
    WAIT_LONG,
    WAIT_DROPDOWN_OPEN,
    WAIT_PAGE_LOAD,
    WAIT_WIDGET_LOAD,
    WAIT_LOGIN_COMPLETE,
    WAIT_OKTA_PROCESS,
    WAIT_FORM_APPEAR,
    WAIT_MODAL_APPEAR,
    TIMEOUT_SHORT,
    TIMEOUT_MEDIUM,
    TIMEOUT_LONG,
    TIMEOUT_LOGIN,
    TIMEOUT_WIDGET,
    TIMEOUT_PAGE,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'encova_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EncovaLogin:
    """Handles Encova portal login automation"""
    
    def __init__(self, username: str = None, password: str = None, task_id: str = None):
        if not username:
            username = ENCOVA_USERNAME
        if not password:
            password = ENCOVA_PASSWORD
        
        self.username = username
        self.password = password
        self.context: BrowserContext = None
        self.page: Page = None
        self.playwright = None
        self.task_id = task_id or "default"
        self.cookies_file = SESSION_DIR / "encova_cookies.json"
        
    async def init_browser(self) -> None:
        """Initialize browser with persistent context for cookie storage"""
        self.playwright = await async_playwright().start()
        
        # Use task-specific user data directory to avoid conflicts in concurrent execution
        # Each task gets its own isolated browser session
        user_data_dir = SESSION_DIR / f"browser_data_{self.task_id}"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Use persistent context to save cookies with better fingerprinting evasion
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=BROWSER_HEADLESS,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Add extra args to avoid detection (Okta-specific)
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--start-maximized',
            ],
            # Add extra HTTP headers
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(BROWSER_TIMEOUT)
        
        # Comprehensive anti-detection script to prevent Okta from blocking
        await self.page.add_init_script("""
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override Chrome runtime
            window.chrome = {
                runtime: {}
            };
            
            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Remove automation indicators
            delete navigator.__proto__.webdriver;
        """)
        
        logger.info("Browser initialized")
        
    async def load_cookies(self) -> bool:
        """Load saved cookies if they exist and are not expired"""
        if self.cookies_file.exists():
            try:
                import time
                from datetime import datetime, timedelta
                
                # Check if cookie file is older than 1 day (F5 sessions typically expire after 1-2 days)
                file_age = time.time() - self.cookies_file.stat().st_mtime
                days_old = file_age / (24 * 60 * 60)
                
                if days_old > 1.5:  # If cookies are older than 1.5 days, they're likely expired
                    logger.info(f"Cookie file is {days_old:.1f} days old - likely expired, will not load")
                    logger.info("Cookies will be cleared to avoid F5 policy block")
                    # Delete stale cookie file
                    self.cookies_file.unlink()
                    return False
                
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    
                    # Check if cookies have expiration dates and if they're expired
                    current_time = time.time()
                    valid_cookies = []
                    for cookie in cookies:
                        # Check if cookie has expiration
                        if 'expires' in cookie:
                            expires = cookie.get('expires', 0)
                            # Playwright stores expires as -1 for session cookies, or as timestamp
                            if expires > 0 and expires < current_time:
                                logger.debug(f"Cookie {cookie.get('name', 'unknown')} has expired")
                                continue
                        valid_cookies.append(cookie)
                    
                    if len(valid_cookies) < len(cookies):
                        logger.info(f"Filtered out {len(cookies) - len(valid_cookies)} expired cookies")
                    
                    if valid_cookies:
                        await self.context.add_cookies(valid_cookies)
                        logger.info(f"Loaded {len(valid_cookies)} cookies from storage (file age: {days_old:.1f} days)")
                        return True
                    else:
                        logger.info("All cookies were expired - will perform fresh login")
                        self.cookies_file.unlink()
                        return False
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")
        return False
    
    async def save_cookies(self) -> None:
        """Save current cookies for future auto-login"""
        try:
            cookies = await self.context.cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"Saved {len(cookies)} cookies")
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
    
    async def _check_f5_policy_block(self) -> bool:
        """Check if F5 Networks access policy is blocking the session"""
        try:
            page_content = await self.page.content()
            current_url = self.page.url
            
            # Check for F5 Networks policy evaluation message
            f5_indicators = [
                "policy evaluation is already in progress",
                "F5 Networks",
                "create a new session",
                "policy evaluation"
            ]
            
            for indicator in f5_indicators:
                if indicator.lower() in page_content.lower():
                    logger.warning(f"F5 Networks access policy detected: {indicator}")
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"Error checking F5 policy: {e}")
            return False
    
    async def _handle_f5_policy_block(self) -> bool:
        """Automatically handle F5 Networks policy block by creating a new session"""
        try:
            logger.info("Attempting to resolve F5 Networks policy block...")
            
            # Look for the "create a new session" link
            # The link text is usually "click here" or "create a new session"
            link_selectors = [
                'a:has-text("here")',  # "click here"
                'a:has-text("create a new session")',
                'a:has-text("new session")',
                'a[href*="new"]',
                'a[href*="session"]',
                # Try to find any link on the F5 error page
                'a',
            ]
            
            link_clicked = False
            for selector in link_selectors:
                try:
                    link = await self.page.query_selector(selector)
                    if link:
                        link_text = await link.inner_text()
                        # Check if it's the right link
                        if any(keyword in link_text.lower() for keyword in ['here', 'new session', 'create']):
                            logger.info(f"Found F5 'create new session' link: {link_text}")
                            await link.click()
                            link_clicked = True
                            break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not link_clicked:
                # Fallback: try JavaScript to find and click the link
                try:
                    logger.info("Trying JavaScript approach to find F5 link...")
                    clicked = await self.page.evaluate("""
                        () => {
                            const links = Array.from(document.querySelectorAll('a'));
                            for (let link of links) {
                                const text = link.textContent.toLowerCase();
                                if (text.includes('here') || text.includes('new session') || text.includes('create')) {
                                    link.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                    if clicked:
                        logger.info("Successfully clicked F5 link via JavaScript")
                        link_clicked = True
                except Exception as e:
                    logger.debug(f"JavaScript approach failed: {e}")
            
            if link_clicked:
                # Wait for navigation to login page
                logger.info("Waiting for new session page to load...")
                await asyncio.sleep(WAIT_PAGE_LOAD)
                
                # Clear old cookies since they're stale (F5 detected them as invalid)
                try:
                    logger.info("Clearing stale cookies due to F5 policy block...")
                    await self.context.clear_cookies()
                    if self.cookies_file.exists():
                        self.cookies_file.unlink()
                        logger.info("Deleted stale cookie file")
                except Exception as e:
                    logger.warning(f"Could not clear cookies: {e}")
                
                # Check if we're now on a login page
                current_url = self.page.url
                logger.info(f"After clicking F5 link, current URL: {current_url}")
                
                # Wait a bit more for page to fully load
                await asyncio.sleep(WAIT_PAGE_LOAD)
                
                return True
            else:
                logger.error("Could not find 'create new session' link on F5 error page")
                return False
                
        except Exception as e:
            logger.error(f"Error handling F5 policy block: {e}", exc_info=True)
            return False
    
    async def check_auto_login(self) -> bool:
        """Check if already logged in (auto-login scenario)"""
        try:
            logger.info("Checking for auto-login...")
            # Use 'load' instead of 'networkidle' for better reliability in containerized environments
            await self.page.goto(ENCOVA_LOGIN_URL, wait_until="load", timeout=TIMEOUT_PAGE)
            
            await asyncio.sleep(WAIT_PAGE_LOAD)
            
            # Check for F5 Networks policy block and handle it automatically
            if await self._check_f5_policy_block():
                logger.warning("F5 Networks access policy block detected - attempting to resolve automatically...")
                if await self._handle_f5_policy_block():
                    logger.info("F5 policy block resolved - navigating to login page for fresh login")
                    # Navigate to login page again after resolving F5 block
                    await self.page.goto(ENCOVA_LOGIN_URL, wait_until="load", timeout=TIMEOUT_PAGE)
                    await asyncio.sleep(WAIT_PAGE_LOAD)
                    # After handling F5 block, we need to login again (cookies were cleared)
                    # Return False to trigger perform_login()
                else:
                    logger.error("Could not automatically resolve F5 policy block")
                    return False
            
            current_url = self.page.url
            logger.info(f"Current URL after navigation: {current_url}")
            
            # If we're redirected away from login page, we're likely logged in
            if "login" not in current_url.lower() and "auth.encova.com" not in current_url:
                logger.info("Auto-login successful - already authenticated")
                await self.navigate_to_new_quote_search()
                return True
            
            # Check for login form presence
            login_form = await self.page.query_selector('#okta-login-container')
            if not login_form:
                logger.info("No login form found - likely already logged in")
                await self.navigate_to_new_quote_search()
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking auto-login: {e}")
            return False
    
    async def _enter_username(self) -> bool:
        """Enter username in Okta login form"""
        try:
            logger.info("Step 1: Entering username...")
            # Try the most likely selector first (based on successful logs)
            username_selectors = [
                '#okta-login-container input[type="text"]',  # Most likely - try first
                'input[name="username"]',
                'input[type="text"][id*="username"]',
                'input[type="text"][placeholder*="Username"]',
                'input[type="text"][placeholder*="Email"]',
                'input[type="text"].okta-form-input-field',
                'input.okta-form-input-field[type="text"]',
                'form input[type="text"]'
            ]
            
            username_field = None
            # Use shorter timeout per selector (3 seconds) to fail fast
            selector_timeout = 3000  # 3 seconds per selector
            
            for selector in username_selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    username_field = await self.page.wait_for_selector(
                        selector, timeout=selector_timeout, state='visible'
                    )
                    if username_field:
                        is_visible = await username_field.is_visible()
                        is_enabled = await username_field.is_enabled()
                        if is_visible and is_enabled:
                            logger.info(f"Found username field with selector: {selector}")
                            break
                        else:
                            username_field = None
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not username_field:
                screenshot_path = LOG_DIR / "username_field_not_found.png"
                await self.page.screenshot(path=str(screenshot_path), full_page=True)
                logger.error(f"Could not find username field. Screenshot saved to {screenshot_path}")
                return False
            
            await username_field.click()
            await asyncio.sleep(WAIT_MEDIUM)
            await username_field.fill(self.username, force=True)
            logger.info(f"Username entered: {self.username}")
            await asyncio.sleep(WAIT_LONG)
            
            # Submit username
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                '.button-primary',
                'button.o-form-button',
                'button[data-type="save"]',
                '#okta-login-container button[type="submit"]'
            ]
            
            submitted = False
            for selector in submit_selectors:
                try:
                    submit_btn = await self.page.query_selector(selector)
                    if submit_btn and await submit_btn.is_visible():
                        logger.info(f"Clicking submit button: {selector}")
                        await submit_btn.click()
                        submitted = True
                        break
                except Exception as e:
                    logger.debug(f"Submit button selector {selector} failed: {e}")
                    continue
            
            if not submitted:
                logger.info("Pressing Enter on username field...")
                await username_field.press("Enter")
            
            return True
        except Exception as e:
            logger.error(f"Error entering username: {e}", exc_info=True)
            return False
    
    async def _enter_password(self) -> bool:
        """Enter password in Okta login form"""
        try:
            logger.info("Step 2: Entering password...")
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[type="password"][id*="password"]',
                '#okta-login-container input[type="password"]',
                'input.okta-form-input-field[type="password"]',
                'form input[type="password"]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    logger.debug(f"Trying password selector: {selector}")
                    password_field = await self.page.wait_for_selector(
                        selector, timeout=TIMEOUT_LOGIN, state='visible'
                    )
                    if password_field:
                        is_visible = await password_field.is_visible()
                        is_enabled = await password_field.is_enabled()
                        if is_visible and is_enabled:
                            logger.info(f"Found password field with selector: {selector}")
                            break
                        else:
                            password_field = None
                except Exception as e:
                    logger.debug(f"Password selector {selector} failed: {e}")
                    continue
            
            if not password_field:
                screenshot_path = LOG_DIR / "password_field_not_found.png"
                await self.page.screenshot(path=str(screenshot_path), full_page=True)
                logger.error(f"Could not find password field. Screenshot saved to {screenshot_path}")
                return False
            
            await password_field.click()
            await asyncio.sleep(WAIT_MEDIUM)
            await password_field.fill(self.password, force=True)
            logger.info("Password entered")
            await asyncio.sleep(WAIT_LONG)
            
            # Submit password
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                '.button-primary',
                'button.o-form-button',
                'button[data-type="save"]',
                '#okta-login-container button[type="submit"]'
            ]
            
            submitted = False
            for selector in submit_selectors:
                try:
                    submit_btn = await self.page.query_selector(selector)
                    if submit_btn and await submit_btn.is_visible():
                        logger.info(f"Clicking submit button for password: {selector}")
                        await submit_btn.click()
                        submitted = True
                        break
                except Exception as e:
                    logger.debug(f"Submit button selector {selector} failed: {e}")
                    continue
            
            if not submitted:
                logger.info("Pressing Enter on password field...")
                await password_field.press("Enter")
            
            return True
        except Exception as e:
            logger.error(f"Error entering password: {e}", exc_info=True)
            return False
    
    async def perform_login(self) -> bool:
        """Perform first-time login with username and password (two-step Okta flow)"""
        try:
            logger.info("Performing first-time login...")
            
            if not self.username or not self.password:
                raise ValueError("Username and password are required for login")
            
            logger.info(f"Navigating to {ENCOVA_LOGIN_URL}...")
            # Use 'load' instead of 'networkidle' for better reliability in containerized environments
            # networkidle can timeout if there are background requests that never complete
            await self.page.goto(ENCOVA_LOGIN_URL, wait_until="load", timeout=TIMEOUT_PAGE)
            await asyncio.sleep(WAIT_OKTA_PROCESS)
            
            # Check for F5 Networks policy block and handle it automatically
            if await self._check_f5_policy_block():
                logger.warning("F5 Networks access policy block detected - attempting to resolve automatically...")
                if await self._handle_f5_policy_block():
                    logger.info("F5 policy block resolved - continuing with login")
                    # Wait a bit for the new session page to be ready
                    await asyncio.sleep(WAIT_PAGE_LOAD)
                else:
                    logger.error("Could not automatically resolve F5 policy block")
                    return False
            
            logger.info("Waiting for Okta login widget to load...")
            
            # Wait for page to be interactive first
            # Use domcontentloaded instead of networkidle for better reliability
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PAGE)
                # Try networkidle with shorter timeout, but don't fail if it times out
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    logger.debug("Networkidle timeout - continuing anyway (common in containerized environments)")
            except Exception as e:
                logger.warning(f"Load state wait: {e} - continuing anyway")
            
            # Try multiple strategies to find Okta widget
            widget_found = False
            okta_selectors = [
                '#okta-login-container',
                '#okta-signin-container',
                '[data-se="okta-signin-container"]',
                'iframe[id*="okta"]',
                'iframe[src*="okta"]',
                'form[data-se="okta-signin"]',
            ]
            
            # First, check for iframes (Okta often loads in iframe)
            try:
                frames = self.page.frames
                for frame in frames:
                    if 'okta' in frame.url.lower():
                        logger.info(f"Found Okta iframe: {frame.url}")
                        # Try to find widget in iframe
                        try:
                            await frame.wait_for_selector('input[type="text"]', timeout=5000, state='visible')
                            logger.info("Found Okta widget in iframe")
                            widget_found = True
                            break
                        except:
                            pass
            except Exception as e:
                logger.debug(f"Frame check: {e}")
            
            # If not in iframe, try main page selectors
            if not widget_found:
                for selector in okta_selectors:
                    try:
                        logger.debug(f"Trying selector: {selector}")
                        await self.page.wait_for_selector(selector, timeout=5000, state='visible')
                        logger.info(f"Found Okta widget with selector: {selector}")
                        widget_found = True
                        break
                    except Exception as e:
                        logger.debug(f"Selector {selector} not found: {e}")
                        continue
            
            if not widget_found:
                # Last resort: wait for any input field that might be the username field
                try:
                    logger.info("Trying fallback: waiting for any text input...")
                    await self.page.wait_for_selector('input[type="text"]', timeout=TIMEOUT_WIDGET, state='visible')
                    logger.info("Found text input field (likely Okta username field)")
                    widget_found = True
                except Exception as e:
                    logger.error(f"Could not find Okta login widget. Error: {e}")
                    # Take screenshot for debugging
                    await self.page.screenshot(path=str(LOG_DIR / 'okta_widget_not_found.png'), full_page=True)
                    logger.info(f"Screenshot saved to {LOG_DIR / 'okta_widget_not_found.png'}")
                    raise TimeoutError("Okta login widget did not appear. Okta may be blocking automation.")
            
            await asyncio.sleep(WAIT_WIDGET_LOAD)
            
            # Enter username
            if not await self._enter_username():
                return False
            
            # Wait for password page
            logger.info("Waiting for password page...")
            await asyncio.sleep(WAIT_OKTA_PROCESS)
            
            # Enter password
            if not await self._enter_password():
                return False
            
            # Wait for login to complete
            logger.info("Waiting for login to complete...")
            await asyncio.sleep(WAIT_LOGIN_COMPLETE)
            
            # Wait for navigation away from login page
            try:
                await self.page.wait_for_url(
                    lambda url: "login" not in url.lower() and "auth.encova.com/login" not in url.lower(),
                    timeout=TIMEOUT_LOGIN
                )
            except Exception as e:
                logger.debug(f"URL wait timeout: {e}")
            
            # Check if login was successful
            current_url = self.page.url
            logger.info(f"Final URL after login: {current_url}")
            
            if "login" not in current_url.lower() or "agent.encova.com" in current_url:
                logger.info("Login successful!")
                await self.save_cookies()
                await self.navigate_to_new_quote_search()
                return True
            else:
                logger.warning("Login may have failed - still on login/auth page")
                screenshot_path = LOG_DIR / "login_failed.png"
                await self.page.screenshot(path=str(screenshot_path))
                logger.info(f"Screenshot saved to {screenshot_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error during login: {e}", exc_info=True)
            screenshot_path = LOG_DIR / "login_error.png"
            await self.page.screenshot(path=str(screenshot_path))
            logger.info(f"Screenshot saved to {screenshot_path}")
            return False
    
    async def login(self) -> bool:
        """Main login method - handles both auto-login and first-time login"""
        try:
            await self.init_browser()
            await self.load_cookies()
            
            if await self.check_auto_login():
                return True
            
            return await self.perform_login()
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def navigate_to_new_quote_search(self) -> bool:
        """Navigate to new quote account search page and create new account"""
        try:
            logger.info("Navigating to new quote account search page...")
            
            # Navigate with longer timeout
            await self.page.goto(ENCOVA_NEW_QUOTE_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for loading spinner to disappear
            logger.info("Waiting for application to finish loading...")
            try:
                # Wait for loading text/spinner to disappear
                await self.page.wait_for_function(
                    """
                    () => {
                        const bodyText = document.body.innerText || document.body.textContent || '';
                        return !bodyText.includes('Loading application') && 
                               !bodyText.includes('Loading...') &&
                               document.readyState === 'complete';
                    }
                    """,
                    timeout=60000
                )
                logger.info("Application finished loading")
            except Exception as e:
                logger.warning(f"Loading wait timeout, but continuing: {e}")
            
            # Wait for network to be idle
            try:
                # Use domcontentloaded for better reliability, networkidle can timeout in containers
                await self.page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PAGE)
            except Exception as e:
                logger.debug(f"Network idle wait: {e}")
            
            # Additional wait for Angular/JavaScript to initialize
            await asyncio.sleep(WAIT_PAGE_LOAD * 2)
            
            # Wait for page to be interactive
            try:
                await self.page.wait_for_load_state("domcontentloaded")
            except Exception as e:
                logger.debug(f"DOM load wait: {e}")
            
            current_url = self.page.url
            logger.info(f"Navigated to: {current_url}")
            
            if "new-quote-account-search" not in current_url:
                logger.warning(f"Expected new-quote-account-search page but got: {current_url}")
            
            # Wait for page elements to be ready
            logger.info("Waiting for page elements to be ready...")
            try:
                # Wait for any interactive element to appear
                await self.page.wait_for_selector('body', timeout=10000, state='visible')
                # Wait a bit more for JavaScript to initialize
                await asyncio.sleep(WAIT_PAGE_LOAD)
            except Exception as e:
                logger.debug(f"Element wait: {e}")
            
            await self.click_create_new_account()
            await self.select_commercial_radio()
            await self.wait_for_form()
            
            logger.info("Successfully navigated to new quote account search and opened form")
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to new quote account search: {e}", exc_info=True)
            screenshot_path = LOG_DIR / "navigation_error.png"
            await self.page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"Screenshot saved to {screenshot_path}")
            return False
    
    async def click_create_new_account(self) -> bool:
        """Click on 'Create a new one' button to open popup"""
        try:
            logger.info("Clicking 'Create a new one' button...")
            
            # Wait for page to be ready
            await asyncio.sleep(WAIT_PAGE_LOAD)
            
            # Try JavaScript function first (fastest and most reliable)
            try:
                logger.debug("Trying to execute displayNewAccountPopup() function directly...")
                result = await self.page.evaluate("""
                    () => {
                        if (typeof displayNewAccountPopup === 'function') {
                            displayNewAccountPopup();
                            return true;
                        }
                        return false;
                    }
                """)
                if result:
                    logger.info("Successfully executed displayNewAccountPopup() function")
                    await asyncio.sleep(WAIT_PAGE_LOAD)
                    return True
            except Exception as e:
                logger.debug(f"JavaScript function call failed: {e}")
            
            # Fallback to selectors
            selectors = [
                'a[ng-click*="displayNewAccountPopup"]',
                'a[ng-click="displayNewAccountPopup()"]',
                'a:has-text("Create a new one")',
                'a:has-text("Create a new one.")',
                'a.blue-link.nbs-button.tertiary-button-default',
                'a.nbs-button.tertiary-button-default',
                'xpath=//a[contains(text(), "Create a new one")]',
                'xpath=//a[contains(., "Create a new one")]',
                'xpath=//a[contains(@ng-click, "displayNewAccountPopup")]'
            ]
            
            clicked = False
            selector_timeout = 5000  # 5 seconds per selector
            
            for selector in selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    element = await self.page.wait_for_selector(
                        selector, timeout=selector_timeout, state='visible'
                    )
                    if element and await element.is_visible():
                        logger.info(f"Found 'Create a new one' button with selector: {selector}")
                        await element.click()
                        clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if clicked:
                logger.info("Successfully clicked 'Create a new one' button")
                await asyncio.sleep(WAIT_PAGE_LOAD)
                return True
            else:
                logger.error("Could not find 'Create a new one' button")
                # Take screenshot for debugging
                screenshot_path = LOG_DIR / "create_new_account_not_found.png"
                await self.page.screenshot(path=str(screenshot_path), full_page=True)
                logger.info(f"Screenshot saved to {screenshot_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error clicking 'Create a new one' button: {e}", exc_info=True)
            return False
    
    async def select_commercial_radio(self) -> bool:
        """Select 'Commercial' radio button in the popup"""
        try:
            logger.info("Selecting 'Commercial' radio button...")
            
            await asyncio.sleep(WAIT_PAGE_LOAD)
            
            selectors = [
                'md-radio-button[value="Commercial"]',
                'md-radio-button#radio_42',
                'md-radio-button[aria-label="Commercial"]',
                'md-radio-button:has-text("Commercial")',
                'xpath=//md-radio-button[@value="Commercial"]',
                'xpath=//md-radio-button[@aria-label="Commercial"]',
                'xpath=//md-radio-button[contains(., "Commercial")]',
                'input[type="radio"][value="Commercial"]',
                'input[type="radio"][id="radio_42"]',
                'input[name="accountType"][value="Commercial"]',
                'input[type="radio"][name="accountType"][value="Commercial"]'
            ]
            
            selected = False
            for selector in selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    element = await self.page.wait_for_selector(
                        selector, timeout=TIMEOUT_LONG, state='visible'
                    )
                    if element and await element.is_visible():
                        is_checked = await element.get_attribute('aria-checked')
                        if is_checked == 'true':
                            logger.info("Commercial radio button is already selected")
                            selected = True
                            break
                        
                        logger.info(f"Found Commercial radio button with selector: {selector}")
                        await element.click()
                        selected = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not selected:
                logger.info("Trying to select Commercial radio button via JavaScript...")
                try:
                    await self.page.evaluate('''
                        () => {
                            const radio = document.querySelector('md-radio-button[value="Commercial"]');
                            if (radio) {
                                radio.click();
                                return true;
                            }
                            const input = document.querySelector('input[type="radio"][value="Commercial"]');
                            if (input) {
                                input.click();
                                return true;
                            }
                            return false;
                        }
                    ''')
                    selected = True
                except Exception as e:
                    logger.warning(f"Could not select via JavaScript: {e}")
            
            if selected:
                logger.info("Successfully selected 'Commercial' radio button")
                await asyncio.sleep(WAIT_LONG)
                return True
            else:
                logger.error("Could not find or select 'Commercial' radio button")
                return False
                
        except Exception as e:
            logger.error(f"Error selecting Commercial radio button: {e}", exc_info=True)
            return False
    
    async def wait_for_form(self) -> bool:
        """Wait for the form to be fully loaded and ready"""
        try:
            logger.info("Waiting for form to open...")
            
            # Wait for loading to complete
            try:
                await self.page.wait_for_function(
                    """
                    () => {
                        const bodyText = document.body.innerText || document.body.textContent || '';
                        return !bodyText.includes('Loading application') && 
                               !bodyText.includes('Loading...') &&
                               document.readyState === 'complete';
                    }
                    """,
                    timeout=30000
                )
            except Exception as e:
                logger.debug(f"Loading wait in form: {e}")
            
            # Wait for form elements to appear
            form_selectors = [
                'input[type="text"]',
                'input[name="contactFirstName"]',
                'form',
                'md-input-container',
            ]
            
            form_found = False
            for selector in form_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=10000, state='visible')
                    logger.info(f"Form element found with selector: {selector}")
                    form_found = True
                    break
                except Exception as e:
                    logger.debug(f"Form selector {selector} not found: {e}")
                    continue
            
            if not form_found:
                logger.warning("Form elements not found, but continuing...")
            
            # Additional wait for Angular to initialize form
            await asyncio.sleep(WAIT_FORM_APPEAR * 2)
            
            logger.info("Form is now open and ready")
            return True
            
        except Exception as e:
            logger.warning(f"Error waiting for form: {e}")
            return False
    
    
    async def _fill_field(self, field_selector: str, value: str, field_label: str = None) -> bool:
        """
        Fill a single form field
        
        Args:
            field_selector: CSS selector, XPath, name, id, or label text
            value: Value to fill in the field
            field_label: Optional label text to validate we're filling the right field
        
        Returns:
            bool: True if field was filled successfully
        """
        if not value:
            logger.warning(f"Empty value provided for field: {field_selector}")
            return False
        
        try:
            # Try direct selector first with longer timeout for ID-based selectors
            timeout = TIMEOUT_LONG if 'id=' in field_selector or field_selector.startswith('#') else TIMEOUT_MEDIUM
            
            try:
                element = await self.page.wait_for_selector(
                    field_selector, timeout=timeout, state='visible'
                )
                if element:
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()
                    
                    if is_visible and is_enabled:
                        # Validate field label if provided
                        if field_label:
                            try:
                                # Check if the label matches by looking at nearby text
                                label_match = await element.evaluate(f'''
                                    (el, expectedLabel) => {{
                                        // Look for label in parent or nearby elements
                                        let parent = el.parentElement;
                                        let depth = 0;
                                        while (parent && depth < 5) {{
                                            const text = parent.textContent || '';
                                            if (text.toUpperCase().includes(expectedLabel.toUpperCase())) {{
                                                return true;
                                            }}
                                            parent = parent.parentElement;
                                            depth++;
                                        }}
                                        return false;
                                    }}
                                ''', field_label)
                                
                                if not label_match:
                                    logger.warning(f"Field label validation failed for: {field_label}")
                                    # Don't return False, continue to try other methods
                            except Exception as e:
                                logger.debug(f"Label validation failed: {e}")
                        
                        await element.clear()
                        await asyncio.sleep(WAIT_SHORT)
                        await element.fill(str(value), force=True)
                        await asyncio.sleep(WAIT_SHORT)
                        
                        current_value = await element.input_value()
                        if current_value == str(value):
                            logger.info(f"Successfully filled field with selector: {field_selector}")
                            return True
                        else:
                            logger.warning(f"Value mismatch. Expected: {value}, Got: {current_value}")
            except Exception as e:
                logger.debug(f"Direct selector '{field_selector}' failed: {e}")
            
            # Try JavaScript approach with better ID handling and field validation
            logger.debug(f"Trying JavaScript approach for field: {field_selector}")
            try:
                escaped_value = str(value).replace("'", "\\'").replace("\\", "\\\\")
                escaped_label = field_label.replace("'", "\\'") if field_label else ""
                
                # Extract ID if it's an ID-based selector
                extracted_id = None
                if 'id=' in field_selector:
                    import re
                    id_match = re.search(r'id=["\']([^"\']+)["\']', field_selector)
                    if id_match:
                        extracted_id = id_match.group(1)
                
                # Build JavaScript code with proper string formatting
                extracted_id_js = f'let extractedId = "{extracted_id}";' if extracted_id else 'let extractedId = null;'
                extracted_id_check = '''
                        if (!element && extractedId) {
                            try {
                                const idEl = document.getElementById(extractedId);
                                if (idEl && validateFieldLabel(idEl, expectedLabel)) {
                                    element = idEl;
                                }
                            } catch(e) {
                                console.log('Extracted ID selector failed:', e);
                            }
                        }
                        ''' if extracted_id else ''
                
                js_code = f'''
                    (expectedLabel) => {{
                        let element = null;
                        let selector = '{field_selector}';
                        {extracted_id_js}
                        
                        function validateFieldLabel(el, label) {{
                            if (!label) return true;
                            
                            let parent = el.parentElement;
                            let depth = 0;
                            while (parent && depth < 5) {{
                                const text = (parent.textContent || '').toUpperCase();
                                if (text.includes(label.toUpperCase())) {{
                                    return true;
                                }}
                                parent = parent.parentElement;
                                depth++;
                            }}
                            return false;
                        }}
                        
                        function findCorrectField(selector, label) {{
                            const allElements = document.querySelectorAll(selector);
                            
                            if (allElements.length === 0) return null;
                            
                            if (allElements.length === 1) {{
                                return label ? (validateFieldLabel(allElements[0], label) ? allElements[0] : null) : allElements[0];
                            }}
                            
                            if (label) {{
                                for (let el of allElements) {{
                                    if (validateFieldLabel(el, label)) {{
                                        return el;
                                    }}
                                }}
                            }}
                            
                            for (let el of allElements) {{
                                const style = window.getComputedStyle(el);
                                if (style.display !== 'none' && 
                                    style.visibility !== 'hidden' && 
                                    !el.disabled &&
                                    el.offsetParent !== null) {{
                                    return el;
                                }}
                            }}
                            
                            return null;
                        }}
                        
                        try {{
                            element = findCorrectField(selector, expectedLabel);
                        }} catch(e) {{
                            console.log('Direct selector failed:', e);
                        }}
                        
                        {extracted_id_check}
                        
                        if (!element && selector.startsWith('#')) {{
                            try {{
                                const idEl = document.getElementById(selector.substring(1));
                                if (idEl && validateFieldLabel(idEl, expectedLabel)) {{
                                    element = idEl;
                                }}
                            }} catch(e) {{
                                console.log('ID selector failed:', e);
                            }}
                        }}
                        
                        if (!element && selector.includes('name=')) {{
                            try {{
                                const nameMatch = selector.match(/name=["']([^"']+)["']/);
                                if (nameMatch) {{
                                    element = findCorrectField(`input[name="${{nameMatch[1]}}"]`, expectedLabel);
                                }}
                            }} catch(e) {{
                                console.log('Name selector failed:', e);
                            }}
                        }}
                        
                        if (!element && selector.includes('ng-model=')) {{
                            try {{
                                const ngModelMatch = selector.match(/ng-model=["']([^"']+)["']/);
                                if (ngModelMatch) {{
                                    let specificSelector = `input[ng-model="${{ngModelMatch[1]}}"]`;
                                    
                                    if (selector.includes('type=')) {{
                                        const typeMatch = selector.match(/type=["']([^"']+)["']/);
                                        if (typeMatch) {{
                                            specificSelector += `[type="${{typeMatch[1]}}"]`;
                                        }}
                                    }}
                                    
                                    if (selector.includes('placeholder')) {{
                                        const placeholderMatch = selector.match(/placeholder\\*=["']([^"']+)["']/);
                                        if (placeholderMatch) {{
                                            const allInputs = document.querySelectorAll(specificSelector);
                                            for (let inp of allInputs) {{
                                                const placeholder = (inp.getAttribute('placeholder') || '').toUpperCase();
                                                if (placeholder.includes(placeholderMatch[1].toUpperCase())) {{
                                                    if (validateFieldLabel(inp, expectedLabel)) {{
                                                        element = inp;
                                                        break;
                                                    }}
                                                }}
                                            }}
                                        }}
                                    }} else {{
                                        element = findCorrectField(specificSelector, expectedLabel);
                                    }}
                                }}
                            }} catch(e) {{
                                console.log('ng-model selector failed:', e);
                            }}
                        }}
                        
                        if (element) {{
                            element.value = '{escaped_value}';
                            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            element.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            
                            if (element.ngModelController) {{
                                element.ngModelController.$setViewValue('{escaped_value}');
                            }}
                            
                            return true;
                        }}
                        return false;
                    }}
                '''
                
                result = await self.page.evaluate(js_code, escaped_label)
                
                if result:
                    logger.info(f"Successfully filled field using JavaScript: {field_selector}")
                    await asyncio.sleep(WAIT_SHORT)
                    return True
            except Exception as e:
                logger.debug(f"JavaScript approach failed: {e}")
            
            logger.warning(f"Could not fill field: {field_selector}")
            return False
            
        except Exception as e:
            logger.error(f"Error in _fill_field for '{field_selector}': {e}")
            return False
    
    async def _click_dropdown_toggle(self, focusser) -> bool:
        """Helper method to click dropdown toggle button"""
        try:
            toggle_clicked = await focusser.evaluate('''
                (el) => {
                    const parent = el.parentElement;
                    if (parent) {
                        const toggle = parent.querySelector('.ui-select-toggle');
                        if (toggle) {
                            toggle.click();
                            return true;
                        }
                    }
                    
                    let searchParent = el.parentElement;
                    let depth = 0;
                    while (searchParent && depth < 5) {
                        const toggle = searchParent.querySelector('[ng-click*="$select.activate"]');
                        if (toggle) {
                            toggle.click();
                            return true;
                        }
                        searchParent = searchParent.parentElement;
                        depth++;
                    }
                    
                    searchParent = el.parentElement;
                    depth = 0;
                    while (searchParent && depth < 5) {
                        const toggle = searchParent.querySelector('span.btn.btn-default.form-control.ui-select-toggle');
                        if (toggle) {
                            toggle.click();
                            return true;
                        }
                        searchParent = searchParent.parentElement;
                        depth++;
                    }
                    
                    return false;
                }
            ''')
            return toggle_clicked
        except Exception as e:
            logger.error(f"Error clicking toggle: {e}")
            return False
    
    async def _fill_searchable_dropdown(self, focusser_id: str, value: str) -> bool:
        """
        Generic helper to fill searchable dropdowns
        
        Args:
            focusser_id: ID of the focusser input (e.g., "focusser-0")
            value: Value to search and select
        
        Returns:
            bool: True if successful
        """
        if not value:
            logger.warning(f"Empty value provided for dropdown: {focusser_id}")
            return False
        
        try:
            # Close any open dropdowns
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Find focusser
            focusser = await self.page.wait_for_selector(
                f'input#{focusser_id}', timeout=TIMEOUT_LONG, state='visible'
            )
            logger.info(f"Found {focusser_id}")
            
            await focusser.scroll_into_view_if_needed()
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Click toggle
            if not await self._click_dropdown_toggle(focusser):
                logger.error(f"Could not find or click toggle button for {focusser_id}")
                return False
            
            logger.info("Toggle button clicked, waiting for search input...")
            await asyncio.sleep(WAIT_DROPDOWN_OPEN)
            
            # Find visible search input
            await asyncio.sleep(WAIT_MEDIUM)
            all_search_inputs = await self.page.query_selector_all('input[ng-model="$select.search"]')
            logger.debug(f"Found {len(all_search_inputs)} search inputs total")
            
            search_input = None
            for inp in all_search_inputs:
                try:
                    is_visible = await inp.is_visible()
                    if is_visible:
                        is_really_visible = await inp.evaluate('''
                            (el) => {
                                const style = window.getComputedStyle(el);
                                return style.display !== 'none' && 
                                       style.visibility !== 'hidden' && 
                                       el.offsetParent !== null;
                            }
                        ''')
                        if is_really_visible:
                            search_input = inp
                            input_id = await inp.get_attribute('id')
                            logger.info(f"Found visible search input: {input_id}")
                            break
                except Exception as e:
                    logger.debug(f"Error checking input: {e}")
                    continue
            
            if not search_input:
                logger.error(f"No visible search input found for {focusser_id}")
                return False
            
            # Type and select
            logger.info(f"Typing '{value}' into search input...")
            await search_input.click()
            await asyncio.sleep(WAIT_SHORT)
            await search_input.fill(value)
            await asyncio.sleep(WAIT_MEDIUM)
            await search_input.press('Enter')
            await asyncio.sleep(WAIT_MEDIUM)
            
            logger.info(f"Successfully filled dropdown {focusser_id} with: {value}")
            return True
            
        except Exception as e:
            logger.error(f"Error filling searchable dropdown {focusser_id}: {e}", exc_info=True)
            return False
    
    async def fill_state_dropdown(self, state_value: str) -> bool:
        """Fill the State dropdown"""
        logger.info(f"Filling State dropdown with: {state_value}")
        return await self._fill_searchable_dropdown("focusser-2", state_value)
    
    async def fill_address_type_dropdown(self, address_type: str) -> bool:
        """Fill the Address Type dropdown"""
        logger.info(f"Filling Address Type dropdown with: {address_type}")
        return await self._fill_searchable_dropdown("focusser-3", address_type)
    
    async def fill_preferred_contact_dropdown(self, contact_method: str) -> bool:
        """Fill the Preferred Contact Method dropdown"""
        logger.info(f"Filling Preferred Contact Method dropdown with: {contact_method}")
        return await self._fill_searchable_dropdown("focusser-0", contact_method)
    
    async def select_dropdown(self, focusser_id: str, value: str) -> bool:
        """
        Generic method to select a dropdown by focusser ID
        This is the method called by the webhook server
        
        Args:
            focusser_id: ID of the focusser input (e.g., "focusser-2", "focusser-3")
            value: Value to search and select in the dropdown
        
        Returns:
            bool: True if successful
        """
        logger.info(f"Selecting dropdown {focusser_id} with value: {value}")
        return await self._fill_searchable_dropdown(focusser_id, value)
    
    async def fill_producer_dropdown(self, producer_code: str) -> bool:
        """
        Fill the Producer dropdown (pure selection, not searchable)
        
        Args:
            producer_code: Producer code to select (partial match)
        
        Returns:
            bool: True if successful
        """
        if not producer_code:
            logger.warning("Empty producer_code provided")
            return False
        
        try:
            # Close any open dropdowns
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Find focusser
            focusser = await self.page.wait_for_selector(
                'input#focusser-1', timeout=TIMEOUT_LONG, state='visible'
            )
            logger.info("Found focusser-1 (Producer)")
            
            await focusser.scroll_into_view_if_needed()
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Click toggle
            if not await self._click_dropdown_toggle(focusser):
                logger.error("Could not find or click toggle button for Producer")
                return False
            
            logger.info("Toggle button clicked, waiting for options list...")
            await asyncio.sleep(WAIT_DROPDOWN_OPEN)
            
            # Wait for options
            await self.page.wait_for_selector(
                'div.ui-select-choices-row', timeout=TIMEOUT_MEDIUM, state='visible'
            )
            logger.info("Dropdown options list appeared")
            
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Get all option rows
            option_rows = await self.page.query_selector_all('div.ui-select-choices-row')
            logger.info(f"Found {len(option_rows)} producer options")
            
            # Find matching option
            selected = False
            for idx, row in enumerate(option_rows):
                try:
                    text_content = await row.text_content()
                    logger.debug(f"Option {idx}: {text_content}")
                    
                    if producer_code.lower() in text_content.lower():
                        logger.info(f"Found matching producer option: {text_content}")
                        await row.click()
                        await asyncio.sleep(WAIT_MEDIUM)
                        selected = True
                        logger.info(f"Successfully selected Producer: {text_content}")
                        break
                except Exception as e:
                    logger.error(f"Error checking option {idx}: {e}")
                    continue
            
            if not selected:
                logger.error(f"Could not find producer matching '{producer_code}'")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error filling Producer dropdown: {e}", exc_info=True)
            return False
    
    async def click_use_recommended_address(self) -> bool:
        """
        Click 'Use Recommended' button when Address Validation modal appears
        This auto-fills City, County, and State fields
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Waiting for Address Validation modal...")
            
            await asyncio.sleep(WAIT_MODAL_APPEAR)
            
            selectors = [
                'button[ng-click*="recommendedAddresses"]',
                'button:has-text("Use Recommended")',
                'button:has-text("USE RECOMMENDED")',
                'button.primary-btn:has-text("Recommended")',
                'button[type="button"][ng-click*="select"]',
            ]
            
            clicked = False
            for selector in selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    button = await self.page.wait_for_selector(
                        selector, timeout=TIMEOUT_LONG, state='visible'
                    )
                    
                    if button:
                        text = await button.text_content()
                        if text and 'recommend' in text.lower():
                            await button.click()
                            await asyncio.sleep(WAIT_LONG)
                            clicked = True
                            logger.info(f"Successfully clicked 'Use Recommended' button with selector: {selector}")
                            break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not clicked:
                logger.info("Trying JavaScript approach for Use Recommended button...")
                try:
                    clicked_js = await self.page.evaluate('''
                        () => {
                            const buttons = document.querySelectorAll('button');
                            for (let btn of buttons) {
                                const text = btn.textContent || btn.innerText;
                                if (text && text.toLowerCase().includes('recommend')) {
                                    btn.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''')
                    
                    if clicked_js:
                        clicked = True
                        await asyncio.sleep(WAIT_LONG)
                        logger.info("Successfully clicked 'Use Recommended' via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if clicked:
                logger.info("Successfully clicked 'Use Recommended' - City, County, State auto-filled")
                return True
            else:
                logger.warning("Could not find or click 'Use Recommended' button - modal may not have appeared")
                return False
                
        except Exception as e:
            logger.error(f"Error clicking Use Recommended button: {e}", exc_info=True)
            return False
    
    async def select_mig_radio_yes(self) -> bool:
        """
        Select 'No' for the MIG (Motorists Insurance Group) Customer question
        Based on Angular model: accountInfoView.isMIGCustomer.value should be 'false' for No
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Selecting 'No' for MIG Customer radio button...")
            
            # First, try to set the Angular model value directly (most reliable)
            try:
                logger.info("Trying to set Angular model value directly...")
                result = await self.page.evaluate('''
                    () => {
                        // Try to find and set the Angular model value
                        if (window.angular) {
                            var body = angular.element(document.body);
                            var rootScope = body.scope();
                            
                            // Try to find the scope with accountInfoView
                            function findAccountInfoScope(scope) {
                                if (!scope) return null;
                                
                                if (scope.accountInfoView && scope.accountInfoView.isMIGCustomer) {
                                    return scope;
                                }
                                
                                // Check child scopes
                                if (scope.$$childHead) {
                                    var found = findAccountInfoScope(scope.$$childHead);
                                    if (found) return found;
                                }
                                
                                // Check sibling scopes
                                if (scope.$$nextSibling) {
                                    var found = findAccountInfoScope(scope.$$nextSibling);
                                    if (found) return found;
                                }
                                
                                return null;
                            }
                            
                            var targetScope = findAccountInfoScope(rootScope);
                            if (targetScope && targetScope.accountInfoView) {
                                targetScope.accountInfoView.isMIGCustomer.value = 'false';
                                targetScope.$apply();
                                return true;
                            }
                        }
                        return false;
                    }
                ''')
                
                if result:
                    logger.info("Successfully set Angular model value to 'true'")
                    await asyncio.sleep(WAIT_MEDIUM)
                    
                    # Verify it was set correctly
                    verified = await self.page.evaluate('''
                        () => {
                            if (window.angular) {
                                var body = angular.element(document.body);
                                var rootScope = body.scope();
                                
                                function findAccountInfoScope(scope) {
                                    if (!scope) return null;
                                    if (scope.accountInfoView && scope.accountInfoView.isMIGCustomer) {
                                        return scope;
                                    }
                                    if (scope.$$childHead) {
                                        var found = findAccountInfoScope(scope.$$childHead);
                                        if (found) return found;
                                    }
                                    if (scope.$$nextSibling) {
                                        var found = findAccountInfoScope(scope.$$nextSibling);
                                        if (found) return found;
                                    }
                                    return null;
                                }
                                
                                var targetScope = findAccountInfoScope(rootScope);
                                return targetScope && targetScope.accountInfoView && 
                                       targetScope.accountInfoView.isMIGCustomer.value === 'false';
                            }
                            return false;
                        }
                    ''')
                    
                    if verified:
                        logger.info("Verified: MIG Customer is set to 'No' (false)")
                        return True
            except Exception as e:
                logger.debug(f"Angular model approach: {e}")
            
            # Fallback: Try clicking the radio button with value="false" (No)
            selectors = [
                'md-radio-button[value="false"]',  # Most likely - Angular uses true/false
                'md-radio-button[aria-label="No"]',
                'md-radio-button[id="No_"]',
                'md-radio-button:has-text("No")',
                'input[type="radio"][value="false"]',
                'input[type="radio"][value="No"]',
                'md-radio-button[value="No"]',
            ]
            
            selected = False
            for selector in selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    element = await self.page.wait_for_selector(
                        selector, timeout=TIMEOUT_MEDIUM, state='visible'
                    )
                    
                    if element:
                        # Check if it's already selected
                        aria_checked = await element.get_attribute('aria-checked')
                        if aria_checked == 'true':
                            logger.info("'No' radio button is already selected")
                            return True
                        
                        # Scroll into view and click
                        await element.scroll_into_view_if_needed()
                        await asyncio.sleep(WAIT_SHORT)
                        await element.click()
                        await asyncio.sleep(WAIT_MEDIUM)
                        
                        # Verify it was clicked
                        aria_checked_after = await element.get_attribute('aria-checked')
                        if aria_checked_after == 'true':
                            selected = True
                            logger.info(f"Successfully selected 'No' with selector: {selector}")
                            break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not selected:
                logger.info("Trying JavaScript click approach...")
                try:
                    clicked = await self.page.evaluate('''
                        () => {
                            // Find the No radio button (value="false" or aria-label="No")
                            const noButtons = document.querySelectorAll(
                                'md-radio-button[value="false"], ' +
                                'md-radio-button[aria-label="No"], ' +
                                'md-radio-button[id="No_"], ' +
                                'input[type="radio"][value="false"]'
                            );
                            
                            for (let btn of noButtons) {
                                const ariaLabel = btn.getAttribute('aria-label') || '';
                                const value = btn.getAttribute('value') || '';
                                
                                if (ariaLabel.includes('No') || value === 'false') {
                                    btn.click();
                                    
                                    // Trigger Angular if available
                                    if (window.angular) {
                                        var scope = angular.element(btn).scope();
                                        if (scope) {
                                            scope.$apply();
                                        }
                                    }
                                    
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''')
                    
                    if clicked:
                        selected = True
                        await asyncio.sleep(WAIT_MEDIUM)
                        logger.info("Successfully clicked 'No' via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript click approach failed: {e}")
            
            if selected:
                logger.info("Successfully selected 'No' for MIG Customer")
                return True
            else:
                logger.warning("Could not find or select 'No' radio button")
                return False
                
        except Exception as e:
            logger.error(f"Error selecting MIG radio button: {e}", exc_info=True)
            return False
    
    async def click_save_and_close_button(self) -> bool:
        """
        Click the 'Save & Close' button to save the form.
        The button might be hidden by Angular conditions, so we'll try multiple approaches.
        """
        try:
            logger.info("Looking for 'Save & Close' button...")
            
            # Wait a bit for form to be ready and Angular to process
            await asyncio.sleep(WAIT_MEDIUM)
            
            # First, try to trigger Angular to show the button by evaluating conditions
            try:
                logger.info("Triggering Angular to show Save button...")
                await self.page.evaluate("""
                    () => {
                        // Try to trigger Angular digest cycle
                        if (window.angular) {
                            var body = document.body;
                            var scope = angular.element(body).scope();
                            if (scope) {
                                scope.$apply();
                            }
                            
                            // Try to find the form scope and trigger validation
                            var forms = document.querySelectorAll('form');
                            forms.forEach(function(form) {
                                var formScope = angular.element(form).scope();
                                if (formScope) {
                                    // Mark form as valid if needed
                                    if (formScope.$setDirty) {
                                        formScope.$setDirty();
                                    }
                                    if (formScope.$setPristine) {
                                        formScope.$setPristine();
                                    }
                                    formScope.$apply();
                                }
                            });
                            
                            // Try to set the ng-if condition to true
                            var elements = document.querySelectorAll('[ng-if="popSaveIf"], [ng-if*="popSave"]');
                            elements.forEach(function(el) {
                                var elScope = angular.element(el).scope();
                                if (elScope) {
                                    elScope.popSaveIf = true;
                                    elScope.$apply();
                                }
                            });
                            
                            // Try to enable the button by setting disabled condition
                            var buttons = document.querySelectorAll('button[ng-disabled*="popSave"]');
                            buttons.forEach(function(btn) {
                                var btnScope = angular.element(btn).scope();
                                if (btnScope) {
                                    btnScope.popSaveDisabledValue = false;
                                    btnScope.$apply();
                                }
                            });
                        }
                    }
                """)
                await asyncio.sleep(WAIT_SHORT)
            except Exception as e:
                logger.debug(f"Angular trigger attempt: {e}")
            
            # Wait a bit for Angular to process
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Try multiple selectors for the Save & Close button
            save_button_selectors = [
                'button.orange-button:has-text("Save & Close")',
                'button.next-button:has-text("Save & Close")',
                'button.nbs-button:has-text("Save & Close")',
                'button[ng-click="savePopUp()"]',
                'button.orange-button',
                'button.next-button',
                'button:has-text("Save & Close")',
                'button:has-text("Save")',
            ]
            
            button_clicked = False
            for selector in save_button_selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    # Wait for button to be visible
                    button = await self.page.wait_for_selector(
                        selector, 
                        timeout=3000, 
                        state='visible'
                    )
                    
                    if button:
                        # Check if button is disabled
                        is_disabled = await button.get_attribute('disabled')
                        aria_disabled = await button.get_attribute('aria-disabled')
                        
                        if is_disabled or aria_disabled == 'true':
                            logger.warning("Save button is disabled, trying to enable it...")
                            # Try to enable via JavaScript
                            try:
                                await self.page.evaluate("""
                                    (button) => {
                                        if (window.angular) {
                                            var scope = angular.element(button).scope();
                                            if (scope) {
                                                scope.popSaveDisabledValue = false;
                                                scope.$apply();
                                            }
                                        }
                                        button.disabled = false;
                                        button.setAttribute('aria-disabled', 'false');
                                    }
                                """, button)
                                await asyncio.sleep(WAIT_SHORT)
                            except Exception as e:
                                logger.debug(f"Could not enable button via JS: {e}")
                        
                        # Try to click
                        button_text = await button.inner_text()
                        logger.info(f"Found Save button with text: '{button_text}' using selector: {selector}")
                        
                        # Scroll into view
                        await button.scroll_into_view_if_needed()
                        await asyncio.sleep(WAIT_SHORT)
                        
                        # Click the button
                        await button.click()
                        button_clicked = True
                        logger.info("Successfully clicked 'Save & Close' button")
                        break
                        
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not button_clicked:
                # Fallback: Try JavaScript approach to find and click
                logger.info("Trying JavaScript approach to find and click Save button...")
                try:
                    clicked = await self.page.evaluate("""
                        () => {
                            // Find button by text
                            const buttons = Array.from(document.querySelectorAll('button'));
                            for (let button of buttons) {
                                const text = button.textContent.trim();
                                if (text.includes('Save') && (text.includes('Close') || text.includes('&'))) {
                                    // Enable if disabled
                                    if (button.disabled) {
                                        if (window.angular) {
                                            var scope = angular.element(button).scope();
                                            if (scope) {
                                                scope.popSaveDisabledValue = false;
                                                scope.$apply();
                                            }
                                        }
                                        button.disabled = false;
                                    }
                                    button.click();
                                    return true;
                                }
                            }
                            
                            // Try to call savePopUp directly
                            if (window.angular) {
                                var bodyScope = angular.element(document.body).scope();
                                if (bodyScope && bodyScope.$root) {
                                    var rootScope = bodyScope.$root;
                                    if (rootScope.savePopUp) {
                                        rootScope.savePopUp();
                                        return true;
                                    }
                                }
                            }
                            
                            return false;
                        }
                    """)
                    
                    if clicked:
                        logger.info("Successfully clicked Save button via JavaScript")
                        button_clicked = True
                    else:
                        logger.warning("Could not find Save button via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if button_clicked:
                # Wait for save to complete
                logger.info("Waiting for form to save...")
                await asyncio.sleep(WAIT_LONG)
                
                # Check if we navigated away or modal closed
                try:
                    # Wait a bit to see if page changes
                    await asyncio.sleep(WAIT_MEDIUM)
                    logger.info("Save button clicked - form should be saved")
                except Exception as e:
                    logger.debug(f"Post-save check: {e}")
                
                return True
            else:
                logger.error("Could not find or click 'Save & Close' button")
                # Take screenshot for debugging
                await self.page.screenshot(
                    path=str(LOG_DIR / 'save_button_not_found.png'), 
                    full_page=True
                )
                logger.info(f"Screenshot saved to {LOG_DIR / 'save_button_not_found.png'}")
                return False
                
        except Exception as e:
            logger.error(f"Error clicking Save & Close button: {e}", exc_info=True)
            return False
    
    async def get_page(self) -> Page:
        """Get the current page after login"""
        return self.page
    
    async def close(self) -> None:
        """Close browser and cleanup"""
        try:
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Browser closed and playwright stopped")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")


async def main():
    """Test function"""
    login_handler = EncovaLogin()
    try:
        success = await login_handler.login()
        if success:
            print("Login successful!")
            await asyncio.sleep(10)
        else:
            print("Login failed!")
    finally:
        await login_handler.close()


if __name__ == "__main__":
    asyncio.run(main())
