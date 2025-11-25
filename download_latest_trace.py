"""
Download trace file by task ID
Works with both local and Railway deployment
"""
import sys
import requests
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

TRACES_DIR = Path(__file__).parent / "debug" / "traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)


def download_trace(task_id: str) -> bool:
    """Download trace file for a specific task"""
    trace_url = f"{BASE_URL}/trace/{task_id}"
    print(f"\n[DOWNLOAD] Fetching trace from: {trace_url}")
    
    try:
        response = requests.get(trace_url, timeout=30)
        if response.status_code == 200:
            trace_path = TRACES_DIR / f"{task_id}.zip"
            trace_path.write_bytes(response.content)
            print(f"[OK] Trace saved to: {trace_path}")
            print(f"[VIEW] Run: playwright show-trace {trace_path}")
            return True
        elif response.status_code == 404:
            print(f"[INFO] Trace not found for task {task_id}")
            return False
        else:
            print(f"[ERROR] Server returned: {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        return False


def list_available_traces():
    """List available traces from server"""
    traces_url = f"{BASE_URL}/traces"
    print(f"\n[INFO] Fetching available traces from: {traces_url}")
    
    try:
        response = requests.get(traces_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            traces = data.get('traces', [])
            if traces:
                print(f"\n[AVAILABLE TRACES] ({len(traces)} total, max {data.get('max_traces', 5)})")
                for trace in traces[:10]:  # Show max 10
                    print(f"  - {trace['task_id']} ({trace['size_kb']} KB) - {trace['created_at']}")
                return traces
            else:
                print("[INFO] No traces available on server")
                return []
        else:
            print(f"[WARNING] Could not list traces: {response.status_code}")
            return []
    except Exception as e:
        print(f"[ERROR] Could not fetch traces: {e}")
        return []


def main():
    print("=" * 80)
    print("DOWNLOAD TRACE FILE")
    print("=" * 80)
    print(f"\n[SERVER] {BASE_URL}")
    print(f"[MODE] {'LOCAL' if USE_LOCAL else 'RAILWAY'}")
    
    if len(sys.argv) > 1:
        task_id = sys.argv[1]
        print(f"\n[TASK ID] {task_id}")
        if download_trace(task_id):
            print(f"\n[SUCCESS] Trace downloaded!")
            print(f"[LOCATION] {TRACES_DIR / f'{task_id}.zip'}")
        else:
            print(f"\n[FAILED] Could not download trace")
            sys.exit(1)
    else:
        print("\n[USAGE] python download_latest_trace.py <task_id>")
        print("\n[EXAMPLES]")
        print("   python download_latest_trace.py test_trace_1764090930")
        print("   python download_latest_trace.py default")
        
        # List available traces
        traces = list_available_traces()
        
        if traces:
            print(f"\n[TIP] Download the latest trace:")
            print(f"      python download_latest_trace.py {traces[0]['task_id']}")
        
        print(f"\n[INFO] Traces are saved to: {TRACES_DIR}")


if __name__ == "__main__":
    main()

