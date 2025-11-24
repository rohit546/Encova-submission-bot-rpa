"""
Webhook server to receive data from Next.js app and trigger Encova automation
"""
import asyncio
import json
import logging
import threading
import queue
from datetime import datetime
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from encova_login import EncovaLogin
from config import (
    WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_PATH, LOG_DIR,
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

# Field mapping: Simple field names -> CSS selectors
FIELD_MAPPING = {
    # Contact Information
    "firstName": 'input[name="contactFirstName"]',
    "lastName": 'input[name="contactLastName"]',
    "companyName": 'input[id="inputCtrl0"]',
    "fein": 'input[id="inputCtrl1"]',
    "description": 'input[ng-model="model.value"][ng-trim="true"]',
    
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


def worker_thread():
    """
    Worker thread that processes tasks from the queue
    """
    global active_workers
    
    while True:
        try:
            # Get task from queue (blocks until task available)
            task = task_queue.get(timeout=1)
            task_id, data, credentials = task
            
            # Increment active workers count
            with worker_lock:
                active_workers += 1
                logger.info(f"[QUEUE] Worker started. Active workers: {active_workers}/{MAX_WORKERS}")
            
            try:
                # Update task status
                if task_id in active_sessions:
                    active_sessions[task_id]["status"] = "running"
                    active_sessions[task_id]["queue_position"] = 0
                    active_sessions[task_id]["started_at"] = datetime.now().isoformat()
                
                # Remove from queue position tracking
                if task_id in queue_position:
                    del queue_position[task_id]
                
                logger.info(f"[QUEUE] Processing task {task_id} (was in queue)")
                
                # Run automation task
                run_automation_task_sync(task_id, data, credentials)
                
            except Exception as e:
                logger.error(f"[QUEUE] Error processing task {task_id}: {e}", exc_info=True)
                if task_id in active_sessions:
                    active_sessions[task_id]["status"] = "error"
                    active_sessions[task_id]["error"] = str(e)
            finally:
                # Decrement active workers count
                with worker_lock:
                    active_workers -= 1
                    logger.info(f"[QUEUE] Worker finished. Active workers: {active_workers}/{MAX_WORKERS}")
                
                # Mark task as done
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
                task_queue.put((task_id, data, credentials))
                logger.info(f"Task {task_id} added to queue (will start immediately, {current_workers}/{MAX_WORKERS} workers active)")
            else:
                # Need to wait in queue
                task_queue.put((task_id, data, credentials))
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


def run_automation_task_sync(task_id: str, data: dict, credentials: dict):
    """
    Run automation task synchronously in a thread
    """
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(run_automation_task(task_id, data, credentials))
    finally:
        loop.close()


async def run_automation_task(task_id: str, data: dict, credentials: dict):
    """
    Run automation task asynchronously
    """
    logger.info(f"[TASK {task_id}] Starting automation task")
    logger.info(f"[TASK {task_id}] Credentials provided: username={credentials.get('username', 'N/A')}")
    logger.info(f"[TASK {task_id}] Data received: {json.dumps(data, indent=2, default=str)}")
    
    login_handler = None
    
    try:
        # Initialize login handler
        username = credentials.get('username')
        password = credentials.get('password')
        
        logger.info(f"[TASK {task_id}] Initializing browser...")
        login_handler = EncovaLogin(username=username, password=password, task_id=task_id)
        
        # Perform login
        logger.info(f"[TASK {task_id}] Attempting login...")
        success = await login_handler.login()
        
        if success:
            logger.info(f"[TASK {task_id}] Login successful!")
            page = await login_handler.get_page()
            
            # Navigate to form
            logger.info(f"[TASK {task_id}] Navigating to form...")
            await login_handler.navigate_to_new_quote_search()
            
            # Process the received data and fill form
            logger.info(f"[TASK {task_id}] Processing form data...")
            
            filled_count = 0
            
            # Fill form if form_data is provided in the payload
            if 'form_data' in data and data.get('form_data'):
                form_data = data.get('form_data', {})
                logger.info(f"[TASK {task_id}] Filling {len(form_data)} form fields...")
                
                for field_selector, value in form_data.items():
                    try:
                        success = await login_handler._fill_field(field_selector, value)
                        if success:
                            filled_count += 1
                            logger.info(f"[TASK {task_id}] Filled field: {field_selector}")
                        else:
                            logger.warning(f"[TASK {task_id}] Failed to fill field: {field_selector}")
                    except Exception as e:
                        logger.error(f"[TASK {task_id}] Error filling {field_selector}: {e}")
                
                logger.info(f"[TASK {task_id}] Filled {filled_count}/{len(form_data)} fields")
            
            # Handle dropdowns if provided
            if 'dropdowns' in data and data.get('dropdowns'):
                dropdowns = data.get('dropdowns', [])
                logger.info(f"[TASK {task_id}] Processing {len(dropdowns)} dropdowns...")
                
                for i, dropdown in enumerate(dropdowns):
                    selector = dropdown.get('selector')
                    value = dropdown.get('value')
                    if selector and value:
                        try:
                            await login_handler.select_dropdown(selector, value)
                            logger.info(f"[TASK {task_id}] Filled dropdown {i+1}/{len(dropdowns)}: {selector} = {value}")
                        except Exception as e:
                            logger.error(f"[TASK {task_id}] Error filling dropdown {selector}: {e}")
            
            # Click save button if requested
            if data.get('save_form', True):
                logger.info(f"[TASK {task_id}] Clicking Save & Close button...")
                save_success = await login_handler.click_save_and_close_button()
                if save_success:
                    logger.info(f"[TASK {task_id}] Form saved successfully!")
                else:
                    logger.warning(f"[TASK {task_id}] Failed to save form")
            
            # Get video path if available
            video_path = None
            if login_handler:
                try:
                    video_path = str(login_handler.get_video_path())
                    logger.info(f"[TASK {task_id}] Video recorded: {video_path}")
                except Exception as e:
                    logger.debug(f"[TASK {task_id}] Could not get video path: {e}")
            
            active_sessions[task_id] = {
                "status": "completed",
                "login_handler": login_handler,
                "task_id": task_id,
                "completed_at": datetime.now().isoformat(),
                "fields_filled": filled_count if 'form_data' in data else 0,
                "video_path": video_path
            }
            logger.info(f"[TASK {task_id}] Task completed successfully!")
        else:
            logger.error(f"[TASK {task_id}] Login failed!")
            
            # Get video path even if login failed
            video_path = None
            if login_handler:
                try:
                    video_path = str(login_handler.get_video_path())
                    logger.info(f"[TASK {task_id}] Video recorded (login failed): {video_path}")
                except Exception as e:
                    logger.debug(f"[TASK {task_id}] Could not get video path: {e}")
            
            active_sessions[task_id] = {
                "status": "failed",
                "error": "Login failed",
                "task_id": task_id,
                "failed_at": datetime.now().isoformat(),
                "video_path": video_path
            }
            
    except Exception as e:
        logger.error(f"[TASK {task_id}] Automation task error: {e}", exc_info=True)
        
        # Get video path even if task failed
        video_path = None
        if login_handler:
            try:
                video_path = str(login_handler.get_video_path())
                logger.info(f"[TASK {task_id}] Video recorded (task failed): {video_path}")
            except Exception as e:
                logger.debug(f"[TASK {task_id}] Could not get video path: {e}")
        
        active_sessions[task_id] = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "task_id": task_id,
            "failed_at": datetime.now().isoformat(),
            "video_path": video_path
        }
    finally:
        # Close browser to finalize video recording
        if login_handler:
            try:
                logger.info(f"[TASK {task_id}] Closing browser to finalize video...")
                await login_handler.close()
                logger.info(f"[TASK {task_id}] Browser closed, video should be finalized")
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


@app.route('/video/<task_id>', methods=['GET'])
def get_video(task_id: str):
    """Download video for a specific task"""
    try:
        from pathlib import Path
        video_dir = LOG_DIR / "videos"
        video_path = video_dir / f"{task_id}.webm"
        
        if not video_path.exists():
            logger.warning(f"Video not found for task: {task_id}")
            return jsonify({
                "status": "not_found",
                "message": f"Video not found for task {task_id}"
            }), 404
        
        logger.info(f"Serving video for task {task_id}: {video_path}")
        return send_file(
            str(video_path),
            mimetype='video/webm',
            as_attachment=True,
            download_name=f"{task_id}.webm"
        )
    except Exception as e:
        logger.error(f"Error serving video for task {task_id}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/videos', methods=['GET'])
def list_videos():
    """List all available videos"""
    try:
        from pathlib import Path
        import os
        from datetime import datetime
        
        video_dir = LOG_DIR / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        
        videos = []
        for video_file in video_dir.glob("*.webm"):
            try:
                stat = video_file.stat()
                videos.append({
                    "task_id": video_file.stem,
                    "filename": video_file.name,
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "download_url": f"/video/{video_file.stem}"
                })
            except Exception as e:
                logger.debug(f"Error getting info for {video_file}: {e}")
        
        # Sort by creation time (newest first)
        videos.sort(key=lambda x: x['created_at'], reverse=True)
        
        return jsonify({
            "total": len(videos),
            "videos": videos
        }), 200
    except Exception as e:
        logger.error(f"Error listing videos: {e}", exc_info=True)
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
        "active_workers": current_workers,
        "max_workers": MAX_WORKERS,
        "queue_size": queue_size,
        "total_tasks": len(active_sessions),
        "status_breakdown": status_counts,
        "available_workers": MAX_WORKERS - current_workers
    }), 200


# Initialize worker threads when module is imported (for gunicorn)
def init_workers():
    """Initialize worker threads for queue system"""
    logger.info("=" * 80)
    logger.info("ENCOVA AUTOMATION WEBHOOK SERVER")
    logger.info("=" * 80)
    logger.info(f"Queue System: {MAX_WORKERS} worker threads")
    logger.info("Starting worker threads...")
    
    # Start worker threads
    for i in range(MAX_WORKERS):
        worker = threading.Thread(target=worker_thread, daemon=True, name=f"Worker-{i+1}")
        worker.start()
        logger.info(f"  Worker {i+1}/{MAX_WORKERS} started")
    
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

