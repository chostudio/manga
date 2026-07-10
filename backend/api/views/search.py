"""
GET /search

Query params:
  q (str): Text search string for vector similarity search.

Intended flow (not implemented):
  1. Embed or use text to query the vector store (Postgres / pgvector).
  2. Use result rows (e.g. S3 object keys) to fetch images from Amazon S3.
  3. Return image bytes or URLs to the frontend.

Headers: No special headers required for the stub. For image responses, future
implementation may use Content-Type: image/* or multipart, or JSON with URLs.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from pgvector.django import CosineDistance
from api.models import StoredPanel
from api.embedding import generate_text_embedding


@require_GET
def search(request):
    """
    vector DB query → return images to frontend.
    """
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"panels": []})
        
    query_embedding = generate_text_embedding(q)
    if not query_embedding:
        return JsonResponse({"error": "Failed to generate embedding"}, status=500)
        
    try:
        panels = StoredPanel.objects.exclude(embedding=None).order_by(
            CosineDistance("embedding", query_embedding)
        )[:20]
        # Force evaluation to trigger sqlite exception if pgvector is missing
        list(panels)
    except Exception as e:
        print(f"Vector search failed (likely SQLite): {e}")
        panels = StoredPanel.objects.all()[:20]
    
    results = [
        {
            "id": panel.id,
            "chapter_id": panel.chapter.chapter_id,
            "page_index": panel.page_index,
            "panel_index": panel.panel_index,
            "url": panel.public_url,
        }
        for panel in panels
    ]
    
    return JsonResponse({"panels": results})
