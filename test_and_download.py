"""
Test webhook and automatically download screenshots
"""
import requests
import time
import sys
from pathlib import Path
from datetime import datetime
from download_screenshots import download_screenshots

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        import codecs
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        pass  # Continue if encoding fix fails

# Railway webhook URL
WEBHOOK_URL = "https://encova-submission-bot-rpa-production.up.railway.app/webhook"
STATUS_URL = "https://encova-submission-bot-rpa-production.up.railway.app/task/{task_id}/status"
HEALTH_URL = "https://encova-submission-bot-rpa-production.up.railway.app/health"

def test_webhook():
    """Test webhook with Rincon, GA address"""
    print("\n" + "="*60)
    print("TESTING WEBHOOK")
    print("="*60)
    
    # Generate unique task ID
    task_id = f"test_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Test data with Rincon, GA address
    payload = {
        "action": "start_automation",
        "task_id": task_id,
        "data": {
            "form_data": {
                "firstName": "Michael",
                "lastName": "Johnson",
                "companyName": "Rincon Business Solutions",
                "fein": "98-7654321",
                "description": "Retail store with customer service",
                "addressLine1": "332 Saint Andrews Rd",
                "zipCode": "31326",
                "phone": "(912) 555-9876",
                "email": "test.rincon@example.com"
            },
            "dropdowns": {
                "state": "GA",
                "addressType": "Business",
                "contactMethod": "Email"
            },
            "save_form": True
        }
    }
    
    print(f"Task ID: {task_id}")
    print(f"Address: 332 Saint Andrews Rd, Rincon, GA, 31326")
    print("\nSending request to Railway...")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 202:
            print(f"\n[SUCCESS] Task accepted! Task ID: {task_id}")
            return task_id
        else:
            print(f"\n[FAILED] Request failed!")
            print(f"Response: {response.json()}")
            return None
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return None

def wait_for_task_completion(task_id: str, max_wait=300):
    """Wait for task to complete"""
    print("\n" + "="*60)
    print("WAITING FOR TASK COMPLETION")
    print("="*60)
    
    start_time = time.time()
    check_interval = 5
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(
                STATUS_URL.format(task_id=task_id),
                timeout=10
            )
            
            if response.status_code == 200:
                status = response.json()
                current_status = status.get('status')
                elapsed = int(time.time() - start_time)
                
                print(f"[{elapsed}s] Status: {current_status}")
                
                if current_status in ['completed', 'failed', 'error']:
                    print(f"\n[COMPLETE] Task finished with status: {current_status}")
                    
                    # Show screenshot count
                    screenshot_count = status.get('screenshot_count', 0)
                    print(f"Screenshots available: {screenshot_count}")
                    
                    return status
            else:
                print(f"Status check failed: {response.status_code}")
                
        except Exception as e:
            print(f"Error checking status: {e}")
        
        time.sleep(check_interval)
    
    print(f"\n[TIMEOUT] Timeout after {max_wait} seconds")
    return None

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TEST AND DOWNLOAD SCREENSHOTS")
    print("="*60)
    print(f"Testing: {WEBHOOK_URL}\n")
    
    # Step 1: Test webhook
    task_id = test_webhook()
    
    if not task_id:
        print("\n[ERROR] Failed to start task. Exiting.")
        sys.exit(1)
    
    # Step 2: Wait for completion
    status = wait_for_task_completion(task_id, max_wait=300)
    
    if not status:
        print("\n[WARNING] Task did not complete in time, but will try to download screenshots anyway...")
    
    # Step 3: Download screenshots
    print("\n" + "="*60)
    print("DOWNLOADING SCREENSHOTS")
    print("="*60)
    
    # Wait a bit for screenshots to be finalized
    print("Waiting 5 seconds for screenshots to be finalized...")
    time.sleep(5)
    
    success = download_screenshots(task_id)
    
    if success:
        print(f"\n[SUCCESS] Screenshots downloaded to: debug_screenshots/{task_id}/")
    else:
        print(f"\n[WARNING] Failed to download screenshots or no screenshots available")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

