"""
POST /upload-webscrape

JSON body:
  {
    "url": "<chapter or reader URL>",
    "quality": "data" | "data-saver"   # optional; MangaDex chapter flow only
  }

If the URL is a MangaDex chapter link, fetches pages via the at-home API, then
compress (>500 KiB) → split into panels → store to object storage + DB.
Other hosts return 501 until a scraper exists for that source.

Image requests must not send Authorization headers (MangaDex requirement).
See https://api.mangadex.org/docs/04-chapter/retrieving-chapter/
"""
from __future__ import annotations

import json
from typing import Any

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from api.image_compress import LARGE_IMAGE_BYTES, compress_image_if_needed
from api.image_split import split_image_into_panels
from api.mangadex import (
    MangadexResolveError,
    download_mangadex_at_home_pages,
    extract_mangadex_chapter_id,
    is_mangadex_hostname,
    resolve_mangadex_chapter_pages,
)
from api.models import ChapterIngestion, StoredPanel
from api.storage import build_panel_storage_key, put_object
from api.ingest import index_panel


def process_panels(
    panels: list[bytes],
    *,
    chapter_ingestion: ChapterIngestion,
    page_index: int,
    panel_extensions: list[str] | None = None,
    panel_content_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Persist panel bytes to object storage and record metadata in the database.
    Also generates CLIP embeddings for each panel and its sub-elements.
    """
    chapter_id = chapter_ingestion.chapter_id
    quality = chapter_ingestion.quality
    stored: list[dict[str, Any]] = []

    for panel_index, panel_bytes in enumerate(panels):
        ext = (
            panel_extensions[panel_index]
            if panel_extensions and panel_index < len(panel_extensions)
            else "jpg"
        )
        content_type = (
            panel_content_types[panel_index]
            if panel_content_types and panel_index < len(panel_content_types)
            else "image/jpeg"
        )
        key = build_panel_storage_key(
            chapter_id,
            quality,
            page_index,
            panel_index,
            ext,
        )
        obj = put_object(key, panel_bytes, content_type)

        record, _created = StoredPanel.objects.update_or_create(
            chapter=chapter_ingestion,
            page_index=page_index,
            panel_index=panel_index,
            defaults={
                "storage_key": obj.key,
                "byte_size": obj.byte_size,
                "content_type": obj.content_type,
                "public_url": obj.public_url,
                "embedding": None,
            },
        )
        # Tag + detect sub-elements + embed (panel-level CLIP set inside)
        index_panel(record, panel_bytes)
        stored.append(
            {
                "panel_index": panel_index,
                "storage_key": record.storage_key,
                "byte_size": record.byte_size,
                "content_type": record.content_type,
                "public_url": record.public_url,
            },
        )
    return stored


def _detect_image_format(page_bytes: bytes) -> tuple[str, str]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(page_bytes)) as img:
        fmt = (img.format or "JPEG").upper()
    mapping = {
        "AVIF": ("image/avif", "avif"),
        "JPEG": ("image/jpeg", "jpg"),
        "JPG": ("image/jpeg", "jpg"),
        "PNG": ("image/png", "png"),
        "WEBP": ("image/webp", "webp"),
    }
    return mapping.get(fmt, ("image/jpeg", "jpg"))


def _maybe_compress(page_bytes: bytes) -> tuple[bytes, bool, str, str]:
    if len(page_bytes) > LARGE_IMAGE_BYTES:
        compressed = compress_image_if_needed(page_bytes)
        return compressed.data, True, compressed.content_type, compressed.extension
    content_type, extension = _detect_image_format(page_bytes)
    return page_bytes, False, content_type, extension


def _run_page_pipeline(
    page_bytes: bytes,
    *,
    chapter_ingestion: ChapterIngestion,
    page_index: int,
) -> dict[str, Any]:
    compressed, did_compress, content_type, extension = _maybe_compress(page_bytes)
    panels = split_image_into_panels(compressed)
    extensions = [extension] * len(panels)
    content_types = [content_type] * len(panels)
    stored_panels = process_panels(
        panels,
        chapter_ingestion=chapter_ingestion,
        page_index=page_index,
        panel_extensions=extensions,
        panel_content_types=content_types,
    )
    return {
        "original_bytes": len(page_bytes),
        "compressed": did_compress,
        "panel_count": len(panels),
        "stored_panels": stored_panels,
    }


def _upload_webscrape_mangadex(chapter_id: str, quality: str) -> JsonResponse:
    resolved = resolve_mangadex_chapter_pages(chapter_id, quality)
    if isinstance(resolved, MangadexResolveError):
        return JsonResponse(resolved.body, status=resolved.http_status)

    page_urls = resolved.page_urls
    filenames = resolved.filenames
    results = download_mangadex_at_home_pages(page_urls)

    with transaction.atomic():
        chapter_ingestion, _created = ChapterIngestion.objects.update_or_create(
            chapter_id=chapter_id,
            quality=quality,
            defaults={"page_count": len(filenames)},
        )

        pages_out: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for i in range(len(page_urls)):
            page_url, code, data, err = results[i]
            if err or data is None:
                errors.append({"index": i, "url": page_url, "detail": err or "empty body"})
                continue
            try:
                pipeline = _run_page_pipeline(
                    data,
                    chapter_ingestion=chapter_ingestion,
                    page_index=i,
                )
            except Exception as e:
                errors.append({"index": i, "url": page_url, "detail": str(e)})
                continue
            pages_out.append(
                {
                    "index": i,
                    "url": page_url,
                    "http_status": code,
                    **pipeline,
                },
            )

    if errors and not pages_out:
        return JsonResponse(
            {
                "detail": "All page downloads failed",
                "chapter_id": chapter_id,
                "errors": errors,
            },
            status=502,
        )

    return JsonResponse(
        {
            "chapter_id": chapter_id,
            "quality": quality,
            "page_count": len(filenames),
            "fetched_ok": len(pages_out),
            "stored_panels": sum(p["panel_count"] for p in pages_out),
            "errors": errors,
            "pages": pages_out,
        },
        status=200,
    )


@csrf_exempt
@require_POST
def upload_webscrape(request):
    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    url = body.get("url")
    if not url or not isinstance(url, str):
        return JsonResponse({"detail": "url is required"}, status=400)

    chapter_id = extract_mangadex_chapter_id(url)
    if chapter_id:
        quality = body.get("quality", "data")
        if quality not in ("data", "data-saver"):
            return JsonResponse(
                {"detail": 'quality must be "data" or "data-saver"'},
                status=400,
            )
        return _upload_webscrape_mangadex(chapter_id, quality)

    if is_mangadex_hostname(url):
        return JsonResponse(
            {
                "detail": "MangaDex URL must be a chapter link with a chapter UUID in the path "
                "(e.g. https://mangadex.org/chapter/<uuid>).",
                "url": url,
            },
            status=400,
        )

    return JsonResponse(
        {
            "detail": "Web scrape for this URL is not implemented yet.",
            "url": url,
        },
        status=501,
    )
