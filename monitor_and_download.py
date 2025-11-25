"""
Monitor a task and download trace when it completes
"""
import requests
import time
import sys
from download_trace import download_trace

RAILWAY_URL = "https://encova-submission-bot-rpa-production.up.railway.app"

def monitor_task(task_id: str, max_wait: int = 600):
    """Monitor task and download trace when complete"""
    print(f"\n{'=' * 80}")
    print(f"MONITORING TASK: {task_id}")
    print(f"{'=' * 80}\n")
    
    status_url = f"{RAILWAY_URL}/task/{task_id}/status"
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(status_url, timeout=10)
            if response.status_code == 200:
                status = response.json()
                current_status = status.get('status', 'unknown')
                
                if current_status != last_status:
                    print(f"📊 Status: {current_status}")
                    last_status = current_status
                
                if current_status in ['completed', 'failed']:
                    print(f"\n✅ Task {current_status.upper()}!")
                    print(f"\n⬇️  Downloading trace...")
                    
                    if download_trace(task_id):
                        print(f"\n✅ Trace downloaded successfully!")
                        return True
                    else:
                        print(f"\n⚠️  Could not download trace")
                        return False
            else:
                print(f"⚠️  Status check failed: HTTP {response.status_code}")
        except Exception as e:
            print(f"⚠️  Error: {e}")
        
        # Wait before next check
        time.sleep(10)
        elapsed = int(time.time() - start_time)
        print(f"⏳ Waiting... ({elapsed}s elapsed)", end='\r')
    
    print(f"\n⏱️  Timeout after {max_wait} seconds")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python monitor_and_download.py <task_id>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    monitor_task(task_id)

