"""
Test script: ingest a MangaDex chapter and run semantic searches.
"""
import requests
import json
import time

BASE = "http://localhost:8000"
CHAPTER_URL = "https://mangadex.org/chapter/e716db76-fefa-46c1-8b0a-3a7a8879d7d2/"

print("=" * 60)
print("1. Ingesting MangaDex chapter...")
print("=" * 60)

resp = requests.post(
    f"{BASE}/upload-webscrape",
    json={"url": CHAPTER_URL, "quality": "data-saver"},
    timeout=300,
)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Chapter: {data.get('chapter_id')}")
print(f"Pages fetched: {data.get('fetched_ok')}")
print(f"Panels stored: {data.get('stored_panels')}")
if data.get("errors"):
    print(f"Errors: {json.dumps(data['errors'], indent=2)}")

print()
print("=" * 60)
print("2. Running searches...")
print("=" * 60)

queries = ["face", "hand", "hair", "clothing", "shocked", "fist", "shouting", "eyes"]

for q in queries:
    resp = requests.get(f"{BASE}/search", params={"q": q}, timeout=30)
    results = resp.json().get("panels", [])
    print(f"\n  '{q}' -> {len(results)} results")
    for r in results[:5]:
        print(f"    panel #{r['id']}  matched_via={r['matched_via']}  url={r['url']}")

print()
print("Done!")
