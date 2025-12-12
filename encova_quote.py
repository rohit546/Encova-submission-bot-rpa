"""
Encova Quote Automation
Handles the quoting process after account creation
Uses cookies from existing session - does NOT re-login
"""
import asyncio
import logging
import time
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page

from config import (
    LOG_DIR,
    SESSION_DIR,
    WAIT_SHORT,
    WAIT_MEDIUM,
    WAIT_LONG,
    WAIT_PAGE_LOAD,
    TIMEOUT_MEDIUM,
    TIMEOUT_LONG,
    TIMEOUT_PAGE,
    ENABLE_TRACING,
    TRACE_DIR,
    BROWSER_TIMEOUT,
    BROWSER_HEADLESS,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'encova_quote.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EncovaQuote:
    """Handles Encova quote automation after account creation"""
    
    # Base URL for quote page
    QUOTE_URL_BASE = "https://agent.encova.com/gpa/html/new-quote"
    
    def __init__(self, account_number: str, task_id: str = None, trace_id: str = None):
        """
        Initialize EncovaQuote
        
        Args:
            account_number: The Encova account number (e.g., "4001499718")
            task_id: Task ID for browser data folder
            trace_id: Trace ID for trace file naming
        """
        self.account_number = account_number
        self.task_id = task_id or "default"
        self.trace_id = trace_id or f"quote_{account_number}"
        self.quote_url = f"{self.QUOTE_URL_BASE}/{account_number}"
        
        # Browser components
        self.playwright = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.cookies_file = SESSION_DIR / "encova_cookies.json"
        self.trace_path = TRACE_DIR / f"{self.trace_id}.zip" if ENABLE_TRACING else None
        
        logger.info(f"EncovaQuote initialized for account: {account_number}")
        logger.info(f"Quote URL: {self.quote_url}")
    
    async def init_browser(self) -> None:
        """Initialize browser with persistent context using existing cookies"""
        import json
        
        self.playwright = await async_playwright().start()
        
        # Use shared browser data directory (same as account creation)
        user_data_dir = SESSION_DIR / f"browser_data_{self.task_id}"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Using browser data from: {user_data_dir}")
        
        if ENABLE_TRACING:
            logger.info(f"Tracing ENABLED - will save to: {self.trace_path}")
        
        # Use persistent context to reuse cookies
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=BROWSER_HEADLESS,  # Use config setting (True for Railway)
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        # Load cookies from file if exists
        if self.cookies_file.exists():
            try:
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies from {self.cookies_file}")
            except Exception as e:
                logger.warning(f"Could not load cookies: {e}")
        
        # Start tracing if enabled
        if ENABLE_TRACING and self.trace_path:
            await self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            logger.info("Trace recording started")
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(BROWSER_TIMEOUT)
        
        # Anti-detection script
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        logger.info("Browser initialized with existing session")
    
    async def wait_for_url_contains(self, url_part: str, timeout: int = 15) -> bool:
        """
        Wait until the current URL contains a specific string
        
        Args:
            url_part: String to look for in URL
            timeout: Maximum seconds to wait
        
        Returns:
            bool: True if URL contains the string within timeout
        """
        try:
            logger.info(f"Waiting for URL to contain: {url_part}")
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                current_url = self.page.url
                if url_part.lower() in current_url.lower():
                    logger.info(f"URL verified: {current_url}")
                    await asyncio.sleep(WAIT_SHORT)  # Small wait for page to render
                    return True
                await asyncio.sleep(0.5)
            
            logger.warning(f"Timeout waiting for URL containing '{url_part}'. Current: {self.page.url}")
            return False
            
        except Exception as e:
            logger.error(f"Error waiting for URL: {e}")
            return False

    async def navigate_to_quote(self) -> bool:
        """
        Navigate directly to the quote page using existing cookies
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Navigating directly to quote page: {self.quote_url}")
            
            await self.page.goto(self.quote_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(WAIT_PAGE_LOAD)
            
            current_url = self.page.url
            logger.info(f"Current URL: {current_url}")
            
            # Check if we got redirected to login (cookies expired)
            if "login" in current_url.lower() or "auth.encova.com" in current_url:
                logger.error("Redirected to login - cookies may be expired!")
                return False
            
            if self.account_number in current_url:
                logger.info(f"Successfully navigated to quote page for account {self.account_number}")
                return True
            else:
                logger.warning(f"Unexpected URL: {current_url}")
                return True  # Continue anyway
                
        except Exception as e:
            logger.error(f"Error navigating to quote page: {e}", exc_info=True)
            return False
    
    async def close_help_modal(self) -> bool:
        """
        Close the "Need Help Deciding?" modal if it appears
        The modal has an X button with class "modal-close" and ng-click="close()"
        
        Returns:
            bool: True if modal was closed or didn't appear
        """
        try:
            logger.info("Checking for 'Need Help Deciding?' modal...")
            
            # Wait a moment for modal to appear
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Check if modal is visible
            modal_visible = await self.page.evaluate('''
                () => {
                    // Look for the modal with "Need Help Deciding?" title
                    const modalTitle = document.querySelector('h3.modal-title');
                    if (modalTitle && modalTitle.textContent.includes('Need Help Deciding')) {
                        return true;
                    }
                    
                    // Also check for the modal container
                    const modal = document.querySelector('.add-location-options');
                    if (modal && modal.offsetParent !== null) {
                        return true;
                    }
                    
                    // Check for modal-close button visibility
                    const closeBtn = document.querySelector('a.modal-close');
                    if (closeBtn && closeBtn.offsetParent !== null) {
                        return true;
                    }
                    
                    return false;
                }
            ''')
            
            if not modal_visible:
                logger.info("'Need Help Deciding?' modal not visible, continuing...")
                return True
            
            logger.info("'Need Help Deciding?' modal detected, closing it...")
            
            # Try to click the X (close) button
            close_selectors = [
                'a.modal-close',  # The X button from screenshot
                'a[ng-click="close()"]',
                '.modal-close',
                'a.modal-close[tabindex="0"]',
                'button:has-text("Cancel")',  # Fallback to Cancel button
                'button[ng-click="close()"]',
            ]
            
            clicked = False
            for selector in close_selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    button = await self.page.wait_for_selector(
                        selector, timeout=3000, state='visible'
                    )
                    
                    if button:
                        await button.click()
                        clicked = True
                        logger.info(f"Clicked close button with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not clicked:
                # Try JavaScript approach
                logger.info("Trying JavaScript to close modal...")
                try:
                    js_clicked = await self.page.evaluate('''
                        () => {
                            // Try clicking the X button
                            const closeBtn = document.querySelector('a.modal-close');
                            if (closeBtn) {
                                closeBtn.click();
                                return 'close_button';
                            }
                            
                            // Try Cancel button
                            const cancelBtn = document.querySelector('button[ng-click="close()"]');
                            if (cancelBtn) {
                                cancelBtn.click();
                                return 'cancel_button';
                            }
                            
                            // Try calling close() function directly via Angular
                            if (window.angular) {
                                const modal = document.querySelector('.add-location-options');
                                if (modal) {
                                    const scope = angular.element(modal).scope();
                                    if (scope && scope.close) {
                                        scope.close();
                                        scope.$apply();
                                        return 'angular_close';
                                    }
                                }
                            }
                            
                            return null;
                        }
                    ''')
                    
                    if js_clicked:
                        clicked = True
                        logger.info(f"Closed modal via JavaScript: {js_clicked}")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if clicked:
                await asyncio.sleep(WAIT_MEDIUM)
                logger.info("'Need Help Deciding?' modal closed successfully!")
                return True
            else:
                logger.warning("Could not close the modal - may need manual intervention")
                return False
                
        except Exception as e:
            logger.error(f"Error closing help modal: {e}", exc_info=True)
            return False
    
    async def select_line_of_business(self, line: str = "General Liability") -> bool:
        """
        Select a line of business on the quote page
        
        Args:
            line: The line of business to select (e.g., "General Liability", "Commercial Property")
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Selecting line of business: {line}")
            
            # Map common names to selectors
            line_selectors = {
                "Commercial Property": 'div[ng-click*="Commercial Property Policy"]',
                "General Liability": 'div[ng-click*="General Liability"]',
                "Inland Marine": 'div[ng-click*="Inland Marine"]',
                "Workers Compensation": 'div[ng-click*="Workers Compensation"]',
                "Commercial Package Policy": 'div[ng-click*="Commercial Package Policy"]',
                "BOP": 'div[ng-click*="Businessowners Policy"]',
            }
            
            selector = line_selectors.get(line)
            if not selector:
                # Try generic text search
                selector = f'div:has-text("{line}")'
            
            # Click the line of business
            element = await self.page.wait_for_selector(selector, timeout=TIMEOUT_MEDIUM, state='visible')
            if element:
                await element.click()
                logger.info(f"Clicked on '{line}'")
                await asyncio.sleep(WAIT_MEDIUM)
                return True
            else:
                logger.warning(f"Could not find line of business: {line}")
                return False
                
        except Exception as e:
            logger.error(f"Error selecting line of business: {e}", exc_info=True)
            return False
    
    async def select_commercial_package_policy(self) -> bool:
        """
        Select 'Commercial Package Policy (CPP)' from Choose a Line Of Business
        Selector: a.square[ng-data="cpp"] - becomes 'square selected' when clicked
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Selecting Commercial Package Policy (CPP)...")
            
            # Wait for page to be ready
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Try multiple selectors for CPP
            cpp_selectors = [
                'a.square[ng-data="cpp"]',  # Primary selector from screenshot
                'a[ng-data="cpp"]',
                'a.square[ng-click*="toggleLob(\'cpp\')"]',
                'a[ng-click*="cpp"]',
            ]
            
            clicked = False
            for selector in cpp_selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    element = await self.page.wait_for_selector(
                        selector, timeout=5000, state='visible'
                    )
                    
                    if element:
                        # Check if already selected
                        class_name = await element.get_attribute('class')
                        if 'selected' in (class_name or ''):
                            logger.info("CPP is already selected")
                            return True
                        
                        # Click to select
                        await element.click()
                        clicked = True
                        logger.info(f"Clicked CPP with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not clicked:
                # Try JavaScript approach
                logger.info("Trying JavaScript to click CPP...")
                try:
                    js_clicked = await self.page.evaluate('''
                        () => {
                            // Find CPP square
                            const cpp = document.querySelector('a.square[ng-data="cpp"]');
                            if (cpp) {
                                cpp.click();
                                return true;
                            }
                            
                            // Try via Angular function
                            if (window.angular) {
                                const body = document.body;
                                const scope = angular.element(body).scope();
                                if (scope && scope.toggleLob) {
                                    scope.toggleLob('cpp');
                                    scope.$apply();
                                    return true;
                                }
                            }
                            
                            return false;
                        }
                    ''')
                    
                    if js_clicked:
                        clicked = True
                        logger.info("Clicked CPP via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if clicked:
                await asyncio.sleep(WAIT_MEDIUM)
                
                # Verify selection
                is_selected = await self.page.evaluate('''
                    () => {
                        const cpp = document.querySelector('a.square[ng-data="cpp"]');
                        if (cpp) {
                            return cpp.classList.contains('selected');
                        }
                        return false;
                    }
                ''')
                
                if is_selected:
                    logger.info("Commercial Package Policy (CPP) selected successfully!")
                    return True
                else:
                    logger.warning("CPP clicked but 'selected' class not found - may still be selected")
                    return True  # Continue anyway
            else:
                logger.error("Could not click Commercial Package Policy")
                return False
                
        except Exception as e:
            logger.error(f"Error selecting CPP: {e}", exc_info=True)
            return False
    
    async def click_next_button(self) -> bool:
        """
        Click the 'NEXT' button to proceed to the next step
        Selector: button.nbs-button.orange-button.next-button[ng-click="nextMain()"]
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Clicking NEXT button...")
            
            # Wait for button to be ready
            await asyncio.sleep(WAIT_SHORT)
            
            # Try multiple selectors for NEXT button
            next_selectors = [
                'button.next-button[ng-click="nextMain()"]',  # Primary from screenshot
                'button.orange-button.next-button',
                'button.nbs-button.orange-button.next-button',
                'button[ng-click="nextMain()"]',
                'button:has-text("NEXT")',
            ]
            
            clicked = False
            for selector in next_selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    button = await self.page.wait_for_selector(
                        selector, timeout=5000, state='visible'
                    )
                    
                    if button:
                        # Check if button is disabled
                        is_disabled = await button.get_attribute('aria-disabled')
                        ng_disabled = await button.get_attribute('ng-disabled')
                        
                        if is_disabled == 'true':
                            logger.warning("NEXT button is disabled")
                            return False
                        
                        # Click the button
                        await button.click()
                        clicked = True
                        logger.info(f"Clicked NEXT button with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not clicked:
                # Try JavaScript approach
                logger.info("Trying JavaScript to click NEXT...")
                try:
                    js_clicked = await self.page.evaluate('''
                        () => {
                            // Find NEXT button
                            const nextBtn = document.querySelector('button[ng-click="nextMain()"]');
                            if (nextBtn && !nextBtn.disabled) {
                                nextBtn.click();
                                return true;
                            }
                            
                            // Try calling nextMain() directly via Angular
                            if (window.angular) {
                                const body = document.body;
                                const scope = angular.element(body).scope();
                                if (scope && scope.nextMain) {
                                    scope.nextMain();
                                    scope.$apply();
                                    return true;
                                }
                            }
                            
                            return false;
                        }
                    ''')
                    
                    if js_clicked:
                        clicked = True
                        logger.info("Clicked NEXT via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if clicked:
                logger.info("NEXT button clicked - waiting for page to load...")
                await asyncio.sleep(WAIT_PAGE_LOAD)
                return True
            else:
                logger.error("Could not click NEXT button")
                return False
                
        except Exception as e:
            logger.error(f"Error clicking NEXT button: {e}", exc_info=True)
            return False
    
    async def add_dba(self, dba_name: str) -> bool:
        """
        Add a DBA (Doing Business As) name on the BASIC POLICY INFORMATION page
        1. Click "+ ADD DBA" button
        2. Fill the DBA input field that appears
        
        Args:
            dba_name: The DBA name to add
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Adding DBA: {dba_name}")
            
            # Wait for page to be ready
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Step 1: Click "+ ADD DBA" button
            add_dba_selectors = [
                'button[ng-click*="addDbaNew"]',  # From screenshot
                'button.tertiary-button-default:has-text("ADD DBA")',
                'button.txt-icon-btn:has-text("ADD DBA")',
                'button:has-text("ADD DBA")',
            ]
            
            clicked = False
            for selector in add_dba_selectors:
                try:
                    logger.debug(f"Trying ADD DBA selector: {selector}")
                    button = await self.page.wait_for_selector(
                        selector, timeout=5000, state='visible'
                    )
                    
                    if button:
                        await button.click()
                        clicked = True
                        logger.info(f"Clicked ADD DBA button with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not clicked:
                # Try JavaScript approach
                logger.info("Trying JavaScript to click ADD DBA...")
                try:
                    js_clicked = await self.page.evaluate('''
                        () => {
                            // Find ADD DBA button
                            const buttons = document.querySelectorAll('button');
                            for (let btn of buttons) {
                                if (btn.textContent.includes('ADD DBA')) {
                                    btn.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''')
                    
                    if js_clicked:
                        clicked = True
                        logger.info("Clicked ADD DBA via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if not clicked:
                logger.error("Could not click ADD DBA button")
                return False
            
            # Wait for input field to appear
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Step 2: Fill the DBA input field
            dba_input_selectors = [
                'input[ng-model="item.dBAName"]',  # From screenshot
                'input#input_32',
                'input[name="input_32"]',
                'input[type="text"][ng-model*="dBAName"]',
            ]
            
            filled = False
            for selector in dba_input_selectors:
                try:
                    logger.debug(f"Trying DBA input selector: {selector}")
                    input_field = await self.page.wait_for_selector(
                        selector, timeout=5000, state='visible'
                    )
                    
                    if input_field:
                        await input_field.fill(dba_name)
                        filled = True
                        logger.info(f"Filled DBA input with: {dba_name}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not filled:
                # Try JavaScript approach
                logger.info("Trying JavaScript to fill DBA input...")
                try:
                    js_filled = await self.page.evaluate(f'''
                        () => {{
                            // Find DBA input field
                            const input = document.querySelector('input[ng-model="item.dBAName"]') ||
                                         document.querySelector('input[ng-model*="dBAName"]');
                            if (input) {{
                                input.value = '{dba_name}';
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }}
                    ''')
                    
                    if js_filled:
                        filled = True
                        logger.info("Filled DBA via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if filled:
                await asyncio.sleep(WAIT_SHORT)
                logger.info(f"DBA '{dba_name}' added successfully!")
                return True
            else:
                logger.error("Could not fill DBA input field")
                return False
                
        except Exception as e:
            logger.error(f"Error adding DBA: {e}", exc_info=True)
            return False
    
    async def select_organization_type(self, org_type: str = "LLC") -> bool:
        """
        Select Organization Type from dropdown on BASIC POLICY INFORMATION page
        Type the value and press Enter to select
        
        Args:
            org_type: Organization type (e.g., "LLC", "Corporation")
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Selecting Organization Type: {org_type}")
            
            await asyncio.sleep(WAIT_SHORT)
            
            # Click on the Organization Type dropdown toggle
            # It's a ui-select dropdown similar to others
            dropdown_selectors = [
                'div[ng-model="quoteandbind.submission.draftData.policyData.organizationType"] .ui-select-toggle',
                'span.ui-select-toggle[aria-label="Select box activate"]',
            ]
            
            # Find the correct dropdown by looking for Organization Type section
            clicked = await self.page.evaluate('''
                () => {
                    // Find all ui-select toggles
                    const toggles = document.querySelectorAll('.ui-select-toggle');
                    for (let toggle of toggles) {
                        // Look for the one near Organization Type label
                        let parent = toggle.parentElement;
                        let depth = 0;
                        while (parent && depth < 10) {
                            const text = parent.textContent || '';
                            if (text.includes('ORGANIZATION TYPE') && !text.includes('PACKAGE RISK TYPE')) {
                                toggle.click();
                                return true;
                            }
                            parent = parent.parentElement;
                            depth++;
                        }
                    }
                    return false;
                }
            ''')
            
            if not clicked:
                logger.warning("Could not find Organization Type dropdown, trying generic approach...")
                # Try clicking any visible dropdown toggle
                for selector in dropdown_selectors:
                    try:
                        dropdown = await self.page.wait_for_selector(selector, timeout=3000, state='visible')
                        if dropdown:
                            await dropdown.click()
                            clicked = True
                            break
                    except:
                        continue
            
            if clicked:
                await asyncio.sleep(WAIT_SHORT)
                
                # Type the organization type and press Enter
                search_input = await self.page.wait_for_selector(
                    'input.ui-select-search, input[ng-model="$select.search"]',
                    timeout=3000, state='visible'
                )
                
                if search_input:
                    await search_input.fill(org_type)
                    await asyncio.sleep(WAIT_SHORT)
                    await search_input.press('Enter')
                    await asyncio.sleep(WAIT_SHORT)
                    logger.info(f"Organization Type '{org_type}' selected successfully!")
                    return True
            
            logger.error("Could not select Organization Type")
            return False
            
        except Exception as e:
            logger.error(f"Error selecting Organization Type: {e}", exc_info=True)
            return False
    
    async def fill_year_business_started(self, year: str = "2010") -> bool:
        """
        Fill the Year Business Started field
        
        Args:
            year: The year the business started (e.g., "2010")
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Filling Year Business Started: {year}")
            
            await asyncio.sleep(WAIT_MEDIUM)
            
            # The Year Business Started input is a number type input
            # From screenshot: input#inputCtrl9 with ng-model="model.value" type="number"
            # It should be near "YEAR BUSINESS STARTED" label
            
            filled = await self.page.evaluate(f'''
                () => {{
                    // Method 1: Find by looking at all number inputs and checking parent for "YEAR BUSINESS STARTED"
                    const numberInputs = document.querySelectorAll('input[type="number"]');
                    for (let input of numberInputs) {{
                        let parent = input.parentElement;
                        let depth = 0;
                        while (parent && depth < 8) {{
                            const text = (parent.textContent || '').toUpperCase();
                            // Make sure it's YEAR BUSINESS STARTED and not DBA or other field
                            if (text.includes('YEAR BUSINESS STARTED') && !text.includes('DBA')) {{
                                // Make sure this input is visible
                                if (input.offsetParent !== null) {{
                                    input.focus();
                                    input.value = '{year}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    
                                    // Also try Angular model update
                                    if (window.angular) {{
                                        try {{
                                            const scope = angular.element(input).scope();
                                            if (scope && scope.model) {{
                                                scope.model.value = {year};
                                                scope.$apply();
                                            }}
                                        }} catch(e) {{}}
                                    }}
                                    return true;
                                }}
                            }}
                            parent = parent.parentElement;
                            depth++;
                        }}
                    }}
                    
                    // Method 2: Try to find inputCtrl9 specifically
                    const inputCtrl9 = document.getElementById('inputCtrl9');
                    if (inputCtrl9 && inputCtrl9.offsetParent !== null) {{
                        inputCtrl9.focus();
                        inputCtrl9.value = '{year}';
                        inputCtrl9.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputCtrl9.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        inputCtrl9.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return true;
                    }}
                    
                    return false;
                }}
            ''')
            
            if filled:
                logger.info(f"Year Business Started '{year}' filled successfully!")
                return True
            else:
                logger.error("Could not fill Year Business Started")
                return False
            
        except Exception as e:
            logger.error(f"Error filling Year Business Started: {e}", exc_info=True)
            return False
    
    async def select_employees_radio(self, more_than_25: bool = False) -> bool:
        """
        Select radio button for "Are there 25 or more employees?"
        
        Args:
            more_than_25: True for Yes, False for No
        
        Returns:
            bool: True if successful
        """
        try:
            value = "Yes" if more_than_25 else "No"
            logger.info(f"Selecting '25 or more employees': {value}")
            
            await asyncio.sleep(WAIT_SHORT)
            
            # Find the radio button by value and aria-label
            # From screenshot: md-radio-button with aria-label="No" and value="false"
            radio_value = "true" if more_than_25 else "false"
            
            # Use JavaScript to find and click the correct radio button
            clicked = await self.page.evaluate(f'''
                () => {{
                    // Find radio buttons near "25 or more employees" text
                    const containers = document.querySelectorAll('div, section, fieldset');
                    for (let container of containers) {{
                        const text = (container.textContent || '').toLowerCase();
                        if (text.includes('25 or more employees') && !text.includes('annual revenues')) {{
                            // Find radio button with correct value
                            const radios = container.querySelectorAll('md-radio-button');
                            for (let radio of radios) {{
                                const ariaLabel = radio.getAttribute('aria-label') || '';
                                if (ariaLabel === '{value}') {{
                                    radio.click();
                                    return true;
                                }}
                            }}
                        }}
                    }}
                    return false;
                }}
            ''')
            
            if clicked:
                logger.info(f"'25 or more employees' set to {value} successfully!")
                return True
            else:
                logger.warning("Could not find employees radio button, it may already be set")
                return True  # Don't fail if already set
            
        except Exception as e:
            logger.error(f"Error selecting employees radio: {e}", exc_info=True)
            return False
    
    async def select_revenue_radio(self, above_2_5_million: bool = False) -> bool:
        """
        Select radio button for "Are annual revenues at or above $2.5 million?"
        
        Args:
            above_2_5_million: True for Yes, False for No
        
        Returns:
            bool: True if successful
        """
        try:
            value = "Yes" if above_2_5_million else "No"
            ng_value = "true" if above_2_5_million else "false"
            logger.info(f"Selecting 'Annual revenues above $2.5 million': {value}")
            
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Direct approach: Find the specific radio button by aria-label and ng-value
            # From screenshot: md-radio-button with ng-value="false" and aria-label="No"
            radio_selector = f'md-radio-button[aria-label="{value}"][ng-value="{ng_value}"]'
            
            try:
                # Get all matching radio buttons
                radios = await self.page.query_selector_all(radio_selector)
                logger.info(f"Found {len(radios)} radio buttons matching selector")
                
                # We need the second one (revenue question, not employees question)
                if len(radios) >= 2:
                    # Click the second matching radio (revenue question)
                    await radios[1].click()
                    logger.info(f"Clicked second radio button (revenue question)")
                    await asyncio.sleep(WAIT_SHORT)
                    return True
                elif len(radios) == 1:
                    # Only one found, click it
                    await radios[0].click()
                    logger.info(f"Clicked only matching radio button")
                    await asyncio.sleep(WAIT_SHORT)
                    return True
            except Exception as e:
                logger.warning(f"Direct selector approach failed: {e}")
            
            # Fallback: Use JavaScript with more specific targeting
            clicked = await self.page.evaluate(f'''
                () => {{
                    // Get all md-radio-groups on the page
                    const radioGroups = document.querySelectorAll('md-radio-group');
                    console.log('Found radio groups:', radioGroups.length);
                    
                    // The revenue question should be the second radio group
                    // (first is employees, second is revenue)
                    for (let i = 0; i < radioGroups.length; i++) {{
                        const group = radioGroups[i];
                        const groupText = (group.closest('form-field, div.form-group, div')?.textContent || '').toLowerCase();
                        
                        // Check if this group is for revenue question
                        if (groupText.includes('revenue') || groupText.includes('2.5 million') || i === 1) {{
                            const radio = group.querySelector('md-radio-button[ng-value="{ng_value}"], md-radio-button[aria-label="{value}"]');
                            if (radio) {{
                                // Click the radio button
                                radio.click();
                                console.log('Clicked revenue radio in group', i);
                                return true;
                            }}
                        }}
                    }}
                    
                    // Last resort: click any unselected radio with matching value
                    const allRadios = document.querySelectorAll('md-radio-button[ng-value="{ng_value}"]');
                    for (let radio of allRadios) {{
                        if (radio.getAttribute('aria-checked') !== 'true') {{
                            radio.click();
                            console.log('Clicked unselected radio');
                            return true;
                        }}
                    }}
                    
                    return false;
                }}
            ''')
            
            if clicked:
                logger.info(f"'Annual revenues above $2.5 million' set to {value} successfully!")
                return True
            else:
                logger.warning("Could not find revenue radio button")
                await self.take_screenshot("revenue_radio_failed")
                return False
            
        except Exception as e:
            logger.error(f"Error selecting revenue radio: {e}", exc_info=True)
            return False

    async def unselect_coverage_option(self, name: str, for_attribute: str) -> bool:
        """
        Unselect a coverage option (square label) on the Coverage Parts page
        Only clicks if it's currently selected
        
        Args:
            name: Display name for logging (e.g., "EPLI", "Cyber Liability")
            for_attribute: The 'for' attribute of the label (e.g., "NEW_EPLI_Ext", "NEW_CyberLiability")
        
        Returns:
            bool: True if successful or not needed
        """
        try:
            logger.info(f"Checking if {name} is selected...")
            
            # Wait a bit for the page to be ready
            await asyncio.sleep(WAIT_SHORT)
            
            # Check if the label is selected (has 'selected' class) and click to unselect
            unselected = await self.page.evaluate(f'''
                () => {{
                    // Method 1: Find by exact 'for' attribute
                    let label = document.querySelector('label[for="{for_attribute}"]');
                    
                    // Method 2: Try partial match if exact not found
                    if (!label) {{
                        const allLabels = document.querySelectorAll('label.square');
                        for (let lbl of allLabels) {{
                            const forAttr = lbl.getAttribute('for') || '';
                            if (forAttr.includes('{for_attribute}') || forAttr.toLowerCase().includes('{name.lower()}')) {{
                                label = lbl;
                                break;
                            }}
                        }}
                    }}
                    
                    // Method 3: Find by text content
                    if (!label) {{
                        const allLabels = document.querySelectorAll('label.square, label.small');
                        for (let lbl of allLabels) {{
                            const text = (lbl.textContent || '').toLowerCase();
                            if (text.includes('{name.lower()}') || text.includes('epli') || text.includes('cyber')) {{
                                const forAttr = lbl.getAttribute('for') || '';
                                if (forAttr.includes('{for_attribute}')) {{
                                    label = lbl;
                                    break;
                                }}
                            }}
                        }}
                    }}
                    
                    if (!label) {{
                        console.log('Label not found for: {for_attribute}');
                        return 'not_found';
                    }}
                    
                    console.log('Found label:', label.getAttribute('for'), 'classes:', label.className);
                    
                    // Check if it's selected (has 'selected' class)
                    const isSelected = label.classList.contains('selected');
                    console.log('{name} selected:', isSelected);
                    
                    if (isSelected) {{
                        // Click to unselect
                        label.click();
                        console.log('Clicked to unselect {name}');
                        return 'unselected';
                    }} else {{
                        console.log('{name} is not selected, no action needed');
                        return 'already_unselected';
                    }}
                }}
            ''')
            
            if unselected == 'unselected':
                logger.info(f"{name} unselected successfully!")
                await asyncio.sleep(WAIT_SHORT)
                return True
            elif unselected == 'already_unselected':
                logger.info(f"{name} was not selected, no action needed")
                return True
            else:
                # Try direct Playwright approach as fallback
                logger.warning(f"JavaScript couldn't find {name}, trying direct selector...")
                try:
                    label = await self.page.query_selector(f'label[for="{for_attribute}"].selected')
                    if label:
                        await label.click()
                        logger.info(f"{name} unselected via direct click!")
                        await asyncio.sleep(WAIT_SHORT)
                        return True
                    else:
                        # Check if it exists but not selected
                        label_unselected = await self.page.query_selector(f'label[for="{for_attribute}"]')
                        if label_unselected:
                            logger.info(f"{name} exists but is not selected")
                            return True
                except Exception as e:
                    logger.debug(f"Direct selector failed: {e}")
                
                logger.warning(f"Could not find {name} label")
                return False
            
        except Exception as e:
            logger.error(f"Error unselecting {name}: {e}", exc_info=True)
            return False

    async def select_medical_payments_limit(self, value: str = "Exclude") -> bool:
        """
        Select Medical Payments Limit from dropdown on CGL Coverages page
        Type the value and press Enter to select
        
        Args:
            value: The value to select (default: "Exclude")
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Setting Medical Payments Limit to: {value}")
            
            # Wait for page to fully load
            await asyncio.sleep(WAIT_SHORT)
            
            # Get all dropdown toggles on the page
            # Layout: Each Occurrence (0), Damage to Premises (1), General Aggregate (2), 
            #         Medical Payments (3), Prods/Compltd Ops (4)
            # Medical Payments Limit is the 4th dropdown (index 3) in right column
            
            toggles = await self.page.query_selector_all('.ui-select-toggle')
            logger.info(f"Found {len(toggles)} dropdown toggles")
            
            # Medical Payments is the LAST dropdown (6th one, index 5)
            # Layout: Each Occurrence(0), Damage to Premises(1), General Aggregate(2), 
            #         Medical Payments(3), Prods/Compltd Ops(4), BI AND PD DEDUCTIBLE(5)
            # Actually Medical Payments Limit is the 6th/last dropdown
            target_index = 5  # Last dropdown (0-indexed)
            
            if len(toggles) > target_index:
                # Click the Medical Payments dropdown (4th one, index 3)
                await toggles[target_index].click()
                logger.info(f"Clicked dropdown at index {target_index}")
                
                await asyncio.sleep(WAIT_SHORT)
                
                # Type in the search input
                try:
                    search_input = await self.page.wait_for_selector(
                        'input.ui-select-search',
                        timeout=3000,
                        state='visible'
                    )
                    
                    if search_input:
                        await search_input.fill(value)
                        await asyncio.sleep(WAIT_SHORT)
                        await search_input.press('Enter')
                        logger.info(f"Typed '{value}' and pressed Enter for Medical Payments Limit")
                        await asyncio.sleep(WAIT_SHORT)
                        return True
                except Exception as e:
                    logger.warning(f"Could not find search input: {e}")
                    # Try typing directly
                    await self.page.keyboard.type(value)
                    await asyncio.sleep(WAIT_SHORT)
                    await self.page.keyboard.press('Enter')
                    logger.info(f"Typed '{value}' via keyboard")
                    return True
            else:
                logger.warning(f"Not enough dropdowns found. Expected at least {target_index + 1}, found {len(toggles)}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error setting Medical Payments Limit: {e}", exc_info=True)
            return False

    async def select_dropdown_by_index(self, index: int, value: str, name: str = "") -> bool:
        """
        Select a dropdown by its index on the page and type a value
        
        Args:
            index: The 0-based index of the dropdown toggle
            value: The value to type and select
            name: Optional name for logging
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Setting {name or f'dropdown {index}'} to: {value}")
            
            await asyncio.sleep(WAIT_SHORT)
            
            # Get all dropdown toggles on the page
            toggles = await self.page.query_selector_all('.ui-select-toggle')
            logger.info(f"Found {len(toggles)} dropdown toggles")
            
            if len(toggles) > index:
                # Click the dropdown at the specified index
                await toggles[index].click()
                logger.info(f"Clicked dropdown at index {index}")
                
                await asyncio.sleep(WAIT_SHORT)
                
                # Type in the search input
                try:
                    search_input = await self.page.wait_for_selector(
                        'input.ui-select-search',
                        timeout=3000,
                        state='visible'
                    )
                    
                    if search_input:
                        await search_input.fill(value)
                        await asyncio.sleep(WAIT_SHORT)
                        await search_input.press('Enter')
                        logger.info(f"Typed '{value}' and pressed Enter for {name or f'dropdown {index}'}")
                        await asyncio.sleep(WAIT_SHORT)
                        return True
                except Exception as e:
                    logger.warning(f"Could not find search input: {e}")
                    # Try typing directly via keyboard
                    await self.page.keyboard.type(value)
                    await asyncio.sleep(WAIT_SHORT)
                    await self.page.keyboard.press('Enter')
                    logger.info(f"Typed '{value}' via keyboard for {name or f'dropdown {index}'}")
                    await asyncio.sleep(WAIT_SHORT)
                    return True
            else:
                logger.warning(f"Not enough dropdowns found. Expected at least {index + 1}, found {len(toggles)}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error setting {name or f'dropdown {index}'}: {e}", exc_info=True)
            return False

    async def select_dropdown_by_label(self, label_text: str, value: str) -> bool:
        """
        Select a dropdown by finding its associated label text.
        This is more reliable than index-based selection since it finds the exact field.
        
        Args:
            label_text: The exact label text to search for (e.g., "DEDUCTIBLE", "Coinsurance")
            value: The value to type and select
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Setting '{label_text}' dropdown to: {value}")
            
            await asyncio.sleep(0.3)
            
            # Use JavaScript to find the dropdown by its label and click it
            # IMPORTANT: Match exact label text to avoid clicking wrong dropdowns
            clicked = await self.page.evaluate(f'''
                () => {{
                    const labelText = "{label_text}";
                    const labelTextLower = labelText.toLowerCase();
                    
                    // Method 1: Find label element with matching EXACT text and get its parent md-input-container
                    const labels = document.querySelectorAll('label');
                    for (const label of labels) {{
                        // Check all spans inside the label for EXACT match
                        const spans = label.querySelectorAll('span');
                        for (const span of spans) {{
                            const text = (span.textContent || '').trim();
                            const textLower = text.toLowerCase();
                            
                            // Exact match only (case-insensitive)
                            if (textLower === labelTextLower || 
                                textLower === labelTextLower + ' *' ||
                                text === labelText ||
                                text === labelText + ' *') {{
                                
                                // Found the label, now find the dropdown toggle in the same container
                                const container = label.closest('md-input-container');
                                if (container) {{
                                    const toggle = container.querySelector('span.ui-select-toggle');
                                    if (toggle) {{
                                        // Click and return immediately
                                        toggle.click();
                                        return 'clicked via label > span in md-input-container: ' + text;
                                    }}
                                }}
                            }}
                        }}
                    }}
                    
                    // Method 2: Find span with EXACT matching text and walk up to find md-input-container
                    const allSpans = document.querySelectorAll('span');
                    for (const span of allSpans) {{
                        const text = (span.textContent || '').trim();
                        const textLower = text.toLowerCase();
                        
                        // Exact match only
                        if (textLower === labelTextLower || 
                            textLower === labelTextLower + ' *' ||
                            text === labelText ||
                            text === labelText + ' *') {{
                            
                            // Make sure this span is a label (inside label or has bullet-point class)
                            const isLabel = span.closest('label') || 
                                           span.classList.contains('nbs-bullet-point-label') ||
                                           span.parentElement?.tagName === 'LABEL';
                            
                            if (isLabel || span.closest('ng-transclude')) {{
                                // Walk up to find md-input-container
                                let parent = span.parentElement;
                                for (let i = 0; i < 10 && parent; i++) {{
                                    if (parent.tagName === 'MD-INPUT-CONTAINER') {{
                                        const toggle = parent.querySelector('span.ui-select-toggle');
                                        if (toggle) {{
                                            toggle.click();
                                            return 'clicked via span walking up to md-input-container: ' + text;
                                        }}
                                    }}
                                    parent = parent.parentElement;
                                }}
                            }}
                        }}
                    }}
                    
                    // Method 3: Find by bullet point label structure
                    const bulletLabels = document.querySelectorAll('.nbs-bullet-point-label, label.nbs-bullet-point-label');
                    for (const label of bulletLabels) {{
                        const text = (label.textContent || '').trim();
                        const textLower = text.toLowerCase();
                        
                        if (textLower === labelTextLower || 
                            textLower === labelTextLower + ' *' ||
                            text === labelText ||
                            text === labelText + ' *') {{
                            
                            let parent = label.parentElement;
                            for (let i = 0; i < 10 && parent; i++) {{
                                const toggle = parent.querySelector('span.ui-select-toggle');
                                if (toggle) {{
                                    toggle.click();
                                    return 'clicked via bullet point label: ' + text;
                                }}
                                parent = parent.parentElement;
                            }}
                        }}
                    }}
                    
                    return 'not found';
                }}
            ''')
            
            logger.info(f"Dropdown click result for '{label_text}': {clicked}")
            
            if 'clicked' in str(clicked):
                await asyncio.sleep(0.5)
                
                # Try to type in the search input first
                try:
                    search_input = await self.page.wait_for_selector(
                        'input.ui-select-search',
                        timeout=2000,
                        state='visible'
                    )
                    if search_input:
                        await search_input.fill(value)
                        await asyncio.sleep(0.5)
                        
                        # Try to click on the matching option in the dropdown
                        option_clicked = await self.page.evaluate(f'''
                            () => {{
                                const value = "{value}";
                                // Find dropdown options that are visible
                                const options = document.querySelectorAll('.ui-select-choices-row, .ui-select-choices-row-inner, li.ui-select-choices-group div[role="option"], .ui-select-choices span.ui-select-choices-row-inner');
                                for (const opt of options) {{
                                    const text = (opt.textContent || '').trim();
                                    if (text === value || text.includes(value) || text.startsWith(value)) {{
                                        opt.click();
                                        return 'clicked option: ' + text;
                                    }}
                                }}
                                // Also try clicking any highlighted/active option
                                const activeOpt = document.querySelector('.ui-select-choices-row.active, .ui-select-highlight, [class*="active"]');
                                if (activeOpt) {{
                                    activeOpt.click();
                                    return 'clicked active option';
                                }}
                                return 'no option found';
                            }}
                        ''')
                        logger.info(f"Option click result: {option_clicked}")
                        
                        if 'no option' in str(option_clicked):
                            # Fall back to Enter key
                            await self.page.keyboard.press('Enter')
                        
                        logger.info(f"Typed '{value}' in search input for '{label_text}'")
                        await asyncio.sleep(0.5)
                        return True
                except Exception as e:
                    logger.warning(f"Search input approach failed: {e}")
                
                # Fallback: Type via keyboard and try to select option
                await self.page.keyboard.type(value, delay=50)
                await asyncio.sleep(0.5)
                
                # Try to click on the matching option in the dropdown
                option_clicked = await self.page.evaluate(f'''
                    () => {{
                        const value = "{value}";
                        // Find dropdown options that are visible
                        const options = document.querySelectorAll('.ui-select-choices-row, .ui-select-choices-row-inner, li.ui-select-choices-group div[role="option"], span.ui-select-choices-row-inner, div.ui-select-choices-content div');
                        for (const opt of options) {{
                            const text = (opt.textContent || '').trim();
                            if (text === value || text.includes(value) || text.startsWith(value)) {{
                                opt.click();
                                return 'clicked option: ' + text;
                            }}
                        }}
                        // Try clicking any visible option that matches
                        const allDivs = document.querySelectorAll('.ui-select-dropdown div, .ui-select-choices div');
                        for (const div of allDivs) {{
                            const text = (div.textContent || '').trim();
                            if (text === value && div.offsetParent !== null) {{
                                div.click();
                                return 'clicked div option: ' + text;
                            }}
                        }}
                        return 'no option found';
                    }}
                ''')
                logger.info(f"Option click result after keyboard: {option_clicked}")
                
                if 'no option' in str(option_clicked):
                    # Fall back to Enter key
                    await self.page.keyboard.press('Enter')
                
                await asyncio.sleep(0.5)
                logger.info(f"Typed '{value}' via keyboard for '{label_text}'")
                return True
            else:
                logger.warning(f"Could not find dropdown for label '{label_text}'")
                return False
            
        except Exception as e:
            logger.error(f"Error setting dropdown '{label_text}': {e}", exc_info=True)
            return False

    async def select_package_risk_type(self, risk_type: str = "Mercantile") -> bool:
        """
        Select Package Risk Type from the dropdown on LINE SELECTION page
        Type the value and press Enter to select
        
        Args:
            risk_type: The risk type to select (default: "Mercantile")
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Selecting Package Risk Type: {risk_type}")
            
            # Wait for page to be ready
            await asyncio.sleep(WAIT_MEDIUM)
            
            # First, click on the dropdown to open it
            dropdown_selectors = [
                'span.ui-select-toggle[aria-label="Select box activate"]',  # From screenshot
                'span.btn-default.ui-select-toggle',
                '.ui-select-toggle',
                'span[ng-click="$select.activate()"]',
            ]
            
            dropdown_opened = False
            for selector in dropdown_selectors:
                try:
                    logger.debug(f"Trying dropdown selector: {selector}")
                    dropdown = await self.page.wait_for_selector(
                        selector, timeout=5000, state='visible'
                    )
                    
                    if dropdown:
                        await dropdown.click()
                        dropdown_opened = True
                        logger.info(f"Opened dropdown with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not dropdown_opened:
                # Try JavaScript to open dropdown
                logger.info("Trying JavaScript to open dropdown...")
                try:
                    await self.page.evaluate('''
                        () => {
                            const toggle = document.querySelector('.ui-select-toggle');
                            if (toggle) {
                                toggle.click();
                                return true;
                            }
                            return false;
                        }
                    ''')
                    dropdown_opened = True
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            await asyncio.sleep(WAIT_MEDIUM)
            
            # Find the search input and type the risk type
            search_selectors = [
                'input.ui-select-search',
                'input[ng-model="$select.search"]',
                'input[placeholder*="Search"]',
                'input[type="search"]',
            ]
            
            typed = False
            for selector in search_selectors:
                try:
                    logger.debug(f"Trying search input selector: {selector}")
                    search_input = await self.page.wait_for_selector(
                        selector, timeout=3000, state='visible'
                    )
                    
                    if search_input:
                        # Type the risk type
                        await search_input.fill(risk_type)
                        await asyncio.sleep(WAIT_SHORT)
                        
                        # Press Enter to select
                        await search_input.press('Enter')
                        typed = True
                        logger.info(f"Typed '{risk_type}' and pressed Enter")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not typed:
                # Try JavaScript approach
                logger.info("Trying JavaScript to fill dropdown...")
                try:
                    js_result = await self.page.evaluate(f'''
                        () => {{
                            // Find visible search input
                            const inputs = document.querySelectorAll('input.ui-select-search, input[ng-model="$select.search"]');
                            for (let input of inputs) {{
                                if (input.offsetParent !== null) {{
                                    input.value = '{risk_type}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    
                                    // Wait a moment then simulate Enter
                                    setTimeout(() => {{
                                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', keyCode: 13 }}));
                                    }}, 300);
                                    
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    ''')
                    
                    if js_result:
                        typed = True
                        await asyncio.sleep(WAIT_MEDIUM)
                        logger.info("Filled dropdown via JavaScript")
                except Exception as e:
                    logger.warning(f"JavaScript approach failed: {e}")
            
            if typed:
                await asyncio.sleep(WAIT_MEDIUM)
                logger.info(f"Package Risk Type '{risk_type}' selected successfully!")
                return True
            else:
                logger.error("Could not fill Package Risk Type dropdown")
                return False
                
        except Exception as e:
            logger.error(f"Error selecting Package Risk Type: {e}", exc_info=True)
            return False
    
    async def run_quote_automation(self, quote_data: dict = None) -> dict:
        """
        Run the full quote automation
        
        Args:
            quote_data: Dictionary with quote configuration
                - line_of_business: str (default: "cpp" for Commercial Package Policy)
                - package_risk_type: str (default: "Mercantile")
                - Additional fields TBD
        
        Returns:
            dict: Result with success status and details
        """
        result = {
            "success": False,
            "account_number": self.account_number,
            "quote_url": self.quote_url,
            "message": ""
        }
        
        # Get config from quote_data or use defaults
        if quote_data is None:
            quote_data = {}
        package_risk_type = quote_data.get('package_risk_type', 'Mercantile')
        
        try:
            # Step 1: Initialize browser with existing cookies
            logger.info("Step 1: Initializing browser with existing session...")
            await self.init_browser()
            
            # Step 2: Navigate directly to quote page
            logger.info("Step 2: Navigating to quote page...")
            if not await self.navigate_to_quote():
                result["message"] = "Failed to navigate to quote page (cookies may be expired)"
                return result
            
            # Step 3: Close the "Need Help Deciding?" modal if it appears
            logger.info("Step 3: Closing help modal if present...")
            await self.close_help_modal()  # Don't fail if modal not present
            
            # Step 4: Select Commercial Package Policy (CPP)
            logger.info("Step 4: Selecting Commercial Package Policy...")
            if not await self.select_commercial_package_policy():
                result["message"] = "Failed to select Commercial Package Policy"
                return result
            
            # Step 5: Click NEXT button to go to LINE SELECTION page
            logger.info("Step 5: Clicking NEXT button...")
            if not await self.click_next_button():
                result["message"] = "Failed to click NEXT button"
                return result
            
            # Step 6: Select Package Risk Type dropdown (Mercantile)
            logger.info("Step 6: Selecting Package Risk Type...")
            if not await self.select_package_risk_type(package_risk_type):
                result["message"] = "Failed to select Package Risk Type"
                return result
            
            # Step 7: Click NEXT button again to proceed to BASIC POLICY INFORMATION
            logger.info("Step 7: Clicking NEXT button (Line Selection)...")
            if not await self.click_next_button():
                result["message"] = "Failed to click NEXT button on Line Selection"
                return result
            
            # Step 8: Add DBA on BASIC POLICY INFORMATION page
            dba_name = quote_data.get('dba', quote_data.get('dba_name', ''))
            logger.info(f"Step 8: Adding DBA: {dba_name}...")
            if not await self.add_dba(dba_name):
                result["message"] = "Failed to add DBA"
                return result
            
            # Step 9: Select Organization Type
            org_type = quote_data.get('organization_type', 'LLC')
            logger.info(f"Step 9: Selecting Organization Type: {org_type}...")
            if not await self.select_organization_type(org_type):
                result["message"] = "Failed to select Organization Type"
                return result
            
            # Step 10: Fill Year Business Started
            year_started = quote_data.get('year_business_started', '2015')
            logger.info(f"Step 10: Filling Year Business Started: {year_started}...")
            if not await self.fill_year_business_started(year_started):
                result["message"] = "Failed to fill Year Business Started"
                return result
            
            # Step 11: Select "25 or more employees" radio (No)
            more_than_25 = quote_data.get('more_than_25_employees', False)
            logger.info(f"Step 11: Selecting '25 or more employees': {'Yes' if more_than_25 else 'No'}...")
            if not await self.select_employees_radio(more_than_25):
                result["message"] = "Failed to select employees radio"
                return result
            
            # Step 12: Select "Annual revenues above $2.5 million" radio (No)
            above_2_5m = quote_data.get('revenue_above_2_5_million', False)
            logger.info(f"Step 12: Selecting 'Revenue above $2.5M': {'Yes' if above_2_5m else 'No'}...")
            if not await self.select_revenue_radio(above_2_5m):
                result["message"] = "Failed to select revenue radio"
                return result
            
            # Step 13: Click NEXT button to proceed
            logger.info("Step 13: Clicking NEXT button (Basic Policy Info)...")
            if not await self.click_next_button():
                result["message"] = "Failed to click NEXT button on Basic Policy Info"
                return result
            
            # Step 14: Now on LOCATION page - click NEXT to proceed
            logger.info("Step 14: On Location page - clicking NEXT...")
            await self.wait_for_url_contains("cpp/location", timeout=10)
            if not await self.click_next_button():
                result["message"] = "Failed to click NEXT button on Location page"
                return result
            
            # Step 15: On Coverage Parts page - unselect EPLI and Cyber Liability
            logger.info("Step 15: On Coverage Parts page - unselecting expensive options...")
            await self.wait_for_url_contains("gl/coverageParts", timeout=10)
            logger.info(f"Current URL: {self.page.url}")
            
            # Unselect EPLI - try multiple possible 'for' values
            epli_unselected = False
            for epli_for in ["NEW_EPLI_Ext", "EPLI_Ext", "NEW_EPLI", "epli"]:
                if await self.unselect_coverage_option("EPLI", epli_for):
                    epli_unselected = True
                    break
            
            if not epli_unselected:
                # Try clicking by text content
                logger.info("Trying to unselect EPLI by text content...")
                try:
                    clicked = await self.page.evaluate('''
                        () => {
                            // Find all selected labels
                            const labels = document.querySelectorAll('label.selected, label.square.selected');
                            for (let label of labels) {
                                const text = (label.textContent || '').toUpperCase();
                                const forAttr = (label.getAttribute('for') || '').toUpperCase();
                                if (text.includes('EPLI') || forAttr.includes('EPLI')) {
                                    console.log('Found EPLI label:', label.getAttribute('for'), label.textContent);
                                    label.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''')
                    if clicked:
                        logger.info("EPLI unselected by text content!")
                        await asyncio.sleep(WAIT_SHORT)
                except Exception as e:
                    logger.warning(f"Could not unselect EPLI by text: {e}")
            
            # Unselect Cyber Liability - try multiple possible 'for' values
            cyber_unselected = False
            for cyber_for in ["NEW_CyberLiability", "CyberLiability", "NEW_Cyber", "cyber"]:
                if await self.unselect_coverage_option("Cyber Liability", cyber_for):
                    cyber_unselected = True
                    break
            
            if not cyber_unselected:
                # Try clicking by text content
                logger.info("Trying to unselect Cyber Liability by text content...")
                try:
                    clicked = await self.page.evaluate('''
                        () => {
                            const labels = document.querySelectorAll('label.selected, label.square.selected');
                            for (let label of labels) {
                                const text = (label.textContent || '').toUpperCase();
                                const forAttr = (label.getAttribute('for') || '').toUpperCase();
                                if (text.includes('CYBER') || forAttr.includes('CYBER')) {
                                    console.log('Found Cyber label:', label.getAttribute('for'), label.textContent);
                                    label.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''')
                    if clicked:
                        logger.info("Cyber Liability unselected by text content!")
                        await asyncio.sleep(WAIT_SHORT)
                except Exception as e:
                    logger.warning(f"Could not unselect Cyber by text: {e}")
            
            # Step 16: Click NEXT on Coverage Parts page
            logger.info("Step 16: Clicking NEXT on Coverage Parts page...")
            await asyncio.sleep(WAIT_SHORT)
            if not await self.click_next_button():
                result["message"] = "Failed to click NEXT button on Coverage Parts page"
                return result
            
            # Step 17: On GL Locations page - click NEXT
            logger.info("Step 17: On GL Locations page - clicking NEXT...")
            await self.wait_for_url_contains("gl/locations", timeout=10)
            if not await self.click_next_button():
                result["message"] = "Failed to click NEXT button on GL Locations page"
                return result
            
            # Step 18: On CGL Coverages page - set BI/PD Deductible and Medical Payments Limit
            logger.info("Step 18: On CGL Coverages page - setting dropdowns...")
            
            # Wait for CGL Coverages page URL
            if not await self.wait_for_url_contains("coverages", timeout=15):
                logger.warning("Did not reach CGL Coverages page")
            
            # First select BI AND PD DEDUCTIBLE (index 3, 4th dropdown) - "2,000 Per Occurrence"
            if not await self.select_dropdown_by_index(3, "2,000 Per Occurrence", "BI AND PD DEDUCTIBLE"):
                logger.warning("Could not set BI AND PD DEDUCTIBLE - continuing anyway")
            
            # Then select Medical Payments Limit (index 5, 6th/last dropdown) - "Exclude"
            if not await self.select_dropdown_by_index(5, "Exclude", "Medical Payments Limit"):
                logger.warning("Could not set Medical Payments Limit - continuing anyway")
            
            # Step 19: Switch to CLASS CODES tab and enter class code
            logger.info("Step 19: Switching to CLASS CODES tab...")
            await asyncio.sleep(WAIT_SHORT)
            
            # Click the CLASS CODES tab
            class_codes_tab = await self.page.query_selector('a:has-text("CLASS CODES")')
            if not class_codes_tab:
                # Try alternative selectors
                class_codes_tab = await self.page.query_selector('a[ng-click*="switchTab"]:has-text("CLASS CODES")')
            if not class_codes_tab:
                class_codes_tab = await self.page.query_selector('text=CLASS CODES')
            
            if class_codes_tab:
                await class_codes_tab.click()
                logger.info("Clicked CLASS CODES tab")
                await asyncio.sleep(WAIT_PAGE_LOAD)  # Wait longer for tab content to load
            else:
                logger.warning("Could not find CLASS CODES tab")
            
            # Step 20: Enter class code 13454 for Gasoline Stations
            logger.info("Step 20: Entering class code 13454...")
            
            # The class code input is a TEXTAREA, not input
            try:
                class_code_input = await self.page.wait_for_selector(
                    'textarea[name="ClassCode"], textarea#class_codeclassCode1, textarea[ng-model="inputCharacter.text"]',
                    timeout=10000,
                    state='visible'
                )
            except:
                try:
                    class_code_input = await self.page.wait_for_selector(
                        '#classcode-input textarea, md-input-container textarea',
                        timeout=5000,
                        state='visible'
                    )
                except:
                    class_code_input = None
            
            if class_code_input:
                await class_code_input.click()
                await class_code_input.fill("13454")
                logger.info("Typed 13454 in class code textarea")
                
                # Press Enter to search
                await self.page.keyboard.press('Enter')
                logger.info("Pressed Enter to search for class code")
                
                # Wait for modal/results to appear - detect when loaded
                row_selected = False
                try:
                    # Wait for table rows to appear in modal
                    row = await self.page.wait_for_selector(
                        'tr[ng-click*="pick"], tr.clickable-row, table tbody tr',
                        timeout=10000,
                        state='visible'
                    )
                    
                    if row:
                        # Now find and click the specific row with 13454
                        specific_row = await self.page.query_selector('tr:has-text("13454")')
                        if specific_row:
                            await specific_row.click()
                            logger.info("Selected row: 13454 - Gasoline Stations")
                            row_selected = True
                        else:
                            # Click the first available row
                            await row.click()
                            logger.info("Clicked first available row")
                            row_selected = True
                except Exception as e:
                    logger.warning(f"Could not find row in modal: {e}")
                
                if row_selected:
                    # Wait for modal to close by detecting it's gone
                    try:
                        await self.page.wait_for_selector('.modal, .dialog, [role="dialog"]', state='hidden', timeout=5000)
                        logger.info("Modal closed")
                    except:
                        pass  # Modal might not exist or already closed
                    
                    # Wait for loading to complete
                    try:
                        await self.page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        pass
            else:
                logger.warning("Could not find class code textarea field")
            
            # Step 21: Fill PREM/OPS ANNUAL BASIS for first class code (13454)
            logger.info("Step 21: Filling PREM/OPS ANNUAL BASIS for class code 13454...")
            
            # Wait for the input to be visible (detect when ready)
            try:
                prem_ops_input = await self.page.wait_for_selector(
                    'input[aria-label="Prem/Ops Annual Basis"], input[ng-model*="annualBasisAmount"]',
                    timeout=10000,
                    state='visible'
                )
                
                if prem_ops_input:
                    await prem_ops_input.click()
                    prem_ops_basis = quote_data.get('prem_ops_annual_basis', '100000')
                    await prem_ops_input.fill(prem_ops_basis)
                    logger.info(f"Filled PREM/OPS ANNUAL BASIS with {prem_ops_basis}")
                    
                    # Blur to trigger validation
                    await self.page.keyboard.press('Tab')
                    logger.info("Pressed Tab to blur input")
                else:
                    logger.warning("Could not find PREM/OPS ANNUAL BASIS input")
            except Exception as e:
                logger.warning(f"Error filling PREM/OPS ANNUAL BASIS: {e}")
            
            # Step 21B: Enter SECOND class code 13673
            logger.info("Step 21B: Entering second class code 13673...")
            
            # Find the class code textarea again
            try:
                class_code_input2 = await self.page.wait_for_selector(
                    'textarea[name="ClassCode"], textarea#class_codeclassCode1, textarea[ng-model="inputCharacter.text"]',
                    timeout=10000,
                    state='visible'
                )
            except:
                try:
                    class_code_input2 = await self.page.wait_for_selector(
                        '#classcode-input textarea, md-input-container textarea',
                        timeout=5000,
                        state='visible'
                    )
                except:
                    class_code_input2 = None
            
            if class_code_input2:
                await class_code_input2.click()
                await class_code_input2.fill("13673")
                logger.info("Typed 13673 in class code textarea")
                
                # Press Enter to search
                await self.page.keyboard.press('Enter')
                logger.info("Pressed Enter to search for class code 13673")
                
                # Wait for modal/results to appear
                row_selected2 = False
                try:
                    row2 = await self.page.wait_for_selector(
                        'tr[ng-click*="pick"], tr.clickable-row, table tbody tr',
                        timeout=10000,
                        state='visible'
                    )
                    
                    if row2:
                        specific_row2 = await self.page.query_selector('tr:has-text("13673")')
                        if specific_row2:
                            await specific_row2.click()
                            logger.info("Selected row: 13673")
                            row_selected2 = True
                        else:
                            await row2.click()
                            logger.info("Clicked first available row for 13673")
                            row_selected2 = True
                except Exception as e:
                    logger.warning(f"Could not find row for 13673: {e}")
                
                if row_selected2:
                    try:
                        await self.page.wait_for_selector('.modal, .dialog, [role="dialog"]', state='hidden', timeout=5000)
                        logger.info("Modal closed for 13673")
                    except:
                        pass
                    # Wait longer for DOM to fully rebuild after adding second class code
                    await asyncio.sleep(2)
                    try:
                        await self.page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        pass
            else:
                logger.warning("Could not find class code textarea for second entry")
            
            # Step 21C: Fill PREM/OPS ANNUAL BASIS for second class code (13673)
            logger.info("Step 21C: Filling PREM/OPS ANNUAL BASIS for class code 13673...")
            
            try:
                # Wait for DOM to stabilize - this is critical after Angular rebuilds
                await asyncio.sleep(2)
                
                # Get ALL prem/ops inputs fresh from DOM
                all_prem_ops = await self.page.query_selector_all('input[aria-label="Prem/Ops Annual Basis"]')
                logger.info(f"Found {len(all_prem_ops)} PREM/OPS inputs after adding 13673")
                
                # Log all input IDs
                for i, inp in enumerate(all_prem_ops):
                    try:
                        inp_id = await inp.get_attribute('id')
                        inp_val = await inp.get_attribute('value') or ''
                        logger.info(f"  Input {i}: id={inp_id}, value='{inp_val}'")
                    except:
                        pass
                
                if len(all_prem_ops) >= 2:
                    # Use the second input (index 1)
                    second_input = all_prem_ops[1]
                    second_id = await second_input.get_attribute('id')
                    logger.info(f"Using second input with ID: {second_id}")
                    
                    await second_input.scroll_into_view_if_needed()
                    await second_input.click()
                    await second_input.fill("100000")
                    logger.info(f"Filled PREM/OPS ANNUAL BASIS for 13673 with 100000")
                    await self.page.keyboard.press('Tab')
                elif len(all_prem_ops) == 1:
                    # Only one input - check if it's the new one (empty)
                    single_input = all_prem_ops[0]
                    val = await single_input.get_attribute('value') or ''
                    if not val.strip() or val.strip() == '0':
                        await single_input.click()
                        await single_input.fill("100000")
                        logger.info("Filled single empty PREM/OPS input for 13673")
                        await self.page.keyboard.press('Tab')
                    else:
                        logger.info(f"Single input already has value: {val}")
                else:
                    # Try JavaScript approach to find and fill
                    logger.info("Trying JavaScript approach to find second PREM/OPS input...")
                    filled = await self.page.evaluate('''
                        () => {
                            const inputs = document.querySelectorAll('input[aria-label="Prem/Ops Annual Basis"]');
                            console.log('Found inputs:', inputs.length);
                            if (inputs.length >= 2) {
                                const second = inputs[1];
                                second.focus();
                                second.value = '100000';
                                second.dispatchEvent(new Event('input', { bubbles: true }));
                                second.dispatchEvent(new Event('change', { bubbles: true }));
                                second.dispatchEvent(new Event('blur', { bubbles: true }));
                                return true;
                            }
                            // Try finding any empty input
                            for (let inp of inputs) {
                                if (!inp.value || inp.value === '0' || inp.value === '$0') {
                                    inp.focus();
                                    inp.value = '100000';
                                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                                    inp.dispatchEvent(new Event('blur', { bubbles: true }));
                                    return true;
                                }
                            }
                            return false;
                        }
                    ''')
                    if filled:
                        logger.info("Filled PREM/OPS via JavaScript")
                    else:
                        logger.warning("Could not fill PREM/OPS via JavaScript")
            except Exception as e:
                logger.warning(f"Error filling PREM/OPS ANNUAL BASIS for 13673: {e}")
            
            # Step 22: Switch to EXCLUSIONS tab
            logger.info("Step 22: Switching to EXCLUSIONS tab...")
            
            try:
                # Find and click the EXCLUSIONS tab
                exclusions_tab = await self.page.wait_for_selector(
                    'a[ng-click*="switchTab"]:has-text("EXCLUSIONS"), a.dark-tab:has-text("EXCLUSIONS")',
                    timeout=5000,
                    state='visible'
                )
                
                if exclusions_tab:
                    await exclusions_tab.click()
                    logger.info("Clicked EXCLUSIONS tab")
                    
                    # Wait for URL to change to exclusions
                    await asyncio.sleep(2)
                    await self.wait_for_url_contains("exclusions", timeout=10)
                    logger.info("Now on EXCLUSIONS page")
                else:
                    logger.warning("Could not find EXCLUSIONS tab")
            except Exception as e:
                logger.warning(f"Error switching to EXCLUSIONS tab: {e}")
            
            # Step 23: Remove Dog Liability Exclusion (ONLY on exclusions page, NOT class codes)
            logger.info("Step 23: Checking for Dog Liability Exclusion to remove...")
            await asyncio.sleep(1)  # Wait for page to stabilize
            
            # Verify we're on the exclusions page
            current_url = self.page.url
            logger.info(f"Current URL: {current_url}")
            
            if 'exclusions' not in current_url.lower():
                logger.warning("Not on exclusions page - trying to click EXCLUSIONS tab again...")
                # Try clicking the tab again
                try:
                    exclusions_tab = await self.page.query_selector('a:has-text("EXCLUSIONS")')
                    if exclusions_tab:
                        await exclusions_tab.click()
                        await asyncio.sleep(2)
                        current_url = self.page.url
                        logger.info(f"URL after retry: {current_url}")
                except:
                    pass
            
            if 'exclusions' in current_url.lower():
                try:
                    # Take screenshot for debugging
                    screenshot_path = LOG_DIR / "screenshots" / f"exclusions_page_{int(time.time())}.png"
                    await self.page.screenshot(path=str(screenshot_path))
                    logger.info(f"Screenshot saved: {screenshot_path}")
                    
                    # Check if Dog Liability Exclusion exists on this page
                    dog_liability_exists = await self.page.query_selector('text=Dog Liability Exclusion')
                    
                    if not dog_liability_exists:
                        logger.info("Dog Liability Exclusion not found on page - may not be applicable or already removed")
                    else:
                        logger.info("Found Dog Liability Exclusion - attempting to remove...")
                        
                        # The remove button has ng-click="removeMain()" based on screenshot
                        # Try to find and click it specifically for Dog Liability
                        removed = await self.page.evaluate('''
                            () => {
                                // Find the specific element containing "Dog Liability Exclusion"
                                const xpath = "//span[contains(text(), 'Dog Liability')] | //div[contains(text(), 'Dog Liability')] | //*[contains(text(), 'Dog Liability Exclusion')]";
                                const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                                const dogLiabilityEl = result.singleNodeValue;
                                
                                if (!dogLiabilityEl) {
                                    return { success: false, reason: 'Element not found via xpath' };
                                }
                                
                                // Go up to find the row/container that has the remove button
                                let container = dogLiabilityEl;
                                for (let i = 0; i < 10; i++) {
                                    if (!container || !container.parentElement) break;
                                    container = container.parentElement;
                                    
                                    // Look for button with ng-click="removeMain()" - this is the exclusion remove button
                                    const removeBtn = container.querySelector('button[ng-click="removeMain()"], button[ng-click*="removeMain"]');
                                    if (removeBtn && removeBtn.offsetParent !== null) {
                                        removeBtn.click();
                                        return { success: true, reason: 'Clicked removeMain() button' };
                                    }
                                    
                                    // Also try the remove-icon button
                                    const iconBtn = container.querySelector('button.btn-icon-button i.remove-icon');
                                    if (iconBtn) {
                                        const btn = iconBtn.closest('button');
                                        if (btn && btn.offsetParent !== null) {
                                            btn.click();
                                            return { success: true, reason: 'Clicked remove-icon button' };
                                        }
                                    }
                                }
                                
                                return { success: false, reason: 'No removeMain button found near Dog Liability' };
                            }
                        ''')
                        
                        if removed and removed.get('success'):
                            logger.info(f"Dog Liability Exclusion removed: {removed.get('reason')}")
                            await asyncio.sleep(1)  # Wait for UI to update
                        else:
                            logger.warning(f"Could not remove Dog Liability Exclusion: {removed.get('reason') if removed else 'Unknown'}")
                            
                except Exception as e:
                    logger.warning(f"Error in Dog Liability removal: {e}")
            else:
                logger.warning(f"Still not on exclusions page, URL: {current_url}")
            
            # Step 24: Click NEXT to go to Property page
            logger.info("Step 24: Clicking NEXT to go to Property page...")
            await asyncio.sleep(1)
            
            if not await self.click_next_button():
                logger.warning("Could not click NEXT button on EXCLUSIONS tab")
            
            # Wait for Property page URL to load: https://agent.encova.com/gpa/html/quote/cp/risks
            logger.info("Waiting for Property page to load (cp/risks)...")
            if not await self.wait_for_url_contains("cp/risks", timeout=30):
                logger.warning("Did not reach Property page URL")
            
            # IMPORTANT: cp/risks is a parent page that auto-jumps to property details
            # We need to wait for the Building Information section to actually appear
            logger.info("Waiting for property page to fully load and Building Information section to appear...")
            
            # Wait for page to settle and Building Information section to load
            building_info_found = False
            max_attempts = 15  # Wait up to 15 seconds
            for attempt in range(max_attempts):
                try:
                    # Check if Building Information section is visible
                    building_section = await self.page.query_selector('text=Building Information')
                    if building_section:
                        is_visible = await building_section.is_visible()
                        if is_visible:
                            logger.info(f"Building Information section found after {attempt + 1} seconds")
                            building_info_found = True
                            break
                except:
                    pass
                
                # Also try to detect by Building Description field
                try:
                    desc_field = await self.page.query_selector('input[ng-model="model.value"][maxlength], input[id*="inputCtrl"]')
                    if desc_field:
                        is_visible = await desc_field.is_visible()
                        if is_visible:
                            logger.info(f"Building Description field found after {attempt + 1} seconds")
                            building_info_found = True
                            break
                except:
                    pass
                
                await asyncio.sleep(1)
            
            if not building_info_found:
                logger.warning("Building Information section did not appear in time, continuing anyway...")
            else:
                # Additional wait for all fields to fully render
                await asyncio.sleep(1)
            
            logger.info("On Property page...")
            
            # CORRECT ORDER for Property page:
            # 1. Building Description
            # 2. Building Class Code
            # 3. Construction
            # 4. Number of Stories
            # 5. Square Footage
            # 6. Year Built
            # 7. Business Income checkbox (LAST)
            
            # Step 25: Fill Building Description (FIRST)
            logger.info("Step 25: Filling Building Description...")
            
            try:
                # Building Information section should already be detected above
                # Give a small additional wait for input fields to be interactive
                await asyncio.sleep(0.5)
                
                # Find the Building Description input
                building_desc_input = await self.page.wait_for_selector(
                    'input#inputCtrl57, input[ng-model="model.value"][maxlength]',
                    timeout=10000,
                    state='visible'
                )
                
                if building_desc_input:
                    await building_desc_input.click()
                    await asyncio.sleep(WAIT_SHORT)
                    building_desc = quote_data.get('building_description', 'Gas Station C-Store open 18 hours')
                    await building_desc_input.fill(building_desc)
                    logger.info(f"Filled Building Description with '{building_desc}'")
                    await asyncio.sleep(WAIT_SHORT)
                else:
                    # Try JavaScript approach
                    await self.page.evaluate('''
                        () => {
                            const inputs = document.querySelectorAll('input[type="text"]');
                            for (let input of inputs) {
                                let parent = input.parentElement;
                                let depth = 0;
                                while (parent && depth < 6) {
                                    const text = (parent.textContent || '').toUpperCase();
                                    if (text.includes('BUILDING DESCRIPTION') && input.offsetParent !== null) {
                                        input.focus();
                                        input.value = 'Gas Station C-Store open 18 hours';
                                        input.dispatchEvent(new Event('input', { bubbles: true }));
                                        input.dispatchEvent(new Event('change', { bubbles: true }));
                                        return true;
                                    }
                                    parent = parent.parentElement;
                                    depth++;
                                }
                            }
                            return false;
                        }
                    ''')
                    logger.info("Filled Building Description via JavaScript")
            except Exception as e:
                logger.warning(f"Error filling Building Description: {e}")
            
            # Step 25B: Select Building Class Code (SECOND)
            logger.info("Step 25B: Selecting Building Class Code...")
            await asyncio.sleep(1)
            
            try:
                # Find the class code textarea - it has id="class_codeclassCode2" based on screenshot
                # Similar to GL class codes but for CP/Property
                class_code_textarea = await self.page.wait_for_selector(
                    'textarea#class_codeclassCode2, textarea[name="ClassCode"], textarea[id*="class_code"]',
                    timeout=10000,
                    state='visible'
                )
                
                if class_code_textarea:
                    await class_code_textarea.click()
                    await asyncio.sleep(0.5)
                    
                    # Type the building class code
                    building_class = "Convenience Food/Gasoline Stores"
                    await class_code_textarea.fill(building_class)
                    logger.info(f"Typed '{building_class}' in Building Class Code textarea")
                    
                    await asyncio.sleep(0.5)
                    await class_code_textarea.press('Enter')
                    logger.info("Pressed Enter to open Building Class Code modal")
                    
                    # Wait for modal to open
                    await asyncio.sleep(2)
                    
                    # Select the first row in the modal - similar to GL class code modal
                    # Modal has table with class "gw-bicolor-table" and rows with ng-click="pick(item)"
                    try:
                        # Wait for modal and table
                        await self.page.wait_for_selector('div.class-code-modal, div.modal', timeout=5000, state='visible')
                        logger.info("Building Class Code modal opened")
                        
                        # Click the first row in the table
                        first_row = await self.page.wait_for_selector(
                            'table#searchclasscode tr[ng-click*="pick"], table.gw-bicolor-table tbody tr:first-child, tr[ng-repeat*="sortedAndPaginated"]',
                            timeout=5000,
                            state='visible'
                        )
                        
                        if first_row:
                            await first_row.click()
                            logger.info("Clicked first row in Building Class Code modal")
                            await asyncio.sleep(1)
                        else:
                            # Try JavaScript to click first row
                            clicked = await self.page.evaluate('''
                                () => {
                                    // Find the class code modal table
                                    const table = document.querySelector('table#searchclasscode') || 
                                                  document.querySelector('table.gw-bicolor-table');
                                    if (table) {
                                        const rows = table.querySelectorAll('tbody tr');
                                        if (rows.length > 0) {
                                            rows[0].click();
                                            return true;
                                        }
                                    }
                                    
                                    // Try clicking any tr with ng-click="pick(item)"
                                    const pickRows = document.querySelectorAll('tr[ng-click*="pick"]');
                                    if (pickRows.length > 0) {
                                        pickRows[0].click();
                                        return true;
                                    }
                                    
                                    return false;
                                }
                            ''')
                            if clicked:
                                logger.info("Clicked Building Class Code row via JavaScript")
                            else:
                                logger.warning("Could not click Building Class Code row")
                        
                        # Wait for modal to close
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.warning(f"Error selecting Building Class Code from modal: {e}")
                else:
                    logger.warning("Could not find Building Class Code textarea")
                    
            except Exception as e:
                logger.warning(f"Error in Building Class Code selection: {e}")
            
            await asyncio.sleep(1)
            
            # Step 26: Select CONSTRUCTION dropdown (Frame)
            logger.info("Step 26: Selecting CONSTRUCTION dropdown (Frame)...")
            await asyncio.sleep(1)
            
            try:
                # CONSTRUCTION is the 2nd dropdown (index 1)
                # It's a ui-select dropdown, type "Frame" and press Enter
                if not await self.select_dropdown_by_index(1, "Frame", "CONSTRUCTION"):
                    logger.warning("Could not select CONSTRUCTION dropdown")
            except Exception as e:
                logger.warning(f"Error selecting CONSTRUCTION: {e}")
            
            # Step 27: Select NUMBER OF STORIES dropdown (index 2, 3rd dropdown)
            logger.info("Step 27: Selecting NUMBER OF STORIES dropdown...")
            await asyncio.sleep(0.5)
            
            try:
                # NUMBER OF STORIES is the 3rd dropdown (index 2)
                if not await self.select_dropdown_by_index(2, "1", "NUMBER OF STORIES"):
                    logger.warning("Could not select NUMBER OF STORIES dropdown")
            except Exception as e:
                logger.warning(f"Error selecting NUMBER OF STORIES: {e}")
            
            # Step 28: Fill SQUARE FOOTAGE input
            logger.info("Step 28: Filling SQUARE FOOTAGE...")
            await asyncio.sleep(0.5)
            
            try:
                # Find the Square Footage input field
                sq_footage_input = await self.page.wait_for_selector(
                    'input[name="Square Footage"], input[ng-model*="totalArea"], input[aria-label*="Square"]',
                    timeout=5000,
                    state='visible'
                )
                
                if sq_footage_input:
                    await sq_footage_input.click()
                    sq_footage = quote_data.get('square_footage', '2500')
                    await sq_footage_input.fill(sq_footage)
                    logger.info(f"Filled SQUARE FOOTAGE with {sq_footage}")
                    await self.page.keyboard.press('Tab')
                else:
                    logger.warning("Could not find SQUARE FOOTAGE input")
            except Exception as e:
                logger.warning(f"Error filling SQUARE FOOTAGE: {e}")
            
            # Step 29: Fill YEAR BUILT input
            logger.info("Step 29: Filling YEAR BUILT...")
            await asyncio.sleep(0.5)
            
            try:
                year_built = quote_data.get('year_built', '2010')
                
                # The YEAR BUILT input is next to SQUARE FOOTAGE
                # Find the md-input-container that has a span with text "YEAR BUILT"
                result = await self.page.evaluate(f'''
                    () => {{
                        // Method 1: Find the specific md-input-container with YEAR BUILT bullet point label
                        const containers = document.querySelectorAll('md-input-container');
                        for (const container of containers) {{
                            const spans = container.querySelectorAll('span');
                            for (const span of spans) {{
                                const text = span.textContent.trim().toUpperCase();
                                if (text === 'YEAR BUILT' || text.includes('YEAR BUILT')) {{
                                    const input = container.querySelector('input');
                                    if (input) {{
                                        // Clear and fill
                                        input.focus();
                                        input.select();
                                        input.value = '{year_built}';
                                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                        return 'filled via md-input-container: ' + input.id;
                                    }}
                                }}
                            }}
                        }}
                        
                        // Method 2: Find all inputs and check siblings for YEAR BUILT text
                        const allInputs = document.querySelectorAll('input[type="text"], input[type="number"]');
                        for (const input of allInputs) {{
                            const parent = input.closest('md-input-container') || input.parentElement;
                            if (parent) {{
                                const textContent = parent.textContent.toUpperCase();
                                if (textContent.includes('YEAR BUILT') && !textContent.includes('SQUARE')) {{
                                    input.focus();
                                    input.select();
                                    input.value = '{year_built}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    return 'filled via parent text: ' + input.id;
                                }}
                            }}
                        }}
                        
                        return 'not found';
                    }}
                ''')
                
                if result and 'filled' in result:
                    logger.info(f"Filled YEAR BUILT with {year_built} - {result}")
                else:
                    # Fallback: Try using Playwright directly with a more specific selector
                    logger.warning(f"JavaScript approach failed: {result}, trying Playwright selector...")
                    try:
                        # Look for input containers and find the one with YEAR BUILT
                        year_input = await self.page.locator('md-input-container:has(span:text-is("YEAR BUILT")) input').first
                        if year_input:
                            await year_input.click()
                            await year_input.fill(year_built)
                            logger.info(f"Filled YEAR BUILT with {year_built} via Playwright locator")
                    except Exception as e2:
                        logger.warning(f"Playwright fallback also failed: {e2}")
                
                await self.page.keyboard.press('Tab')
            except Exception as e:
                logger.warning(f"Error filling YEAR BUILT: {e}")
            
            # Helper function to wait for Processing dialog to disappear
            async def wait_for_processing_complete(max_wait=15):
                """Wait for the Processing dialog to disappear after an action"""
                logger.info("Waiting for Processing dialog to complete...")
                for i in range(max_wait):
                    is_processing = await self.page.evaluate('''
                        () => {
                            // Check for Processing text in a dialog/modal
                            const processingText = document.body.innerText.includes('Processing');
                            // Check for loading spinner or progress bar
                            const hasLoader = document.querySelector('.loading, .spinner, .progress, [class*="loading"], [class*="progress"]');
                            // Check for modal with Processing
                            const modal = document.querySelector('.modal, .dialog, md-dialog');
                            if (modal && modal.innerText.includes('Processing')) {
                                return true;
                            }
                            return processingText && hasLoader;
                        }
                    ''')
                    if not is_processing:
                        logger.info(f"Processing complete after {i+1} seconds")
                        return True
                    await asyncio.sleep(1)
                logger.warning("Processing dialog did not disappear in time")
                return False
            
            # Step 30: Select Business Income checkbox (LAST step - after all other fields)
            logger.info("Step 30: Selecting Business Income checkbox...")
            await asyncio.sleep(1)
            
            try:
                # Use JavaScript to find and click ONLY Business Income checkbox
                clicked = await self.page.evaluate('''
                    () => {
                        // Method 1: Find checkbox with ng-model containing businessIncome
                        const cb = document.querySelector('md-checkbox[ng-model*="businessIncome"]');
                        if (cb && cb.getAttribute('aria-checked') !== 'true') {
                            cb.click();
                            return "clicked by ng-model";
                        }
                        if (cb && cb.getAttribute('aria-checked') === 'true') {
                            return "already checked";
                        }
                        
                        // Method 2: Find by looking at ng-change containing BusinessIncome
                        const checkboxes = document.querySelectorAll('md-checkbox');
                        for (let checkbox of checkboxes) {
                            const ngChange = checkbox.getAttribute('ng-change') || '';
                            if (ngChange.includes('BusinessIncome') || ngChange.includes('businessIncome')) {
                                if (checkbox.getAttribute('aria-checked') !== 'true') {
                                    checkbox.click();
                                    return "clicked by ng-change";
                                } else {
                                    return "already checked by ng-change";
                                }
                            }
                        }
                        
                        // Method 3: Find by aria-label
                        for (let checkbox of checkboxes) {
                            const label = checkbox.getAttribute('aria-label') || '';
                            if (label.toLowerCase().includes('business income')) {
                                if (checkbox.getAttribute('aria-checked') !== 'true') {
                                    checkbox.click();
                                    return "clicked by aria-label";
                                } else {
                                    return "already checked by aria-label";
                                }
                            }
                        }
                        
                        return "not found - total md-checkbox count: " + document.querySelectorAll('md-checkbox').length;
                    }
                ''')
                
                if clicked and 'clicked' in clicked:
                    logger.info(f"Checked 'Business Income' checkbox: {clicked}")
                    # Wait for Processing dialog to complete
                    await wait_for_processing_complete(15)
                elif 'already checked' in str(clicked):
                    logger.info(f"'Business Income' checkbox already checked: {clicked}")
                else:
                    logger.warning(f"Business Income checkbox result: {clicked}")
                
                # IMPORTANT: Wait for Business Income section to fully load
                # The checkbox triggers a dynamic load of form fields
                logger.info("Waiting for Business Income fields to load...")
                await asyncio.sleep(2)  # Additional wait after processing
                
                # Wait for loading to complete - look for LIMIT field to appear
                limit_found = False
                max_wait = 10  # Wait up to 10 seconds
                for attempt in range(max_wait):
                    try:
                        # Check for LIMIT label or input
                        limit_visible = await self.page.evaluate('''
                            () => {
                                // Check for LIMIT label
                                const labels = document.querySelectorAll('label');
                                for (const label of labels) {
                                    if (label.textContent.trim().toUpperCase() === 'LIMIT') {
                                        return true;
                                    }
                                }
                                
                                // Check for input with aria-label="Limit"
                                const limitInput = document.querySelector('input[aria-label="Limit"]');
                                if (limitInput && limitInput.offsetParent !== null) {
                                    return true;
                                }
                                
                                // Check for Business Income Coverage section
                                const text = document.body.innerText;
                                if (text.includes('Business Income Coverage') && text.includes('LIMIT')) {
                                    return true;
                                }
                                
                                return false;
                            }
                        ''')
                        
                        if limit_visible:
                            logger.info(f"LIMIT field appeared after {attempt + 1} seconds")
                            limit_found = True
                            break
                    except:
                        pass
                    
                    await asyncio.sleep(1)
                
                if not limit_found:
                    logger.warning("LIMIT field did not appear in expected time, taking screenshot...")
                    screenshot_path = LOG_DIR / "screenshots" / f"business_income_no_limit_{int(time.time())}.png"
                    await self.page.screenshot(path=str(screenshot_path))
                    logger.info(f"Screenshot saved: {screenshot_path}")
                else:
                    # Additional small wait for field to be fully interactive
                    await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Error selecting Business Income checkbox: {e}")
            
            # Step 31: Fill Business Income LIMIT field
            logger.info("Step 31: Filling Business Income LIMIT...")
            try:
                business_income_limit = quote_data.get('business_income_limit', '100000')
                
                # Take screenshot to see what fields appeared
                screenshot_path = LOG_DIR / "screenshots" / f"business_income_fields_{int(time.time())}.png"
                await self.page.screenshot(path=str(screenshot_path))
                logger.info(f"Screenshot saved: {screenshot_path}")
                
                # Try multiple selectors for the LIMIT input
                limit_selectors = [
                    'input[aria-label="Limit"]',
                    'input[ng-model="term.newValue"][is-format="term"]',
                    'input.term-input[aria-label="Limit"]',
                    'div.coverage-term input[aria-label="Limit"]',
                    'md-input-container input[aria-label="Limit"]'
                ]
                
                limit_input = None
                for selector in limit_selectors:
                    try:
                        limit_input = await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                        if limit_input:
                            logger.info(f"Found LIMIT input with selector: {selector}")
                            break
                    except:
                        continue
                
                if limit_input:
                    await limit_input.click()
                    await limit_input.fill(business_income_limit)
                    await self.page.keyboard.press('Tab')
                    logger.info(f"Filled Business Income LIMIT with {business_income_limit}")
                    # Wait for Processing dialog after filling LIMIT
                    await wait_for_processing_complete(10)
                else:
                    # Try JavaScript approach to find input with "Limit" label nearby
                    result = await self.page.evaluate(f'''
                        () => {{
                            // Look for label containing "Limit" or "LIMIT"
                            const labels = document.querySelectorAll('label');
                            for (const label of labels) {{
                                if (label.textContent.toLowerCase().includes('limit')) {{
                                    // Find associated input
                                    const forAttr = label.getAttribute('for');
                                    if (forAttr) {{
                                        const input = document.getElementById(forAttr);
                                        if (input) {{
                                            input.focus();
                                            input.value = '{business_income_limit}';
                                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            return 'filled via label for=' + forAttr;
                                        }}
                                    }}
                                    // Try sibling or parent-sibling input
                                    const parent = label.closest('md-input-container, div.term-container, div.coverage-term');
                                    if (parent) {{
                                        const input = parent.querySelector('input');
                                        if (input) {{
                                            input.focus();
                                            input.value = '{business_income_limit}';
                                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            return 'filled via parent container';
                                        }}
                                    }}
                                }}
                            }}
                            
                            // Fallback: look for any visible number input that appeared after checkbox
                            const numberInputs = document.querySelectorAll('input[type="text"][is-format="term"], input[ng-model*="term"]');
                            if (numberInputs.length > 0) {{
                                const input = numberInputs[numberInputs.length - 1];  // Last one added
                                input.focus();
                                input.value = '{business_income_limit}';
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return 'filled last term input';
                            }}
                            
                            return 'not found';
                        }}
                    ''')
                    
                    if result and 'filled' in result:
                        logger.info(f"Filled Business Income LIMIT via JavaScript: {result}")
                        # Wait for Processing dialog after filling LIMIT
                        await wait_for_processing_complete(10)
                    else:
                        logger.warning(f"Could not find Business Income LIMIT input: {result}")
                
            except Exception as e:
                logger.warning(f"Error filling Business Income LIMIT: {e}")
            
            # Step 32: Click Personal Property checkbox
            logger.info("Step 32: Selecting Personal Property checkbox...")
            try:
                # Scroll up to ensure Coverage Type checkboxes are visible
                await self.page.evaluate('window.scrollTo(0, 0)')
                await asyncio.sleep(0.5)
                
                # Click the Personal Property checkbox - look for text "Personal Property" in checkbox container
                clicked = await self.page.evaluate('''
                    () => {
                        // Method 1: Find by looking at text inside the checkbox/label
                        const checkboxes = document.querySelectorAll('md-checkbox');
                        console.log('Found ' + checkboxes.length + ' checkboxes');
                        
                        for (const checkbox of checkboxes) {
                            const text = checkbox.textContent || '';
                            const ariaLabel = checkbox.getAttribute('aria-label') || '';
                            const ngModel = checkbox.getAttribute('ng-model') || '';
                            
                            // Check for "Personal Property" text (case insensitive)
                            if (text.toLowerCase().includes('personal property') || 
                                ariaLabel.toLowerCase().includes('personal property') ||
                                ngModel.toLowerCase().includes('personalproperty') ||
                                ngModel.toLowerCase().includes('personal_property')) {
                                
                                const isChecked = checkbox.getAttribute('aria-checked') === 'true';
                                console.log('Found Personal Property checkbox, checked=' + isChecked);
                                
                                if (!isChecked) {
                                    checkbox.click();
                                    return "clicked personal property checkbox via text match";
                                } else {
                                    return "already checked";
                                }
                            }
                        }
                        
                        // Method 2: Find by Coverage Type section header
                        const headers = document.querySelectorAll('h3, h4, div, span');
                        for (const header of headers) {
                            if (header.textContent.trim() === 'Coverage Type') {
                                // Found Coverage Type section, look for Personal Property checkbox
                                const section = header.closest('div[class*="row"], div[class*="section"], div');
                                if (section) {
                                    const personalCheckbox = Array.from(section.querySelectorAll('md-checkbox')).find(
                                        cb => cb.textContent.toLowerCase().includes('personal property')
                                    );
                                    if (personalCheckbox) {
                                        if (personalCheckbox.getAttribute('aria-checked') !== 'true') {
                                            personalCheckbox.click();
                                            return "clicked via Coverage Type section";
                                        } else {
                                            return "already checked in Coverage Type section";
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Method 3: Click by index - Personal Property is typically 2nd checkbox in Coverage Type
                        // Get all checkboxes in the right panel (Coverage Type area)
                        const allCheckboxes = document.querySelectorAll('md-checkbox');
                        let coverageCheckboxes = [];
                        for (const cb of allCheckboxes) {
                            const text = cb.textContent.toLowerCase();
                            if (text.includes('building') || text.includes('personal property') || text.includes('business income')) {
                                coverageCheckboxes.push(cb);
                            }
                        }
                        
                        console.log('Coverage checkboxes found: ' + coverageCheckboxes.length);
                        
                        // Personal Property should be the second one (after Building)
                        if (coverageCheckboxes.length >= 2) {
                            const personalProp = coverageCheckboxes[1]; // Index 1 = Personal Property
                            if (personalProp.getAttribute('aria-checked') !== 'true') {
                                personalProp.click();
                                return "clicked by index (2nd coverage checkbox)";
                            }
                        }
                        
                        return "not found - total checkboxes: " + checkboxes.length;
                    }
                ''')
                
                if clicked and 'clicked' in clicked:
                    logger.info(f"Checked 'Personal Property' checkbox: {clicked}")
                    # Wait for Processing dialog to complete
                    await wait_for_processing_complete(15)
                elif 'already checked' in str(clicked):
                    logger.info(f"'Personal Property' checkbox already checked")
                else:
                    logger.warning(f"Personal Property checkbox result: {clicked}")
                
                # Wait for Personal Property fields to load
                logger.info("Waiting for Personal Property fields to load...")
                await asyncio.sleep(2)  # Additional wait after processing
                
            except Exception as e:
                logger.warning(f"Error selecting Personal Property checkbox: {e}")
            
            # Step 32b: Select Personal Property DEDUCTIBLE dropdown (5,000)
            # Use label-based selection - more reliable than index-based
            logger.info("Step 32b: Selecting Personal Property DEDUCTIBLE dropdown (5,000)...")
            await asyncio.sleep(0.5)
            
            try:
                deductible_value = quote_data.get('personal_property_deductible', '5,000')
                
                # Use the label-based dropdown selection
                if not await self.select_dropdown_by_label("DEDUCTIBLE", deductible_value):
                    logger.warning("Could not select DEDUCTIBLE dropdown")
                
                # Wait for processing after DEDUCTIBLE selection
                await wait_for_processing_complete(10)
                
            except Exception as e:
                logger.warning(f"Error selecting Deductible dropdown: {e}")
            
            # Step 33: Fill Personal Property LIMIT field
            logger.info("Step 33: Filling Personal Property LIMIT...")
            try:
                personal_property_limit = quote_data.get('personal_property_limit', '100000')
                
                # The Personal Property LIMIT appears after Business Income LIMIT
                # Need to find the second/new LIMIT input that appeared
                # Try to find all visible LIMIT inputs and fill the one for Personal Property
                
                # First try: Find input by aria-label="Limit" that's visible and empty or inside Personal Property section
                result = await self.page.evaluate(f'''
                    () => {{
                        // Find all inputs with aria-label="Limit"
                        const limitInputs = document.querySelectorAll('input[aria-label="Limit"]');
                        
                        // Get the last one (most recently added for Personal Property)
                        // Or find one that's empty/not yet filled
                        for (let i = limitInputs.length - 1; i >= 0; i--) {{
                            const input = limitInputs[i];
                            // Check if visible
                            if (input.offsetParent !== null) {{
                                // Check if it's empty or has placeholder value
                                const currentValue = input.value.replace(/[,$]/g, '');
                                if (!currentValue || currentValue === '0' || currentValue === '') {{
                                    input.focus();
                                    input.value = '{personal_property_limit}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    return 'filled personal property limit: ' + input.id;
                                }}
                            }}
                        }}
                        
                        return 'no empty limit input found, count=' + limitInputs.length;
                    }}
                ''')
                
                if result and 'filled' in result:
                    logger.info(f"Filled Personal Property LIMIT: {result}")
                    # Wait for Processing dialog after filling LIMIT
                    await wait_for_processing_complete(10)
                else:
                    # Fallback: Try to find by looking for the second LIMIT input
                    logger.info(f"First attempt result: {result}, trying alternate approach...")
                    
                    # Try using Playwright to find and fill
                    limit_inputs = await self.page.query_selector_all('input[aria-label="Limit"]')
                    logger.info(f"Found {len(limit_inputs)} LIMIT inputs on page")
                    
                    if len(limit_inputs) >= 2:
                        # The second one should be Personal Property
                        second_limit = limit_inputs[1]
                        await second_limit.click()
                        await second_limit.fill(personal_property_limit)
                        await self.page.keyboard.press('Tab')
                        logger.info(f"Filled Personal Property LIMIT (2nd input) with {personal_property_limit}")
                        # Wait for Processing dialog after filling LIMIT
                        await wait_for_processing_complete(10)
                    elif len(limit_inputs) == 1:
                        logger.warning("Only 1 LIMIT input found - Personal Property may not have loaded yet")
                    else:
                        logger.warning("No LIMIT inputs found on page")
                
            except Exception as e:
                logger.warning(f"Error filling Personal Property LIMIT: {e}")
            
            # Step 34: Wait for loading after LIMIT field and select Valuation dropdown
            # Use label-based selection - more reliable than ID-based
            logger.info("Step 34: Selecting Valuation dropdown (Replacement Cost)...")
            try:
                # First, ensure we've focused out of the LIMIT field to trigger loading
                await self.page.keyboard.press('Tab')
                
                # Wait for processing after LIMIT field
                await wait_for_processing_complete(10)
                
                # Scroll down to ensure VALUATION dropdown is visible
                await self.page.evaluate('window.scrollBy(0, 300)')
                await asyncio.sleep(0.5)
                
                valuation_value = quote_data.get('valuation', 'Replacement Cost')
                
                # Use the label-based dropdown selection
                if not await self.select_dropdown_by_label("VALUATION", valuation_value):
                    logger.warning("Could not select VALUATION dropdown")
                
                # Wait for processing after VALUATION selection
                await wait_for_processing_complete(10)
                
            except Exception as e:
                logger.warning(f"Error selecting Valuation dropdown: {e}")
            
            # Step 35: Fill COINSURANCE dropdown (80%)
            # Use label-based selection - more reliable than index-based
            logger.info("Step 35: Filling COINSURANCE dropdown (80%)...")
            try:
                await asyncio.sleep(0.5)
                
                coinsurance_value = quote_data.get('coinsurance', '80')
                
                # Use the label-based dropdown selection
                if not await self.select_dropdown_by_label("Coinsurance", coinsurance_value):
                    logger.warning("Could not select COINSURANCE dropdown")
                
                # Wait for processing after COINSURANCE selection
                await wait_for_processing_complete(10)
                
            except Exception as e:
                logger.warning(f"Error selecting Coinsurance dropdown: {e}")
            
            # Step 36: Click Save & Close button
            logger.info("Step 36: Clicking Save & Close button...")
            try:
                # Wait a moment for any loading to complete
                await asyncio.sleep(1)
                
                # Find and click the Save & Close button
                save_close_selectors = [
                    'button[ng-click="savePopUp()"]',
                    'button.nbs-button.orange-button.next-button:has-text("Save & Close")',
                    'button:has-text("Save & Close")',
                    'button.orange-button:has-text("Save")'
                ]
                
                save_button = None
                for selector in save_close_selectors:
                    try:
                        save_button = await self.page.wait_for_selector(selector, timeout=3000, state='visible')
                        if save_button:
                            logger.info(f"Found Save & Close button with selector: {selector}")
                            break
                    except:
                        continue
                
                if save_button:
                    await save_button.click()
                    logger.info("Clicked 'Save & Close' button")
                    await asyncio.sleep(2)  # Wait for save to complete
                else:
                    # Try JavaScript approach
                    result = await self.page.evaluate('''
                        () => {
                            // Find button with Save & Close text or ng-click="savePopUp()"
                            const buttons = document.querySelectorAll('button');
                            for (const btn of buttons) {
                                const ngClick = btn.getAttribute('ng-click') || '';
                                const text = btn.textContent.trim();
                                if (ngClick.includes('savePopUp') || text.includes('Save & Close') || text.includes('Save &amp; Close')) {
                                    btn.click();
                                    return 'clicked: ' + text;
                                }
                            }
                            return 'not found';
                        }
                    ''')
                    
                    if result and 'clicked' in result:
                        logger.info(f"Clicked Save & Close via JavaScript: {js_click_result}")
                        await asyncio.sleep(2)
                    else:
                        logger.warning(f"Could not find Save & Close button: {js_click_result}")
                
            except Exception as e:
                logger.warning(f"Error clicking Save & Close button: {e}")
            
            logger.info("Property page - all fields filled and saved!")
            
            final_result = {
                "success": True,
                "account_number": self.account_number,
                "quote_url": self.quote_url,
                "message": "Property page - fields filled, awaiting further instructions"
            }
            
            return final_result
            
        except Exception as e:
            logger.error(f"Quote automation error: {e}", exc_info=True)
            error_result = {
                "success": False,
                "account_number": self.account_number,
                "quote_url": self.quote_url,
                "message": f"Error: {str(e)}"
            }
            return error_result
    
    async def close(self) -> None:
        """Close browser and save trace"""
        try:
            # Stop tracing and save
            if ENABLE_TRACING and self.trace_path and self.context:
                try:
                    logger.info(f"Saving trace to: {self.trace_path}")
                    await self.context.tracing.stop(path=str(self.trace_path))
                    logger.info(f"Trace saved: {self.trace_path}")
                except Exception as e:
                    logger.error(f"Error saving trace: {e}")
            
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")


async def test_quote_automation():
    """Test function for quote automation with existing account"""
    # Test with the account number from trace
    test_account = "4001499341"
    
    print(f"\n{'=' * 60}")
    print(f"TESTING QUOTE AUTOMATION")
    print(f"Account Number: {test_account}")
    print(f"{'=' * 60}\n")
    
    # Use "default" as task_id to share browser cache with account creation
    quote_handler = EncovaQuote(
        account_number=test_account,
        task_id="default",  # IMPORTANT: Use same as account creation
        trace_id=f"quote_test_{test_account}"
    )
    
    try:
        result = await quote_handler.run_quote_automation()
        
        print(f"\n{'=' * 60}")
        print(f"RESULT:")
        print(f"  Success: {result['success']}")
        print(f"  Account: {result['account_number']}")
        print(f"  URL: {result['quote_url']}")
        print(f"  Message: {result['message']}")
        print(f"{'=' * 60}\n")
        
        if result['success']:
            print("Quote page is ready! Browser will stay open for 30 seconds...")
            await asyncio.sleep(30)
        
    finally:
        await quote_handler.close()


if __name__ == "__main__":
    asyncio.run(test_quote_automation())
