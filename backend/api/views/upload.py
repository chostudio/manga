"""
POST /upload

Multipart form body:
  image (file): User-uploaded image.

Intended flow (not implemented):
  1. Accept uploaded image.
  2. Compress image.
  3. Crop into panel images.
  4. Run embedding model (e.g. OpenCLIP).
  5. Store files and vectors in Postgres (and objects in S3 per product design).

Headers:
  Content-Type: multipart/form-data; boundary=... (set automatically by the client).
"""
from django.http import JsonResponse
from django.views.decorators.http import require_POST


@require_POST
def upload(request):
    """
    Placeholder: compress → crop → embed → persist to DB / object storage.
    """
    _has_file = "image" in request.FILES
    return JsonResponse(
        {
            "detail": "Not implemented",
            "received_image_field": _has_file,
        },
        status=501,
    )
