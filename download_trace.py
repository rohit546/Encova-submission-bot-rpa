"""
Download trace files from Railway server to local debug directory
"""
import requests
import sys
import os
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Configuration
RAILWAY_URL = "https://encova-submission-bot-rpa-production.up.railway.app"
DEBUG_DIR = Path(__file__).parent / "debug" / "traces"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

def download_trace(task_id: str) -> bool:
    """
    Download trace file for a specific task
    
    Args:
        task_id: The task ID to download trace for
        
    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'=' * 80}")
    print(f"DOWNLOADING TRACE FOR TASK: {task_id}")
    print(f"{'=' * 80}")
    
    # First, check task status to get trace info
    status_url = f"{RAILWAY_URL}/task/{task_id}/status"
    print(f"\n📊 Checking task status...")
    print(f"   URL: {status_url}")
    
    try:
        response = requests.get(status_url, timeout=10)
        if response.status_code != 200:
            print(f"❌ Task not found or error: HTTP {response.status_code}")
            return False
        
        status = response.json()
        task_status = status.get('status', 'unknown')
        print(f"✅ Task status: {task_status}")
        
        # Check if trace exists
        trace_url = status.get('trace_url')
        trace_path = status.get('trace_path')
        
        if not trace_url and not trace_path:
            print(f"\n⚠️  No trace file found for this task")
            print(f"   Tracing may be disabled or task hasn't completed yet")
            return False
        
        if trace_url:
            print(f"\n📦 Trace URL: {trace_url}")
        if trace_path:
            print(f"   Server path: {trace_path}")
        
    except Exception as e:
        print(f"❌ Error checking task status: {e}")
        # Try direct download anyway
        trace_url = f"{RAILWAY_URL}/trace/{task_id}"
        print(f"\n📦 Attempting direct download: {trace_url}")
    
    # Download trace file
    if not trace_url:
        trace_url = f"{RAILWAY_URL}/trace/{task_id}"
    
    print(f"\n⬇️  Downloading trace file...")
    print(f"   From: {trace_url}")
    
    try:
        response = requests.get(trace_url, timeout=60, stream=True)
        
        if response.status_code == 404:
            print(f"❌ Trace file not found on server")
            print(f"   The task may not have completed yet, or tracing is disabled")
            return False
        
        if response.status_code != 200:
            print(f"❌ Error downloading: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
        
        # Determine file size
        content_length = response.headers.get('Content-Length')
        if content_length:
            file_size = int(content_length)
            print(f"   File size: {file_size / (1024*1024):.2f} MB")
        
        # Save to local file
        local_path = DEBUG_DIR / f"{task_id}.zip"
        print(f"   Saving to: {local_path}")
        
        with open(local_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if content_length:
                        percent = (downloaded / file_size) * 100
                        print(f"\r   Progress: {percent:.1f}% ({downloaded / (1024*1024):.2f} MB)", end='', flush=True)
        
        print()  # New line after progress
        
        # Verify file
        if local_path.exists():
            actual_size = local_path.stat().st_size
            print(f"✅ Trace downloaded successfully!")
            print(f"   File: {local_path}")
            print(f"   Size: {actual_size / (1024*1024):.2f} MB")
            print(f"\n💡 To view the trace:")
            print(f"   1. Install Playwright: pip install playwright")
            print(f"   2. Install browser: playwright install chromium")
            print(f"   3. View trace: playwright show-trace \"{local_path}\"")
            return True
        else:
            print(f"❌ File was not saved correctly")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ Download timeout - file may be very large")
        return False
    except Exception as e:
        print(f"❌ Error downloading trace: {e}")
        import traceback
        traceback.print_exc()
        return False


def download_multiple_traces(task_ids: list) -> None:
    """Download traces for multiple tasks"""
    print(f"\n{'=' * 80}")
    print(f"DOWNLOADING {len(task_ids)} TRACE FILES")
    print(f"{'=' * 80}")
    
    success_count = 0
    failed_count = 0
    
    for i, task_id in enumerate(task_ids, 1):
        print(f"\n[{i}/{len(task_ids)}] Processing task: {task_id}")
        if download_trace(task_id):
            success_count += 1
        else:
            failed_count += 1
        print()
    
    print(f"\n{'=' * 80}")
    print(f"DOWNLOAD SUMMARY")
    print(f"{'=' * 80}")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📁 Location: {DEBUG_DIR}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  python download_trace.py <task_id>")
        print(f"  python download_trace.py <task_id1> <task_id2> ...")
        print(f"\nExample:")
        print(f"  python download_trace.py test_trace_1764083435")
        print(f"  python download_trace.py task1 task2 task3")
        print(f"\nTrace files will be saved to: {DEBUG_DIR}")
        sys.exit(1)
    
    task_ids = sys.argv[1:]
    
    if len(task_ids) == 1:
        success = download_trace(task_ids[0])
        sys.exit(0 if success else 1)
    else:
        download_multiple_traces(task_ids)
        sys.exit(0)


if __name__ == "__main__":
    main()

