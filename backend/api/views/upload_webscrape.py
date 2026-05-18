"""
POST /upload-webscrape

JSON body:
  {
    "url": "<chapter or reader URL>",
    "quality": "data" | "data-saver"   # optional; MangaDex chapter flow only
  }

If the URL is a MangaDex chapter link, fetches pages via the at-home API, then
optional compress (>500 KiB) → split into panels → further processing (stub).
Other hosts return 501 until a scraper exists for that source.

Image requests must not send Authorization headers (MangaDex requirement).
See https://api.mangadex.org/docs/04-chapter/retrieving-chapter/
"""
from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
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


def process_panels(panels: list[bytes]) -> None:
    """Placeholder: embeddings / persistence / downstream steps. Not implemented yet."""
    _ = panels


def _maybe_compress(image: bytes) -> tuple[bytes, bool]:
    if len(image) > LARGE_IMAGE_BYTES:
        return compress_image_if_needed(image), True
    return image, False


def _run_page_pipeline(page_bytes: bytes) -> dict[str, Any]:
    compressed, did_compress = _maybe_compress(page_bytes)
    panels = split_image_into_panels(compressed)
    process_panels(panels)
    return {
        "original_bytes": len(page_bytes),
        "compressed": did_compress,
        "panel_count": len(panels),
    }


def _upload_webscrape_mangadex(chapter_id: str, quality: str) -> JsonResponse:
    resolved = resolve_mangadex_chapter_pages(chapter_id, quality)
    if isinstance(resolved, MangadexResolveError):
        return JsonResponse(resolved.body, status=resolved.http_status)

    page_urls = resolved.page_urls
    filenames = resolved.filenames
    results = download_mangadex_at_home_pages(page_urls)

    pages_out: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for i in range(len(page_urls)):
        page_url, code, data, err = results[i]
        if err or data is None:
            errors.append({"index": i, "url": page_url, "detail": err or "empty body"})
            continue
        pipeline = _run_page_pipeline(data)
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
            "errors": errors,
            "pages": pages_out,
        },
        status=200,
    )


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
