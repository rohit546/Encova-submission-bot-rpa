"""
Test local webhook server - sends data to localhost:5000
Run webhook_server.py first, then run this test

NEW QUOTE DATA PROCESSING (process_quote_data function):
================================================
INPUT FIELDS (from request):
1. dba -> dba (passthrough)
2. org_type -> org_type (LLC, Corporation, Joint Venture, etc.)
3. years_at_location -> Calculate year_business_started (2026 - years_at_location)
4. no_of_gallons_annual -> Maps to class_code_13454_premops_annual
5. inside_sales -> Maps to class_code_13673_premops_annual
6. construction_type -> construction_type (passthrough)
7. no_of_stories -> num_stories
8. square_footage -> square_footage (passthrough)
9. year_built -> If < 2006, add 10 years
10. limit_business_income -> business_income_limit
11. limit_personal_property -> personal_property_limit
12. building_description -> building_description (passthrough)

HARDCODED VALUES (always the same, NOT inputs):
- building_class_code: "Convenience Food/Gasoline Stores"
- personal_property_deductible: "5000"
- valuation: "Replacement Cost"
- coinsurance: "80%"

TEST DATA TRANSFORMATIONS:
- years_at_location: 8 -> year_business_started: 2018 (2026 - 8)
- year_built: 2003 -> 2013 (added 10 years because < 2006)
- no_of_gallons_annual: 500000 -> class_code_13454_premops_annual
- inside_sales: 150000 -> class_code_13673_premops_annual
"""
import requests
import time
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

WEBHOOK_URL = "http://localhost:5000/webhook"
STATUS_URL_BASE = "http://localhost:5000/task"
TRACE_URL_BASE = "http://localhost:5000/trace"
TRACES_DIR = Path(__file__).parent / "traces"

def test_local_webhook():
    """Send a test request to local webhook server"""
    print("=" * 80)
    print("TEST LOCAL WEBHOOK SERVER")
    print("=" * 80)
    print("\nMake sure webhook_server.py is running first!")
    print("Run: python webhook_server.py")
    print("=" * 80)
    
    # Test data - matching the format expected by webhook server
    task_id = f"local_test_{int(time.time())}"
    payload = {
        "action": "start_automation",
        "task_id": task_id,
        "data": {
            "form_data": {
                "firstName": "Sarah",
                "lastName": "Mitchell",
                "companyName": "Cottage Walk Convenience LLC",
                "fein": "58-3692147",
                "description": "Convenience store with gas station and retail operations",
                "addressLine1": "55 COTTAGE WALK NW",
                "zipCode": "30121",
                "phone": "(770) 555-8899",
                "email": "sarah.mitchell@cottagewalk.com"
            },
            "dropdowns": {
                "state": "GA",
                "addressType": "Business",
                "contactMethod": "Email",
                "producer": "Shahnaz Sutar"  # Producer name
            },
            "save_form": True,
            "run_quote_automation": True,  # Run quote automation after account creation
            "quote_data": {
                # INPUT FIELDS - will be processed by process_quote_data()
                "dba": "Cottage Walk Convenience",
                "org_type": "LLC",
                "years_at_location": "6",  # Will calculate: 2026 - 6 = 2020
                "no_of_gallons_annual": "450000",  # Maps to class_code_13454_premops_annual
                "inside_sales": "175000",  # Maps to class_code_13673_premops_annual
                "construction_type": "Masonry Non-Combustible",
                "no_of_stories": "1",
                "square_footage": "2800",
                "year_built": "2004",  # < 2006, will be adjusted to 2014
                "limit_business_income": "300000",
                "limit_personal_property": "180000",
                "building_description": "Convenience store with fuel sales and retail operations"
                
                # HARDCODED (not inputs, handled by process_quote_data):
                # - building_class_code: "Convenience Food/Gasoline Stores"
                # - personal_property_deductible: "5000"
                # - valuation: "Replacement Cost"
                # - coinsurance: "80%"
            }
        }
    }
    
    print(f"\n[REQUEST] Sending to: {WEBHOOK_URL}")
    print(f"[TASK ID] {task_id}")
    print(f"[DATA] Company: Cottage Walk Convenience LLC")
    print(f"[DATA] Address: 55 COTTAGE WALK NW, CARTERSVILLE, GA 30121")
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        print(f"\n[OK] Request accepted: {result.get('message', 'OK')}")
        print(f"[STATUS] {result.get('status', 'unknown')}")
        
        if result.get('queue_position'):
            print(f"[QUEUE] Position: {result['queue_position']}")
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to webhook server!")
        print(f"[INFO] Make sure webhook_server.py is running:")
        print(f"       python webhook_server.py")
        return
    except Exception as e:
        print(f"\n[ERROR] Failed to send request: {e}")
        return
    
    # Monitor task status
    status_url = f"{STATUS_URL_BASE}/{task_id}/status"
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
                    
                    # Show queue info if available
                    if status.get('queue_position'):
                        print(f"[QUEUE] Position: {status['queue_position']}")
                    if status.get('active_workers') is not None:
                        print(f"[WORKERS] Active: {status['active_workers']}")
                    
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
                    elif status.get('message'):
                        print(f"\n[RESULT] {status.get('message')}")
                    
                    # Show trace info
                    trace_url = f"{TRACE_URL_BASE}/{task_id}"
                    print(f"\n[TRACE] Download trace file:")
                    print(f"        {trace_url}")
                    print(f"        Or: curl -O {trace_url}")
                    
                    # Try to download trace
                    try:
                        print(f"\n[DOWNLOAD] Attempting to download trace...")
                        trace_response = requests.get(trace_url, timeout=10)
                        if trace_response.status_code == 200:
                            trace_path = TRACES_DIR / f"{task_id}.zip"
                            trace_path.parent.mkdir(exist_ok=True)
                            trace_path.write_bytes(trace_response.content)
                            print(f"[OK] Trace saved to: {trace_path}")
                            print(f"[VIEW] Run: playwright show-trace {trace_path}")
                        else:
                            print(f"[INFO] Trace not available (status: {trace_response.status_code})")
                    except Exception as e:
                        print(f"[INFO] Could not download trace: {e}")
                    
                    break
                    
                elif current_status in ['failed', 'error']:
                    print(f"\n{'=' * 80}")
                    print(f"[FAILED] Task failed!")
                    print(f"{'=' * 80}")
                    if status.get('error'):
                        print(f"[ERROR] {status['error']}")
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
    
    print(f"\n{'=' * 80}")
    print("[DONE]")
    print("=" * 80)


def check_server_health():
    """Check if the webhook server is running"""
    try:
        response = requests.get("http://localhost:5000/health", timeout=5)
        if response.status_code == 200:
            print("[OK] Webhook server is running!")
            return True
        else:
            print(f"[WARNING] Server responded with status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[ERROR] Webhook server is not running!")
        print("[INFO] Start it with: python webhook_server.py")
        return False
    except Exception as e:
        print(f"[ERROR] Could not check server health: {e}")
        return False


if __name__ == "__main__":
    print("\n[CHECK] Testing webhook server health...")
    if check_server_health():
        print("\n" + "=" * 80)
        test_local_webhook()
    else:
        print("\n[ABORT] Cannot proceed without webhook server running")
        print("[INFO] Start the server in another terminal:")
        print("       cd \"c:\\Users\\Dell\\Desktop\\RPA For a\\automation\"")
        print("       python webhook_server.py")
        sys.exit(1)
