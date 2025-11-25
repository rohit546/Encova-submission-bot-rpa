"""
Test automation and automatically download trace file
"""
import requests
import time
import sys
import os
from pathlib import Path
from download_trace import download_trace, DEBUG_DIR

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

WEBHOOK_URL = "https://encova-submission-bot-rpa-production.up.railway.app/webhook"

def test_and_download_trace():
    """Send a test request, wait for completion, then download trace"""
    print("=" * 80)
    print("TEST AUTOMATION AND DOWNLOAD TRACE")
    print("=" * 80)
    
    # Test data
    task_id = f"test_trace_{int(time.time())}"
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
    
    print(f"\n📤 Sending request to: {WEBHOOK_URL}")
    print(f"📋 Task ID: {task_id}")
    print(f"📝 Address: 332 Saint Andrews Rd, Rincon, GA, 31326, USA")
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        print(f"\n✅ Request accepted: {result.get('message', 'OK')}")
        print(f"📊 Status: {result.get('status', 'unknown')}")
    except Exception as e:
        print(f"\n❌ Error sending request: {e}")
        return
    
    # Monitor task status
    status_url = f"https://encova-submission-bot-rpa-production.up.railway.app/task/{task_id}/status"
    print(f"\n⏳ Monitoring task status...")
    print(f"🔗 Status URL: {status_url}")
    
    max_wait = 300  # 5 minutes
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(status_url, timeout=10)
            if response.status_code == 200:
                status = response.json()
                current_status = status.get('status', 'unknown')
                
                if current_status != last_status:
                    print(f"\n📊 Status: {current_status}")
                    last_status = current_status
                
                if current_status in ['completed', 'failed']:
                    print(f"\n{'=' * 80}")
                    print(f"✅ Task {current_status.upper()}")
                    print(f"{'=' * 80}")
                    
                    # Download trace
                    print(f"\n⬇️  Downloading trace file...")
                    if download_trace(task_id):
                        print(f"\n✅ Trace downloaded successfully!")
                        print(f"📁 Location: {DEBUG_DIR / f'{task_id}.zip'}")
                    else:
                        print(f"\n⚠️  Could not download trace file")
                        print(f"   Check if tracing is enabled and task completed")
                    
                    break
            else:
                print(f"⚠️  Status check returned: {response.status_code}")
        except Exception as e:
            print(f"⚠️  Error checking status: {e}")
        
        time.sleep(5)
    
    if time.time() - start_time >= max_wait:
        print(f"\n⏱️  Timeout waiting for task completion")
        print(f"   You can still try to download the trace manually:")
        print(f"   python download_trace.py {task_id}")
    
    print(f"\n{'=' * 80}")

if __name__ == "__main__":
    test_and_download_trace()

