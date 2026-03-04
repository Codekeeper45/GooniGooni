import requests
import json
import time

url = "http://34.73.173.191/api/generate"
headers = {
    "X-API-Key": "gooni_shared_api_9wQw6nY3fD2PpR7kLm4sV8xTa1cH5uJeZ0rBnM2q",
    "Content-Type": "application/json"
}
payload = {
    "model": "pony",
    "type": "image",
    "mode": "txt2img",
    "prompt": "score_9, score_8_up, rating_safe, test generation, 1girl, colorful, masterpiece",
    "width": 1024,
    "height": 1024,
    "steps": 30,
    "cfg_scale": 6.0,
    "sampler": "Euler"
}

print(f"Sending request to {url}...")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
