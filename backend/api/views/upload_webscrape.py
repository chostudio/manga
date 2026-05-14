"""
POST /upload-webscrape

JSON body:
  { "url": "<link to manga page online>" }

Intended flow (not implemented):
  1. Fetch and parse the page; collect manga image URLs.
  2. For each image (or batch), run the same pipeline as POST /upload:
     compress, crop, embed, store in Postgres / S3.

Headers:
  Content-Type: application/json
"""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST


@require_POST
def upload_webscrape(request):
    """
    Placeholder: webscrape link → reuse /upload processing pipeline.
    """
    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    url = body.get("url")
    return JsonResponse(
        {
            "detail": "Not implemented",
            "url": url,
        },
        status=501,
    )
