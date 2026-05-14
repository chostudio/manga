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


@require_GET
def search(request):
    """
    Placeholder: vector DB query → S3 fetch → return images to frontend.
    """
    _q = request.GET.get("q", "")
    return JsonResponse(
        {
            "detail": "Not implemented",
            "query": _q,
        },
        status=501,
    )
