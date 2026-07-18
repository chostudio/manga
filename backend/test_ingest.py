import requests

base_url = "http://localhost:8000"
image_path = "/Users/chrisho/.gemini/antigravity-ide/brain/e40e722e-7bac-4df7-b688-f725b55c5f17/manga_panel_test_1784416618676.png"

print("Uploading image...")
with open(image_path, "rb") as f:
    response = requests.post(f"{base_url}/upload", files={"image": f})

print("Upload response:", response.status_code, response.text)

print("\nSearching for 'face'...")
res = requests.get(f"{base_url}/search", params={"q": "face"})
print("Search 'face' results:", res.json())

print("\nSearching for 'hand'...")
res = requests.get(f"{base_url}/search", params={"q": "hand"})
print("Search 'hand' results:", res.json())

print("\nSearching for 'hair'...")
res = requests.get(f"{base_url}/search", params={"q": "hair"})
print("Search 'hair' results:", res.json())

print("\nSearching for 'clothing'...")
res = requests.get(f"{base_url}/search", params={"q": "clothing"})
print("Search 'clothing' results:", res.json())
