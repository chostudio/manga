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
from django.views.decorators.csrf import csrf_exempt
import uuid

from api.image_split import split_image_into_panels
from api.image_compress import compress_image_if_needed
from api.ingest import index_panel
from api.storage import put_object
from api.models import ChapterIngestion, StoredPanel


@csrf_exempt
@require_POST
def upload(request):
    """
    Handle single page upload: compress → crop → embed → persist to DB / object storage.
    """
    if "image" not in request.FILES:
        return JsonResponse({"detail": "No image provided"}, status=400)
        
    uploaded_file = request.FILES["image"]
    image_bytes = uploaded_file.read()
    
    # Create a dummy chapter for single uploads
    dummy_chapter_id = str(uuid.uuid4())
    chapter = ChapterIngestion.objects.create(
        chapter_id=dummy_chapter_id,
        quality="upload",
        page_count=1
    )
    
    # 1. Split image into panels
    panels_bytes = split_image_into_panels(image_bytes)
    
    results = []
    
    # 2. Process each panel
    for i, panel_bytes in enumerate(panels_bytes):
        # Compress (for storage only)
        compressed = compress_image_if_needed(panel_bytes)

        # Store
        key = f"upload/{dummy_chapter_id}/page_0/panel_{i:04d}.{compressed.extension}"
        stored = put_object(key, compressed.data, compressed.content_type)

        # Save to DB
        stored_panel = StoredPanel.objects.create(
            chapter=chapter,
            page_index=0,
            panel_index=i,
            storage_key=stored.key,
            byte_size=stored.byte_size,
            content_type=stored.content_type,
            public_url=stored.public_url,
            embedding=None,
        )

        # Tag + detect sub-elements + embed from the raw (uncompressed) panel
        index_panel(stored_panel, panel_bytes)

        results.append({
            "panel_index": i,
            "url": stored.public_url,
            "has_embedding": bool(stored_panel.embedding is not None),
            "tags": sorted((stored_panel.tags or {}).keys()),
        })
        
    return JsonResponse({
        "detail": "Success",
        "chapter_id": dummy_chapter_id,
        "panels": results
    })
