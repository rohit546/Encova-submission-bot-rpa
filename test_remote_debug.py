"""
Quick test script to trigger automation for remote debugging
"""
import requests
import json
from datetime import datetime

WEBHOOK_URL = "https://encova-submission-bot-rpa-production.up.railway.app/webhook"

# Generate unique task ID
task_id = f"remote_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Test payload
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

print("="*60)
print("TRIGGERING AUTOMATION FOR REMOTE DEBUGGING")
print("="*60)
print(f"Task ID: {task_id}")
print(f"\nSending request to: {WEBHOOK_URL}")
print("\nNow check chrome://inspect - you should see the browser!")
print("="*60)

try:
    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 202:
        result = response.json()
        print(f"\n[SUCCESS] Task accepted!")
        print(f"Task ID: {result.get('task_id')}")
        print(f"\n[INFO] Check status: https://encova-submission-bot-rpa-production.up.railway.app/task/{task_id}/status")
        print(f"\n[ACTION] Open chrome://inspect and look for the browser under 'Remote Target'")
        print(f"\n[WAIT] The browser should appear within a few seconds...")
    else:
        print(f"\n[FAILED] Request failed!")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"\n[ERROR] {e}")

