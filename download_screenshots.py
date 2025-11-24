"""
Download all screenshots from Railway deployment for debugging
"""
import requests
import os
import sys
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Railway webhook URL
BASE_URL = "https://encova-submission-bot-rpa-production.up.railway.app"
SCREENSHOTS_LIST_URL = f"{BASE_URL}/screenshots/{{task_id}}"
SCREENSHOT_DOWNLOAD_URL = f"{BASE_URL}/screenshot/{{task_id}}/{{filename}}"

# Create debugging directory
DEBUG_DIR = Path(__file__).parent / "debug_screenshots"
DEBUG_DIR.mkdir(exist_ok=True)

def download_screenshots(task_id: str):
    """Download all screenshots for a given task"""
    print(f"\n{'='*60}")
    print(f"Downloading Screenshots for Task: {task_id}")
    print(f"{'='*60}\n")
    
    # Create task-specific directory
    task_dir = DEBUG_DIR / task_id
    task_dir.mkdir(exist_ok=True)
    print(f"Download directory: {task_dir}\n")
    
    # Get list of screenshots
    print("Fetching screenshot list...")
    try:
        response = requests.get(SCREENSHOTS_LIST_URL.format(task_id=task_id), timeout=30)
        
        if response.status_code != 200:
            print(f"ERROR: Failed to get screenshot list. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        data = response.json()
        screenshots = data.get('screenshots', [])
        total = data.get('total', 0)
        
        print(f"Found {total} screenshots\n")
        
        if total == 0:
            print("No screenshots available for this task.")
            return False
        
        # Download each screenshot
        downloaded = 0
        failed = 0
        
        for i, screenshot in enumerate(screenshots, 1):
            filename = screenshot.get('filename')
            name = screenshot.get('name', filename)
            size_kb = screenshot.get('size_kb', 0)
            
            print(f"[{i}/{total}] Downloading: {filename} ({size_kb} KB)...", end=" ")
            
            try:
                # Download screenshot
                download_response = requests.get(
                    SCREENSHOT_DOWNLOAD_URL.format(task_id=task_id, filename=filename),
                    timeout=30,
                    stream=True
                )
                
                if download_response.status_code == 200:
                    # Save to file
                    file_path = task_dir / filename
                    with open(file_path, 'wb') as f:
                        for chunk in download_response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Verify file size
                    actual_size = file_path.stat().st_size
                    print(f"[OK] Saved ({actual_size} bytes)")
                    downloaded += 1
                else:
                    print(f"[FAILED] Status: {download_response.status_code}")
                    failed += 1
                    
            except Exception as e:
                print(f"[ERROR] {e}")
                failed += 1
        
        print(f"\n{'='*60}")
        print(f"Download Complete!")
        print(f"  Downloaded: {downloaded}/{total}")
        print(f"  Failed: {failed}")
        print(f"  Location: {task_dir}")
        print(f"{'='*60}\n")
        
        return downloaded > 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def download_all_tasks():
    """Download screenshots for multiple tasks"""
    print("\n" + "="*60)
    print("Download Screenshots from Railway Deployment")
    print("="*60)
    
    # Get task IDs from user
    print("\nEnter task IDs (one per line, or 'all' to list recent tasks):")
    print("Press Enter twice when done, or type 'exit' to quit\n")
    
    task_ids = []
    while True:
        task_id = input("Task ID (or 'exit'): ").strip()
        if task_id.lower() == 'exit':
            break
        if task_id:
            task_ids.append(task_id)
        elif task_ids:  # Empty line after at least one task ID
            break
    
    if not task_ids:
        print("No task IDs provided. Exiting.")
        return
    
    # Download screenshots for each task
    for task_id in task_ids:
        download_screenshots(task_id)
        print()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Task ID provided as argument
        task_id = sys.argv[1]
        download_screenshots(task_id)
    else:
        # Interactive mode
        download_all_tasks()

