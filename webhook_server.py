"""
Webhook server to receive data from Next.js app and trigger Encova automation
Version: 2.1.1 - Browser locking, cleanup scheduler, trace per task (rebuild)
"""
import asyncio
import json
import logging
import threading
import queue
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from encova_login import EncovaLogin
from encova_quote import EncovaQuote
from config import (
    WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_PATH, LOG_DIR, TRACE_DIR, SESSION_DIR,
    ENCOVA_USERNAME, ENCOVA_PASSWORD
)

# Setup logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'webhook_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Enable CORS for Next.js - allow all origins for development
CORS(app, resources={
    r"/*": {
        "origins": "*",  # In production, specify your Next.js domain
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Store active login sessions
active_sessions = {}

# Queue system for managing concurrent requests
task_queue = queue.Queue()
MAX_WORKERS = 3  # Maximum concurrent browser instances
active_workers = 0  # Current number of running workers
worker_lock = threading.Lock()  # Lock for thread-safe worker count
queue_position = {}  # Track queue position for each task

# Browser pool with locking for concurrency safety
# Only ONE browser can use browser_data_default at a time
browser_lock = threading.Lock()  # Lock for browser_data folder access
browser_in_use = False  # Track if browser is currently in use

# Cleanup scheduler configuration
CLEANUP_INTERVAL_HOURS = 6  # Run cleanup every 6 hours
CLEANUP_MAX_AGE_DAYS = 2  # Delete files older than 2 days
MAX_TRACE_FILES = 5  # Keep only last 5 trace files

# Cleanup scheduler thread
cleanup_thread = None
cleanup_stop_event = threading.Event()

# Field mapping: Simple field names -> CSS selectors
FIELD_MAPPING = {
    # Contact Information
    "firstName": 'input[name="contactFirstName"]',
    "lastName": 'input[name="contactLastName"]',
    "companyName": 'input[id="inputCtrl0"]',
    "fein": 'input[id="inputCtrl1"]',
    "description": 'input#inputCtrl2',  # Operations/Description - it's an input, not textarea
    
    # Address Information
    "addressLine1": 'input[ng-model="addressOwner.addressLine1.value"]',
    "addressLine2": 'input[ng-model="addressOwner.addressLine2.value"]',
    "city": 'input[ng-model="addressOwner.city.value"]',
    "county": 'input[ng-model="addressOwner.county.value"]',
    "state": 'input[ng-model="addressOwner.state.value"]',
    "zipCode": 'input[ng-model="addressOwner.postalCode.value"]',
    
    # Contact Details
    "phone": 'input[id="inputCtrl13"]',
    "email": 'input[id="inputCtrl14"]',
    
    # Dropdowns (use focusser IDs)
    "stateDropdown": "focusser-2",
    "addressTypeDropdown": "focusser-3",
    "contactMethodDropdown": "focusser-0",
    "producerDropdown": "focusser-1",
}

# Dropdown value mapping for common values
DROPDOWN_VALUE_MAPPING = {
    "stateDropdown": {
        "GA": "GA",
        "Georgia": "GA",
    },
    "addressTypeDropdown": {
        "Business": "Business",
        "business": "Business",
    },
    "contactMethodDropdown": {
        "Email": "Email",
        "email": "Email",
        "Phone": "Phone",
        "phone": "Phone",
    }
}


def map_form_data(simple_data: dict) -> dict:
    """
    Convert simple field names to CSS selectors
    
    Input: {"firstName": "John", "addressLine1": "280 Griffin"}
    Output: {"input[name=\"contactFirstName\"]": "John", "input[ng-model=\"addressOwner.addressLine1.value\"]": "280 Griffin"}
    """
    mapped_data = {}
    
    for field_name, value in simple_data.items():
        if field_name in FIELD_MAPPING:
            selector = FIELD_MAPPING[field_name]
            mapped_data[selector] = value
            logger.debug(f"Mapped field '{field_name}' -> '{selector}'")
        else:
            # If field name is already a selector, use it as-is
            logger.warning(f"Unknown field name '{field_name}', using as selector")
            mapped_data[field_name] = value
    
    return mapped_data


def map_dropdowns(simple_dropdowns: dict) -> list:
    """
    Convert simple dropdown names to focusser selectors
    
    Input: {"state": "GA", "addressType": "Business"}
    Output: [{"selector": "focusser-2", "value": "GA"}, {"selector": "focusser-3", "value": "Business"}]
    """
    mapped_dropdowns = []
    
    dropdown_mapping = {
        "state": "stateDropdown",
        "stateDropdown": "stateDropdown",
        "addressType": "addressTypeDropdown",
        "addressTypeDropdown": "addressTypeDropdown",
        "contactMethod": "contactMethodDropdown",
        "contactMethodDropdown": "contactMethodDropdown",
        "producer": "producerDropdown",
        "producerDropdown": "producerDropdown",
    }
    
    for dropdown_name, value in simple_dropdowns.items():
        if dropdown_name in dropdown_mapping:
            mapped_name = dropdown_mapping[dropdown_name]
            if mapped_name in FIELD_MAPPING:
                selector = FIELD_MAPPING[mapped_name]
                mapped_dropdowns.append({
                    "selector": selector,
                    "value": value
                })
                logger.debug(f"Mapped dropdown '{dropdown_name}' -> '{selector}' = '{value}'")
        else:
            logger.warning(f"Unknown dropdown name '{dropdown_name}'")
    
    return mapped_dropdowns


def process_quote_data(quote_data: dict) -> dict:
    """
    Process and transform quote data fields according to business logic
    
    Mappings:
    1. dba -> dba (passthrough)
    2. org_type -> org_type (LLC, Corporation, Joint Venture, etc.)
    3. years_at_location -> Calculate year_business_started (current_year - years_at_location)
    4. no_of_gallons_annual -> Map to class_code_13454_premops_annual
    5. inside_sales -> Map to class_code_13673_premops_annual
    6. construction_type -> construction_type (passthrough)
    7. no_of_stories -> num_stories
    8. square_footage -> square_footage (passthrough)
    9. year_built -> If < 2006, add 10 years
    10. limit_business_income -> business_income_limit
    11. limit_personal_property -> personal_property_limit
    """
    from datetime import datetime
    
    processed_data = {}
    current_year = datetime.now().year
    
    # 1. DBA - Direct mapping
    if 'dba' in quote_data:
        processed_data['dba'] = quote_data['dba']
    
    # 2. Organization Type - Direct mapping
    if 'org_type' in quote_data:
        processed_data['org_type'] = quote_data['org_type']
    
    # 3. Years at Location -> Calculate Year Business Started
    if 'years_at_location' in quote_data:
        try:
            years_at_location = int(quote_data['years_at_location'])
            year_business_started = current_year - years_at_location
            processed_data['year_business_started'] = str(year_business_started)
            logger.info(f"Calculated year_business_started: {current_year} - {years_at_location} = {year_business_started}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid years_at_location value: {quote_data['years_at_location']}")
    
    # 4. No of Gallons Annual -> Class Code 13454 PremOps Annual
    if 'no_of_gallons_annual' in quote_data:
        processed_data['class_code_13454_premops_annual'] = quote_data['no_of_gallons_annual']
        logger.info(f"Mapped no_of_gallons_annual to class_code_13454_premops_annual: {quote_data['no_of_gallons_annual']}")
    
    # 5. Inside Sales -> Class Code 13673 PremOps Annual
    if 'inside_sales' in quote_data:
        processed_data['class_code_13673_premops_annual'] = quote_data['inside_sales']
        logger.info(f"Mapped inside_sales to class_code_13673_premops_annual: {quote_data['inside_sales']}")
    
    # 6. Construction Type - Direct mapping
    if 'construction_type' in quote_data:
        processed_data['construction_type'] = quote_data['construction_type']
    
    # 7. No of Stories -> num_stories
    if 'no_of_stories' in quote_data:
        processed_data['num_stories'] = quote_data['no_of_stories']
    
    # 8. Square Footage - Direct mapping
    if 'square_footage' in quote_data:
        processed_data['square_footage'] = quote_data['square_footage']
    
    # 9. Year Built -> If < 2006, add 10 years
    if 'year_built' in quote_data:
        try:
            year_built = int(quote_data['year_built'])
            if year_built < 2006:
                adjusted_year = year_built + 10
                processed_data['year_built'] = str(adjusted_year)
                logger.info(f"Adjusted year_built: {year_built} -> {adjusted_year} (added 10 years because < 2006)")
            else:
                processed_data['year_built'] = str(year_built)
        except (ValueError, TypeError):
            logger.warning(f"Invalid year_built value: {quote_data['year_built']}")
            processed_data['year_built'] = quote_data['year_built']
    
    # 10. Limit Business Income -> business_income_limit
    if 'limit_business_income' in quote_data:
        processed_data['business_income_limit'] = quote_data['limit_business_income']
    
    # 11. Limit Personal Property -> personal_property_limit
    if 'limit_personal_property' in quote_data:
        processed_data['personal_property_limit'] = quote_data['limit_personal_property']
    
    # 12. Building Description (if provided)
    if 'building_description' in quote_data:
        processed_data['building_description'] = quote_data['building_description']
    
    # 13-16. HARDCODED VALUES (always the same, not from input)
    processed_data['personal_property_deductible'] = "5000"
    processed_data['valuation'] = "Replacement Cost"
    processed_data['coinsurance'] = "80%"
    processed_data['building_class_code'] = "Convenience Food/Gasoline Stores"
    
    logger.info("Applied hardcoded values: deductible=5000, valuation=Replacement Cost, coinsurance=80%, building_class=Convenience Food/Gasoline Stores")
    
    logger.info(f"Processed quote_data: {len(quote_data)} fields -> {len(processed_data)} processed fields")
    return processed_data


def update_queue_positions():
    """Update queue positions for all queued tasks"""
    with worker_lock:
        current_workers = active_workers
        queue_size = task_queue.qsize()
    
    # Update positions for tasks in queue
    position = 1
    for task_id in list(queue_position.keys()):
        if task_id in active_sessions:
            if active_sessions[task_id]["status"] == "queued":
                active_sessions[task_id]["queue_position"] = position
                active_sessions[task_id]["active_workers"] = current_workers
                position += 1
            else:
                # Task started, remove from queue tracking
                if task_id in queue_position:
                    del queue_position[task_id]


def cleanup_old_files():
    """
    Cleanup old files to prevent disk space issues:
    - Delete browser_data folders older than CLEANUP_MAX_AGE_DAYS
    - Keep only MAX_TRACE_FILES most recent trace files
    - Delete old log files older than CLEANUP_MAX_AGE_DAYS
    - Delete all screenshot folders (screenshots are disabled)
    """
    logger.info("[CLEANUP] Starting scheduled cleanup...")
    now = time.time()
    max_age_seconds = CLEANUP_MAX_AGE_DAYS * 24 * 60 * 60
    deleted_count = 0
    
    try:
        # 1. Cleanup old browser_data folders (except browser_data_default)
        logger.info("[CLEANUP] Cleaning up old browser_data folders...")
        for folder in SESSION_DIR.glob("browser_data_*"):
            if folder.name == "browser_data_default":
                continue  # Keep the default browser data folder
            try:
                folder_age = now - folder.stat().st_mtime
                if folder_age > max_age_seconds:
                    shutil.rmtree(folder)
                    deleted_count += 1
                    logger.info(f"[CLEANUP] Deleted old browser_data: {folder.name}")
            except Exception as e:
                logger.debug(f"[CLEANUP] Could not delete {folder}: {e}")
        
        # 2. Keep only last MAX_TRACE_FILES trace files
        logger.info("[CLEANUP] Cleaning up old trace files...")
        trace_files = sorted(TRACE_DIR.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
        if len(trace_files) > MAX_TRACE_FILES:
            for trace_file in trace_files[MAX_TRACE_FILES:]:
                try:
                    trace_file.unlink()
                    deleted_count += 1
                    logger.info(f"[CLEANUP] Deleted old trace: {trace_file.name}")
                except Exception as e:
                    logger.debug(f"[CLEANUP] Could not delete trace {trace_file}: {e}")
        
        # 3. Cleanup old log files
        logger.info("[CLEANUP] Cleaning up old log files...")
        for log_file in LOG_DIR.glob("*.log"):
            try:
                file_age = now - log_file.stat().st_mtime
                if file_age > max_age_seconds:
                    log_file.unlink()
                    deleted_count += 1
                    logger.info(f"[CLEANUP] Deleted old log: {log_file.name}")
            except Exception as e:
                logger.debug(f"[CLEANUP] Could not delete log {log_file}: {e}")
        
        # 4. Delete all screenshot folders (screenshots are disabled)
        logger.info("[CLEANUP] Cleaning up screenshot folders...")
        screenshots_dir = LOG_DIR / "screenshots"
        if screenshots_dir.exists():
            for folder in screenshots_dir.iterdir():
                if folder.is_dir():
                    try:
                        shutil.rmtree(folder)
                        deleted_count += 1
                        logger.info(f"[CLEANUP] Deleted screenshot folder: {folder.name}")
                    except Exception as e:
                        logger.debug(f"[CLEANUP] Could not delete screenshot folder {folder}: {e}")
        
        logger.info(f"[CLEANUP] Cleanup completed. Deleted {deleted_count} items.")
        
    except Exception as e:
        logger.error(f"[CLEANUP] Error during cleanup: {e}")


def cleanup_scheduler():
    """Background thread that runs cleanup periodically"""
    logger.info(f"[CLEANUP] Scheduler started - will run every {CLEANUP_INTERVAL_HOURS} hours")
    
    while not cleanup_stop_event.is_set():
        # Wait for interval (check stop event every minute)
        for _ in range(CLEANUP_INTERVAL_HOURS * 60):
            if cleanup_stop_event.is_set():
                break
            time.sleep(60)  # Sleep 1 minute at a time
        
        if not cleanup_stop_event.is_set():
            cleanup_old_files()
    
    logger.info("[CLEANUP] Scheduler stopped")


def worker_thread():
    """
    Worker thread that processes tasks from the queue.
    Uses browser_lock to ensure only ONE task uses browser_data_default at a time.
    """
    global active_workers, browser_in_use
    
    while True:
        try:
            # Get task from queue (blocks until task available)
            task = task_queue.get(timeout=1)
            task_id, data, credentials, trace_id = task
            
            # Update status to "waiting_for_browser"
            if task_id in active_sessions:
                active_sessions[task_id]["status"] = "waiting_for_browser"
                active_sessions[task_id]["picked_at"] = datetime.now().isoformat()
            
            # Acquire browser lock - only ONE browser at a time!
            logger.info(f"[QUEUE] Task {task_id} waiting for browser lock...")
            browser_lock.acquire()
            browser_in_use = True
            
            # NOW increment active workers (only when we have the lock)
            with worker_lock:
                active_workers += 1
                logger.info(f"[QUEUE] Task {task_id} acquired browser lock. Active: {active_workers}/{MAX_WORKERS}")
            
            try:
                # Update task status to running (we have the lock now)
                if task_id in active_sessions:
                    active_sessions[task_id]["status"] = "running"
                    active_sessions[task_id]["queue_position"] = 0
                    active_sessions[task_id]["started_at"] = datetime.now().isoformat()
                
                # Remove from queue position tracking
                if task_id in queue_position:
                    del queue_position[task_id]
                
                logger.info(f"[QUEUE] Processing task {task_id} (trace: {trace_id})")
                
                # Run automation task
                run_automation_task_sync(task_id, data, credentials, trace_id)
                
            except Exception as e:
                logger.error(f"[QUEUE] Error processing task {task_id}: {e}", exc_info=True)
                if task_id in active_sessions:
                    active_sessions[task_id]["status"] = "error"
                    active_sessions[task_id]["error"] = str(e)
            finally:
                # Decrement active workers count BEFORE releasing lock
                with worker_lock:
                    active_workers -= 1
                    logger.info(f"[QUEUE] Task {task_id} finished. Active: {active_workers}/{MAX_WORKERS}")
                
                # Release browser lock
                browser_in_use = False
                browser_lock.release()
                logger.info(f"[QUEUE] Task {task_id} released browser lock")
                
                # Mark task as done in queue
                task_queue.task_done()
                
        except queue.Empty:
            # Timeout - continue loop
            continue
        except Exception as e:
            logger.error(f"[QUEUE] Worker thread error: {e}", exc_info=True)


def log_request_details():
    """Log detailed information about incoming request"""
    try:
        logger.info("=" * 80)
        logger.info(f"REQUEST RECEIVED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Method: {request.method}")
        logger.info(f"URL: {request.url}")
        logger.info(f"Remote Address: {request.remote_addr}")
        logger.info(f"User Agent: {request.headers.get('User-Agent', 'N/A')}")
        logger.info(f"Content Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Log request data
        if request.is_json:
            payload = request.get_json()
            logger.info(f"JSON Payload: {json.dumps(payload, indent=2, default=str)}")
        elif request.form:
            logger.info(f"Form Data: {dict(request.form)}")
        elif request.data:
            logger.info(f"Raw Data: {request.data.decode('utf-8', errors='ignore')[:500]}")
        
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Error logging request details: {e}")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "encova_automation"}), 200


@app.route(WEBHOOK_PATH, methods=['POST', 'OPTIONS'])
def webhook_receiver():
    """
    Webhook endpoint to receive data from Next.js app
    
    Expected payload structure:
    {
        "action": "start_automation",
        "task_id": "optional_unique_id",
        "data": {
            "form_data": {
                "contactFirstName": "John",
                "contactLastName": "Doe",
                ...
            },
            "dropdowns": [
                {"selector": "...", "value": "..."}
            ]
        },
        "credentials": {
            "username": "user@example.com",
            "password": "password123"
        }
    }
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    try:
        # Log request details
        log_request_details()
        
        # Get request data
        if request.is_json:
            payload = request.get_json()
        elif request.form:
            payload = request.form.to_dict()
        else:
            try:
                payload = json.loads(request.data.decode('utf-8'))
            except:
                payload = {}
        
        if not payload:
            logger.warning("Empty payload received")
            return jsonify({
                "status": "error",
                "message": "No payload received"
            }), 400
        
        logger.info(f"Processing webhook request with payload keys: {list(payload.keys())}")
        
        # Extract action and data
        action = payload.get('action', 'start_automation')
        data = payload.get('data', {})
        request_credentials = payload.get('credentials', {})
        
        # Use credentials from request if provided, otherwise use config defaults
        credentials = {
            "username": request_credentials.get('username') or ENCOVA_USERNAME,
            "password": request_credentials.get('password') or ENCOVA_PASSWORD
        }
        
        # Validate credentials
        if not credentials.get('username') or not credentials.get('password'):
            logger.warning("Missing credentials - neither in request nor in config")
            return jsonify({
                "status": "error",
                "message": "Username and password are required. Set them in .env file or provide in request credentials."
            }), 400
        
        # Log which credentials source is being used
        if request_credentials.get('username'):
            logger.info("Using credentials from request")
        else:
            logger.info("Using credentials from config (.env file)")
        
        # Validate required fields
        if action == 'start_automation':
            # Generate or use provided task_id
            task_id = payload.get('task_id') or f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(active_sessions)}"
            
            # Extract company name for trace file naming (before mapping)
            company_name = ""
            if 'form_data' in data and data.get('form_data'):
                company_name = data['form_data'].get('companyName', '')
            
            # Create trace_id with company name for easy identification
            if company_name:
                # Sanitize company name for filename (remove special chars, limit length)
                safe_company = "".join(c if c.isalnum() else "_" for c in company_name)[:30]
                trace_id = f"{safe_company}_{task_id}"
            else:
                trace_id = task_id
            
            # Map simple field names to CSS selectors
            logger.info(f"Mapping form data from simple field names to CSS selectors...")
            if 'form_data' in data and data.get('form_data'):
                original_data = data['form_data'].copy()
                data['form_data'] = map_form_data(data['form_data'])
                logger.info(f"Mapped {len(original_data)} fields: {list(original_data.keys())} -> {list(data['form_data'].keys())[:3]}...")
            
            # Map dropdown names to selectors
            if 'dropdowns' in data and isinstance(data.get('dropdowns'), dict):
                logger.info(f"Mapping dropdowns from simple names to selectors...")
                data['dropdowns'] = map_dropdowns(data['dropdowns'])
                logger.info(f"Mapped {len(data['dropdowns'])} dropdowns")
            
            logger.info(f"Starting automation task: {task_id}")
            logger.info(f"Task data summary: form_fields={len(data.get('form_data', {}))}, dropdowns={len(data.get('dropdowns', []))}")
            
            # Check if we can start immediately or need to queue
            with worker_lock:
                current_workers = active_workers
                queue_size = task_queue.qsize()
            
            # Initialize task status
            active_sessions[task_id] = {
                "status": "queued" if current_workers >= MAX_WORKERS else "running",
                "task_id": task_id,
                "queued_at": datetime.now().isoformat(),
                "data_received": {
                    "form_fields_count": len(data.get('form_data', {})),
                    "dropdowns_count": len(data.get('dropdowns', []))
                },
                "queue_position": queue_size + 1 if current_workers >= MAX_WORKERS else 0,
                "active_workers": current_workers,
                "max_workers": MAX_WORKERS
            }
            
            if current_workers < MAX_WORKERS:
                # Can start immediately - add to queue (worker will pick it up)
                task_queue.put((task_id, data, credentials, trace_id))
                logger.info(f"Task {task_id} added to queue (will start immediately, {current_workers}/{MAX_WORKERS} workers active)")
            else:
                # Need to wait in queue
                task_queue.put((task_id, data, credentials, trace_id))
                queue_position[task_id] = queue_size + 1
                active_sessions[task_id]["queue_position"] = queue_size + 1
                logger.info(f"Task {task_id} queued (position {queue_size + 1}). Active workers: {current_workers}/{MAX_WORKERS}")
            
            # Update queue positions for all queued tasks
            update_queue_positions()
            
            return jsonify({
                "status": "accepted",
                "task_id": task_id,
                "message": "Automation task started",
                "status_url": f"/task/{task_id}/status"
            }), 202
        
        logger.warning(f"Unknown action: {action}")
        return jsonify({
            "status": "error",
            "message": f"Unknown action: {action}. Supported actions: ['start_automation']"
        }), 400
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return jsonify({
            "status": "error",
            "message": f"Invalid JSON: {str(e)}"
        }), 400
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__
        }), 500


def run_automation_task_sync(task_id: str, data: dict, credentials: dict, trace_id: str):
    """
    Run automation task synchronously in a thread
    """
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(run_automation_task(task_id, data, credentials, trace_id))
    finally:
        loop.close()


async def run_automation_task(task_id: str, data: dict, credentials: dict, trace_id: str):
    """
    Run automation task asynchronously
    """
    logger.info(f"[TASK {task_id}] Starting automation task")
    logger.info(f"[TASK {task_id}] Trace file will be: {trace_id}.zip")
    logger.info(f"[TASK {task_id}] Credentials provided: username={credentials.get('username', 'N/A')}")
    logger.info(f"[TASK {task_id}] Data received: {json.dumps(data, indent=2, default=str)}")
    
    login_handler = None
    
    try:
        # Initialize login handler
        username = credentials.get('username')
        password = credentials.get('password')
        
        logger.info(f"[TASK {task_id}] Initializing browser...")
        # Use "default" as task_id for browser_data directory to share cached Angular app
        # This avoids cold cache issues where each task would need to reload Angular from scratch
        # Pass the trace_id (includes company name) for trace file naming
        login_handler = EncovaLogin(
            username=username, 
            password=password, 
            task_id="default",  # Shared browser cache
            trace_id=trace_id   # Trace file with company name
        )
        
        # Run full automation with provided data
        logger.info(f"[TASK {task_id}] Starting full automation...")
        
        # Extract data from payload (already mapped in webhook route)
        form_data = data.get('form_data', {})
        dropdowns = data.get('dropdowns', [])
        save_form = data.get('save_form', True)
        
        logger.info(f"[TASK {task_id}] Form fields: {len(form_data)}, Dropdowns: {len(dropdowns)}")
        
        # Call the single automation method - now returns a dict with detailed results
        automation_result = await login_handler.run_full_automation(
            form_data=form_data,
            dropdowns=dropdowns,
            save_form=save_form
        )
        
        # Extract result details
        success = automation_result.get("success", False)
        account_created = automation_result.get("account_created", False)
        account_number = automation_result.get("account_number")
        quote_url = automation_result.get("quote_url")
        result_message = automation_result.get("message", "")
        
        # Quote automation result
        quote_result = None
        
        if success:
            if account_created and account_number:
                logger.info(f"[TASK {task_id}] 🎉 SUCCESS! New Account Created: {account_number}")
                logger.info(f"[TASK {task_id}] 🔗 Quote URL: {quote_url}")
                
                # Run quote automation if account was created
                run_quote = data.get('run_quote_automation', True)  # Default to True
                if run_quote:
                    logger.info(f"[TASK {task_id}] Starting quote automation for account {account_number}...")
                    
                    # Close login browser first
                    try:
                        await login_handler.close()
                        logger.info(f"[TASK {task_id}] Login browser closed, starting quote automation...")
                    except Exception as e:
                        logger.warning(f"[TASK {task_id}] Error closing login browser: {e}")
                    
                    # Get quote data from payload or use defaults
                    raw_quote_data = data.get('quote_data', {})
                    
                    # Process quote data with business logic transformations
                    quote_data = process_quote_data(raw_quote_data)
                    logger.info(f"[TASK {task_id}] Processed {len(raw_quote_data)} raw quote fields -> {len(quote_data)} processed fields")
                    
                    # Initialize quote handler with same browser data folder
                    quote_handler = EncovaQuote(
                        account_number=account_number,
                        task_id="default",  # Use same browser data folder
                        trace_id=f"quote_{trace_id}" if trace_id else f"quote_{account_number}"
                    )
                    
                    try:
                        quote_result = await quote_handler.run_quote_automation(quote_data=quote_data)
                        
                        if quote_result.get("success"):
                            logger.info(f"[TASK {task_id}] ✅ Quote automation completed!")
                            result_message = f"Account {account_number} created and quote automation completed"
                        else:
                            logger.warning(f"[TASK {task_id}] Quote automation issue: {quote_result.get('message')}")
                            result_message = f"Account {account_number} created, quote automation: {quote_result.get('message')}"
                    except Exception as e:
                        logger.error(f"[TASK {task_id}] Quote automation error: {e}", exc_info=True)
                        quote_result = {"success": False, "message": str(e)}
                    finally:
                        try:
                            await quote_handler.close()
                        except Exception as e:
                            logger.warning(f"[TASK {task_id}] Error closing quote browser: {e}")
                    
                    # Set login_handler to None since we already closed it
                    login_handler = None
            else:
                logger.info(f"[TASK {task_id}] Automation completed: {result_message}")
            
            # Get trace path if tracing is enabled
            trace_path = None
            if login_handler:
                try:
                    if hasattr(login_handler, 'trace_path') and login_handler.trace_path:
                        trace_path = str(login_handler.trace_path)
                        logger.info(f"[TASK {task_id}] Trace file: {trace_path}")
                except Exception as e:
                    logger.debug(f"[TASK {task_id}] Could not get trace path: {e}")
            
            active_sessions[task_id] = {
                "status": "completed",
                "login_handler": login_handler,
                "task_id": task_id,
                "completed_at": datetime.now().isoformat(),
                "fields_filled": len(form_data) if form_data else 0,
                "trace_path": trace_path,
                # New account result fields
                "account_created": account_created,
                "account_number": account_number,
                "quote_url": quote_url,
                "message": result_message,
                # Quote automation result
                "quote_automation": quote_result
            }
            logger.info(f"[TASK {task_id}] Task completed successfully!")
        else:
            logger.error(f"[TASK {task_id}] Automation failed: {result_message}")
            
            active_sessions[task_id] = {
                "status": "failed",
                "error": result_message or "Automation failed",
                "task_id": task_id,
                "failed_at": datetime.now().isoformat(),
                "message": result_message
            }
            
    except Exception as e:
        logger.error(f"[TASK {task_id}] Automation task error: {e}", exc_info=True)
        
        active_sessions[task_id] = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "task_id": task_id,
            "failed_at": datetime.now().isoformat()
        }
    finally:
        # Close browser and update trace info
        if login_handler:
            try:
                logger.info(f"[TASK {task_id}] Closing browser...")
                await login_handler.close()
                logger.info(f"[TASK {task_id}] Browser closed")
                
                # Update trace in active_sessions
                try:
                    trace_path = None
                    if hasattr(login_handler, 'trace_path') and login_handler.trace_path:
                        trace_path = str(login_handler.trace_path)
                    
                    if task_id in active_sessions and trace_path:
                        active_sessions[task_id]["trace_path"] = trace_path
                        logger.info(f"[TASK {task_id}] Trace: {trace_path}")
                except Exception as e:
                    logger.debug(f"[TASK {task_id}] Could not update trace: {e}")
            except Exception as e:
                logger.error(f"[TASK {task_id}] Error closing browser: {e}")


@app.route('/task/<task_id>/status', methods=['GET'])
def get_task_status(task_id: str):
    """Get status of an automation task"""
    logger.info(f"Status check requested for task: {task_id}")
    
    if task_id in active_sessions:
        # Update queue position before returning
        update_queue_positions()
        
        status = active_sessions[task_id].copy()
        # Remove login_handler from response (not JSON serializable)
        status.pop('login_handler', None)
        
        # Add queue info if queued
        if status.get('status') == 'queued':
            with worker_lock:
                status['queue_position'] = status.get('queue_position', 0)
                status['active_workers'] = active_workers
                status['max_workers'] = MAX_WORKERS
                status['estimated_wait_time'] = f"~{status.get('queue_position', 0) * 5} minutes"  # Rough estimate
        
        logger.info(f"Task {task_id} status: {status.get('status')}")
        return jsonify(status), 200
    else:
        logger.warning(f"Task {task_id} not found")
        return jsonify({
            "status": "not_found",
            "message": f"Task {task_id} not found"
        }), 404


@app.route('/tasks', methods=['GET'])
def list_tasks():
    """List all active tasks"""
    tasks = {}
    for task_id, task_data in active_sessions.items():
        task_info = task_data.copy()
        task_info.pop('login_handler', None)  # Remove non-serializable
        tasks[task_id] = task_info
    
    logger.info(f"Listed {len(tasks)} tasks")
    return jsonify({
        "total": len(tasks),
        "tasks": tasks
    }), 200


@app.route('/task/<task_id>', methods=['DELETE'])
def stop_task(task_id: str):
    """Stop and cleanup an automation task"""
    if task_id in active_sessions:
        session = active_sessions[task_id]
        login_handler = session.get('login_handler')
        
        if login_handler:
            # Run close in a thread
            thread = threading.Thread(
                target=lambda: asyncio.run(login_handler.close()),
                daemon=True
            )
            thread.start()
        
        del active_sessions[task_id]
        return jsonify({
            "status": "stopped",
            "message": f"Task {task_id} stopped"
        }), 200
    else:
        return jsonify({
            "status": "not_found",
            "message": f"Task {task_id} not found"
        }), 404


@app.route('/trace/<task_id>', methods=['GET'])
def get_trace(task_id: str):
    """Download trace file for a specific task"""
    try:
        trace_path = TRACE_DIR / f"{task_id}.zip"
        
        if not trace_path.exists():
            logger.warning(f"Trace not found for task: {task_id}")
            return jsonify({
                "status": "not_found",
                "message": f"Trace not found for task {task_id}"
            }), 404
        
        logger.info(f"Serving trace for task {task_id}: {trace_path}")
        return send_file(
            str(trace_path),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{task_id}.zip"
        )
    except Exception as e:
        logger.error(f"Error serving trace for task {task_id}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/traces', methods=['GET'])
def list_traces():
    """List all available trace files - returns HTML UI or JSON"""
    try:
        traces = []
        for trace_file in sorted(TRACE_DIR.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                stat = trace_file.stat()
                traces.append({
                    "task_id": trace_file.stem,
                    "filename": trace_file.name,
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 2),
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "url": f"/trace/{trace_file.stem}"
                })
            except Exception as e:
                logger.debug(f"Error getting info for {trace_file}: {e}")
        
        # Return HTML if browser request, JSON otherwise
        if 'text/html' in request.headers.get('Accept', ''):
            html = '''<!DOCTYPE html>
<html><head><title>Traces</title>
<style>body{font-family:Arial;max-width:800px;margin:40px auto;padding:0 20px}
h1{color:#333}table{width:100%;border-collapse:collapse}
th,td{padding:10px;text-align:left;border-bottom:1px solid #ddd}
a{color:#0066cc;text-decoration:none}a:hover{text-decoration:underline}
.size{color:#666}</style></head>
<body><h1>📁 Trace Files</h1>
<p>Total: ''' + str(len(traces)) + ''' traces (max ''' + str(MAX_TRACE_FILES) + ''')</p>
<table><tr><th>Task ID</th><th>Size</th><th>Created</th><th>Download</th></tr>'''
            for t in traces:
                html += f'''<tr><td>{t["task_id"]}</td><td class="size">{t["size_kb"]} KB</td>
<td>{t["created_at"][:19]}</td><td><a href="{t["url"]}">⬇ Download</a></td></tr>'''
            html += '</table></body></html>'
            return html, 200, {'Content-Type': 'text/html'}
        
        return jsonify({
            "total": len(traces),
            "max_traces": MAX_TRACE_FILES,
            "traces": traces
        }), 200
    except Exception as e:
        logger.error(f"Error listing traces: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/queue/status', methods=['GET'])
def queue_status():
    """Get queue status and statistics"""
    with worker_lock:
        current_workers = active_workers
        queue_size = task_queue.qsize()
    
    # Count tasks by status
    status_counts = {}
    for task_id, task_data in active_sessions.items():
        status = task_data.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return jsonify({
        "browser_in_use": browser_in_use,
        "active_browsers": current_workers,  # Should always be 0 or 1
        "max_workers": MAX_WORKERS,
        "queue_size": queue_size,
        "total_tasks": len(active_sessions),
        "status_breakdown": status_counts,
        "note": "active_browsers should be 0 or 1 (browser lock enforced)"
    }), 200


# Initialize worker threads when module is imported (for gunicorn)
def init_workers():
    """Initialize worker threads for queue system and cleanup scheduler"""
    global cleanup_thread
    
    logger.info("=" * 80)
    logger.info("ENCOVA AUTOMATION WEBHOOK SERVER")
    logger.info("=" * 80)
    logger.info(f"Queue System: {MAX_WORKERS} worker threads (with browser locking)")
    logger.info(f"Browser Lock: Only 1 browser instance at a time to prevent conflicts")
    logger.info(f"Cleanup: Every {CLEANUP_INTERVAL_HOURS}h, delete files older than {CLEANUP_MAX_AGE_DAYS} days")
    logger.info(f"Traces: Keep only last {MAX_TRACE_FILES} trace files")
    logger.info("Starting worker threads...")
    
    # Start worker threads
    for i in range(MAX_WORKERS):
        worker = threading.Thread(target=worker_thread, daemon=True, name=f"Worker-{i+1}")
        worker.start()
        logger.info(f"  Worker {i+1}/{MAX_WORKERS} started")
    
    # Start cleanup scheduler thread
    cleanup_thread = threading.Thread(target=cleanup_scheduler, daemon=True, name="Cleanup-Scheduler")
    cleanup_thread.start()
    logger.info("  Cleanup scheduler started")
    
    # Run initial cleanup on startup
    logger.info("  Running initial cleanup...")
    cleanup_old_files()
    
    logger.info("=" * 80)
    logger.info("Server ready to accept requests from Next.js app...")
    logger.info("=" * 80)

# Initialize workers when module loads (for gunicorn)
init_workers()

if __name__ == '__main__':
    logger.info(f"Starting webhook server on {WEBHOOK_HOST}:{WEBHOOK_PORT}")
    logger.info(f"Webhook endpoint: http://{WEBHOOK_HOST}:{WEBHOOK_PORT}{WEBHOOK_PATH}")
    logger.info(f"Health check: http://{WEBHOOK_HOST}:{WEBHOOK_PORT}/health")
    logger.info(f"Queue status: http://{WEBHOOK_HOST}:{WEBHOOK_PORT}/queue/status")
    logger.info(f"Logs directory: {LOG_DIR}")
    
    app.run(host=WEBHOOK_HOST, port=WEBHOOK_PORT, debug=False)

