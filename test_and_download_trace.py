"""
Test automation and automatically download trace file
Works with both local and Railway deployment
"""
import requests
import time
import sys
import os
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Configuration - change this to switch between local and Railway
USE_LOCAL = False  # Set to True to test locally, False for Railway

if USE_LOCAL:
    BASE_URL = "http://localhost:5000"
else:
    BASE_URL = "https://encova-submission-bot-rpa-production.up.railway.app"

WEBHOOK_URL = f"{BASE_URL}/webhook"
# Save traces to the main traces directory (same as where Encova saves them)
TRACES_DIR = Path(__file__).parent / "traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)


def download_trace(task_id: str, trace_type: str = "") -> bool:
    """
    Download trace file for a specific task
    Args:
        task_id: Task identifier
        trace_type: Optional prefix for trace file (e.g., "login", "quote")
    """
    trace_url = f"{BASE_URL}/trace/{task_id}"
    print(f"\n[DOWNLOAD] Fetching {trace_type} trace from: {trace_url}")
    
    try:
        response = requests.get(trace_url, timeout=30)
        if response.status_code == 200:
            # Save with descriptive name
            filename = f"{trace_type}_{task_id}.zip" if trace_type else f"{task_id}.zip"
            trace_path = TRACES_DIR / filename
            trace_path.write_bytes(response.content)
            print(f"[OK] {trace_type.capitalize()} trace saved to: {trace_path}")
            print(f"[VIEW] Run: playwright show-trace {trace_path}")
            return True
        elif response.status_code == 404:
            print(f"[INFO] {trace_type.capitalize()} trace not found for task {task_id}")
            return False
        else:
            print(f"[ERROR] Server returned: {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        return False


def download_both_traces(task_id: str) -> None:
    """
    Download both login and quote traces for a task
    The server creates two trace files:
    - {task_id}.zip (login automation)
    - quote_{task_id}.zip (quote automation)
    """
    print(f"\n{'=' * 80}")
    print("[DOWNLOADING TRACES]")
    print(f"{'=' * 80}")
    
    # Download login trace
    login_success = download_trace(task_id, "login")
    
    # Download quote trace (has "quote_" prefix)
    quote_task_id = f"quote_{task_id}"
    quote_success = download_trace(quote_task_id, "quote")
    
    if login_success and quote_success:
        print(f"\n[SUCCESS] Both traces downloaded successfully!")
    elif login_success or quote_success:
        print(f"\n[PARTIAL] Some traces downloaded successfully")
    else:
        print(f"\n[WARNING] No traces were downloaded")


def test_and_download_trace():
    """Send a test request, wait for completion, then download trace"""
    print("=" * 80)
    print("TEST AUTOMATION AND DOWNLOAD TRACE")
    print("=" * 80)
    print(f"\n[SERVER] {BASE_URL}")
    print(f"[MODE] {'LOCAL' if USE_LOCAL else 'RAILWAY'}")
    
    # Test data - with new quote automation fields
    task_id = f"test_trace_{int(time.time())}"
    payload = {
        "action": "start_automation",
        "task_id": task_id,
        "data": {
            "form_data": {
                "firstName": "Marcus",
                "lastName": "Johnson",
                "companyName": "White Bluff Fuel & Mart LLC",
                "fein": "47-2856391",
                "description": "Gas station and convenience store with retail fuel operations",
                "addressLine1": "12403 White Bluff Rd",
                "zipCode": "31419",
                "phone": "(912) 555-2234",
                "email": "marcus.johnson@whitebluffmart.com"
            },
            "dropdowns": {
                "state": "GA",
                "addressType": "Business",
                "contactMethod": "Email",
                "producer": "Shahnaz Sutar"
            },
            "save_form": True,
            "run_quote_automation": True,  # Run quote automation after account creation
            "quote_data": {
                # INPUT FIELDS - will be processed by process_quote_data()
                "dba": "White Bluff Fuel & Mart",
                "org_type": "LLC",
                "years_at_location": "4",  # Will calculate: 2026 - 4 = 2022
                "no_of_gallons_annual": "620000",  # Maps to class_code_13454_premops_annual
                "inside_sales": "225000",  # Maps to class_code_13673_premops_annual
                "construction_type": "Masonry Non-Combustible",
                "no_of_stories": "1",
                "square_footage": "3200",
                "year_built": "2005",  # < 2006, will be adjusted to 2015
                "limit_business_income": "400000",
                "limit_personal_property": "250000",
                "building_description": "Modern gas station with convenience store and automotive services"
                
                # HARDCODED (automatically added by webhook):
                # - building_class_code: "Convenience Food/Gasoline Stores"
                # - personal_property_deductible: "5000"
                # - valuation: "Replacement Cost"
                # - coinsurance: "80%"
            }
        }
    }
    
    print(f"\n[REQUEST] Sending to: {WEBHOOK_URL}")
    print(f"[TASK ID] {task_id}")
    print(f"[DATA] Company: White Bluff Fuel & Mart LLC")
    print(f"[DATA] Address: 12403 White Bluff Rd, Savannah, GA 31419")
    print(f"[QUOTE] Running both login and quote automation")
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        print(f"\n[OK] Request accepted: {result.get('message', 'OK')}")
        print(f"[STATUS] {result.get('status', 'unknown')}")
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to server!")
        if USE_LOCAL:
            print(f"[INFO] Make sure webhook_server.py is running:")
            print(f"       python webhook_server.py")
        else:
            print(f"[INFO] Check if Railway deployment is running")
        return
    except Exception as e:
        print(f"\n[ERROR] Failed to send request: {e}")
        return
    
    # Monitor task status
    status_url = f"{BASE_URL}/task/{task_id}/status"
    print(f"\n[MONITOR] Checking task status...")
    print(f"[URL] {status_url}")
    
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
                    print(f"\n[STATUS] {current_status.upper()}")
                    
                    # Show queue/browser info if available
                    if status.get('queue_position'):
                        print(f"[QUEUE] Position: {status['queue_position']}")
                    if 'active_browsers' in status:
                        print(f"[BROWSERS] Active: {status['active_browsers']}")
                    
                    last_status = current_status
                
                # Check if task is complete
                if current_status in ['completed', 'success']:
                    print(f"\n{'=' * 80}")
                    print(f"[SUCCESS] Task completed successfully!")
                    print(f"{'=' * 80}")
                    
                    # Show account creation result
                    if status.get('account_created'):
                        print(f"\n🎉 NEW ACCOUNT CREATED!")
                        print(f"   Account Number: {status.get('account_number')}")
                        print(f"   Quote URL: {status.get('quote_url')}")
                    
                    # Show quote automation result
                    if status.get('quote_automation'):
                        quote_result = status['quote_automation']
                        if quote_result.get('success'):
                            print(f"\n✅ QUOTE AUTOMATION COMPLETED!")
                            print(f"   Message: {quote_result.get('message', 'Success')}")
                        else:
                            print(f"\n⚠️ QUOTE AUTOMATION ISSUE:")
                            print(f"   Message: {quote_result.get('message', 'Unknown error')}")
                    
                    # Download both login and quote traces
                    download_both_traces(task_id)
                    break
                    
                elif current_status in ['failed', 'error']:
                    print(f"\n{'=' * 80}")
                    print(f"[FAILED] Task failed!")
                    print(f"{'=' * 80}")
                    if status.get('error'):
                        print(f"[ERROR] {status['error']}")
                    
                    # Still try to download traces for debugging
                    print(f"\n[INFO] Attempting to download traces for debugging...")
                    download_both_traces(task_id)
                    break
                    
            elif response.status_code == 404:
                print(f"[INFO] Task not found (may not have started yet)")
            else:
                print(f"[WARNING] Status check returned: {response.status_code}")
        except Exception as e:
            print(f"[WARNING] Error checking status: {e}")
        
        # Wait before next check
        time.sleep(3)
    
    if time.time() - start_time >= max_wait:
        print(f"\n[TIMEOUT] Task did not complete within {max_wait} seconds")
        print(f"[INFO] Task may still be running. Check status manually:")
        print(f"       {status_url}")
        print(f"\n[INFO] You can try to download the trace manually:")
        print(f"       python download_latest_trace.py {task_id}")
    
    print(f"\n{'=' * 80}")
    print("[DONE]")
    print("=" * 80)


def check_server_health():
    """Check if the server is running"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"[OK] Server is running at {BASE_URL}")
            return True
        else:
            print(f"[WARNING] Server responded with status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Could not connect to server!")
        if USE_LOCAL:
            print("[INFO] Start it with: python webhook_server.py")
        return False
    except Exception as e:
        print(f"[ERROR] Could not check server health: {e}")
        return False


if __name__ == "__main__":
    print("\n[CHECK] Testing server health...")
    if check_server_health():
        print("\n" + "=" * 80)
        test_and_download_trace()
    else:
        print("\n[ABORT] Cannot proceed without server running")
        sys.exit(1)

