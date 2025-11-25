"""
Test script to trigger automation with tracing enabled
"""
import requests
import time
import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

WEBHOOK_URL = "https://encova-submission-bot-rpa-production.up.railway.app/webhook"

def test_trace():
    """Send a test request and monitor trace file"""
    print("=" * 80)
    print("PLAYWRIGHT TRACE TEST")
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
                    print(f"\n📊 Status changed: {current_status}")
                    last_status = current_status
                
                if current_status in ['completed', 'failed']:
                    print(f"\n{'=' * 80}")
                    print(f"✅ Task {current_status.upper()}")
                    print(f"{'=' * 80}")
                    
                    # Show trace info
                    trace_path = status.get('trace_path')
                    trace_url = status.get('trace_url')
                    
                    if trace_path or trace_url:
                        print(f"\n📦 TRACE FILE INFORMATION:")
                        if trace_path:
                            print(f"   📁 Path: {trace_path}")
                        if trace_url:
                            print(f"   🔗 Download URL: {trace_url}")
                            print(f"\n💡 To view the trace:")
                            print(f"   1. Download: {trace_url}")
                            print(f"   2. Install Playwright: pip install playwright")
                            print(f"   3. View trace: playwright show-trace <downloaded_file.zip>")
                    else:
                        print(f"\n⚠️  No trace file found (tracing may be disabled)")
                    
                    # Show screenshots
                    screenshots = status.get('screenshots', [])
                    screenshot_count = status.get('screenshot_count', 0)
                    if screenshot_count > 0:
                        print(f"\n📸 Screenshots: {screenshot_count} taken")
                        screenshot_urls = status.get('screenshot_urls', [])
                        if screenshot_urls:
                            print(f"   🔗 Download URLs:")
                            for ss in screenshot_urls[:3]:  # Show first 3
                                print(f"      - {ss.get('url')}")
                    
                    break
            else:
                print(f"⚠️  Status check returned: {response.status_code}")
        except Exception as e:
            print(f"⚠️  Error checking status: {e}")
        
        time.sleep(5)
    
    if time.time() - start_time >= max_wait:
        print(f"\n⏱️  Timeout waiting for task completion")
    
    print(f"\n{'=' * 80}")

if __name__ == "__main__":
    test_trace()

