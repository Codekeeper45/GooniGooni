import requests
import json
import time
import sys

task_id = "codekeeper45::c0724694-6cc9-476c-bfed-1d6a278a723c"
url = f"http://34.73.173.191/api/status/{task_id}"
headers = {
    "X-API-Key": "gooni_shared_api_9wQw6nY3fD2PpR7kLm4sV8xTa1cH5uJeZ0rBnM2q"
}

print(f"Polling status for {task_id}...")
for _ in range(30):
    try:
        resp = requests.get(url, headers=headers)
        data = resp.json()
        print(f"Status: {data.get('status')} | Progress: {data.get('progress')}%")
        if data.get("status") in ("completed", "failed", "success"):
            print(json.dumps(data, indent=2))
            break
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(5)
else:
    print("Timed out waiting for completion.")
