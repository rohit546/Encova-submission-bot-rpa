"""
Check if remote debugging is working by querying the debugging endpoint
"""
import requests
import json

# Try both Railway proxy URLs
PROXY_URLS = [
    "http://hopper.proxy.rlwy.net:19118/json",
    "http://maglev.proxy.rlwy.net:20292/json",
]

print("="*60)
print("CHECKING REMOTE DEBUGGING CONNECTION")
print("="*60)

for url in PROXY_URLS:
    print(f"\nTrying: {url}")
    try:
        response = requests.get(url, timeout=5)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[SUCCESS] Connection works!")
            print(f"Found {len(data)} browser tabs:")
            for tab in data:
                print(f"  - {tab.get('title', 'No title')} ({tab.get('url', 'No URL')})")
                print(f"    WebSocket: {tab.get('webSocketDebuggerUrl', 'N/A')}")
        else:
            print(f"[FAILED] Status: {response.status_code}")
            print(f"Response: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print("[ERROR] Connection refused - Browser might not be running or proxy not accessible")
    except requests.exceptions.Timeout:
        print("[ERROR] Timeout - Proxy might not be responding")
    except Exception as e:
        print(f"[ERROR] {e}")

print("\n" + "="*60)
print("If all connections fail:")
print("1. Make sure a task is currently running")
print("2. Check Railway logs for 'Remote debugging ENABLED'")
print("3. Verify ENABLE_REMOTE_DEBUGGING=True in Railway")
print("="*60)

