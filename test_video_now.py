"""
Test script for Railway webhook with video access
Tests with address: 332 Saint Andrews Rd, Rincon, GA, 31326, USA
"""
import requests
import json
import time
import sys
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Railway webhook URL
WEBHOOK_URL = "https://encova-submission-bot-rpa-production.up.railway.app/webhook"
STATUS_URL = "https://encova-submission-bot-rpa-production.up.railway.app/task/{task_id}/status"
HEALTH_URL = "https://encova-submission-bot-rpa-production.up.railway.app/health"
VIDEO_URL = "https://encova-submission-bot-rpa-production.up.railway.app/video/{task_id}"
VIDEOS_LIST_URL = "https://encova-submission-bot-rpa-production.up.railway.app/videos"

def test_health_check():
    """Test if webhook server is running"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)
    try:
        response = requests.get(HEALTH_URL, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_webhook_request():
    """Test webhook with Rincon, GA address"""
    print("\n" + "="*60)
    print("TEST 2: Webhook Request (Rincon, GA Address)")
    print("="*60)
    
    # Test data with Rincon, GA address
    payload = {
        "action": "start_automation",
        "task_id": f"test_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
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
    
    print(f"Task ID: {payload['task_id']}")
    print(f"Address: 332 Saint Andrews Rd, Rincon, GA, 31326")
    print("\nSending request to Railway...")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 202:
            task_id = response.json().get('task_id')
            print(f"\n[SUCCESS] Task accepted! Task ID: {task_id}")
            return task_id
        else:
            print(f"\n[FAILED] Request failed!")
            print(f"Response: {response.json()}")
            return None
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return None

def check_task_status(task_id: str, max_wait=300):
    """Check task status until completion or timeout"""
    print("\n" + "="*60)
    print(f"TEST 3: Monitoring Task Status")
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
                    
                    # Check for video URL
                    video_url = status.get('video_download_url')
                    video_path = status.get('video_path')
                    
                    if video_url:
                        print(f"\n[VIDEO] Video URL found in status!")
                        print(f"  URL: {video_url}")
                        print(f"  Path: {video_path}")
                    elif video_path:
                        print(f"\n[VIDEO] Video path found: {video_path}")
                    else:
                        print(f"\n[WARNING] No video URL in response")
                    
                    return status
            else:
                print(f"Status check failed: {response.status_code}")
                
        except Exception as e:
            print(f"Error checking status: {e}")
        
        time.sleep(check_interval)
    
    print(f"\n[TIMEOUT] Timeout after {max_wait} seconds")
    return None

def test_video_download(task_id: str, wait_seconds=10):
    """Test downloading the video"""
    print("\n" + "="*60)
    print(f"TEST 4: Video Download Test")
    print("="*60)
    
    print(f"Waiting {wait_seconds} seconds for video to finalize...")
    time.sleep(wait_seconds)
    
    try:
        video_url = VIDEO_URL.format(task_id=task_id)
        print(f"\nAttempting to download video from: {video_url}")
        
        response = requests.get(video_url, timeout=30, stream=True)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            content_length = response.headers.get('Content-Length', 'Unknown')
            
            if 'video' in content_type or 'webm' in content_type:
                print(f"\n[SUCCESS] Video download works!")
                print(f"  Content-Type: {content_type}")
                print(f"  Size: {content_length} bytes")
                
                # Try to save a small sample to verify
                try:
                    chunk = next(response.iter_content(chunk_size=1024))
                    if len(chunk) > 0:
                        print(f"  Video file is valid (received {len(chunk)} bytes)")
                except:
                    pass
                
                return True
            else:
                print(f"\n[WARNING] Response is not a video file")
                print(f"  Content-Type: {content_type}")
                return False
        elif response.status_code == 404:
            print(f"\n[INFO] Video not found (404)")
            print(f"  Video may still be processing or task failed before video was created")
            return False
        else:
            print(f"\n[ERROR] Failed to download video")
            print(f"  Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False

def test_list_videos():
    """Test listing all videos"""
    print("\n" + "="*60)
    print("TEST 5: List All Videos")
    print("="*60)
    
    try:
        response = requests.get(VIDEOS_LIST_URL, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            total = data.get('total', 0)
            print(f"\nTotal videos: {total}")
            
            videos = data.get('videos', [])
            if videos:
                print("\nRecent videos:")
                for video in videos[:5]:
                    print(f"  - {video.get('task_id')}: {video.get('size_mb', 0)} MB")
                    print(f"    Created: {video.get('created_at')}")
            else:
                print("\nNo videos found")
            
            return True
        else:
            print(f"Failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("RAILWAY WEBHOOK TEST - VIDEO RECORDING")
    print("="*60)
    print(f"Testing: {WEBHOOK_URL}")
    print("Address: 332 Saint Andrews Rd, Rincon, GA, 31326")
    print("\nStarting tests...\n")
    
    # Test 1: Health check
    if not test_health_check():
        print("\n[ERROR] Server is not responding.")
        exit(1)
    
    # Test 2: Send webhook request
    task_id = test_webhook_request()
    
    if task_id:
        # Test 3: Monitor task status
        status = check_task_status(task_id, max_wait=300)
        
        if status:
            # Test 4: Try to download video (wait longer for video to finalize)
            test_video_download(task_id, wait_seconds=15)
    
    # Test 5: List all videos
    test_list_videos()
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)
    if task_id:
        print(f"\nTo download video manually:")
        print(f"  curl {VIDEO_URL.format(task_id=task_id)} --output video.webm")
        print(f"\nOr open in browser:")
        print(f"  {VIDEO_URL.format(task_id=task_id)}")

