"""
MangaDex API helpers (chapter at-home image delivery).

See https://api.mangadex.org/docs/04-chapter/retrieving-chapter/
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from django.conf import settings

MANGADEX_API = "https://api.mangadex.org"

DEFAULT_AT_HOME_DOWNLOAD_WORKERS = 6

CHAPTER_ID_RE = re.compile(
    r"/chapter/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

_MANGADEX_HOSTS = frozenset({"mangadex.org", "www.mangadex.org", "api.mangadex.org"})


class TokenBucketLimiter:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_fill = time.perf_counter()
        self.lock = threading.Lock()

    def wait_and_consume(self, tokens_to_consume: float = 1.0) -> None:
        with self.lock:
            while True:
                now = time.perf_counter()
                elapsed = now - self.last_fill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_fill = now

                if self.tokens >= tokens_to_consume:
                    self.tokens -= tokens_to_consume
                    return

                sleep_time = (tokens_to_consume - self.tokens) / self.rate
                time.sleep(sleep_time)


_mangadex_api_limiter = TokenBucketLimiter(rate=5.0, capacity=5.0)


@dataclass(frozen=True)
class MangadexChapterPages:
    """Ordered at-home page URLs for one chapter."""

    page_urls: list[str]
    filenames: list[str]


@dataclass(frozen=True)
class MangadexResolveError:
    """Failed to resolve chapter page list from the at-home API."""

    body: dict[str, Any]
    http_status: int = 502


def is_mangadex_hostname(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    host = (urlparse(url.strip()).hostname or "").lower()
    return host in _MANGADEX_HOSTS


def extract_mangadex_chapter_id(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host not in _MANGADEX_HOSTS:
        return None
    match = CHAPTER_ID_RE.search(parsed.path or "")
    return match.group(1).lower() if match else None


def _http_json_get(url: str, *, timeout: int = 30) -> tuple[int, Any]:
    # Ensure we respect the 5 requests/sec rate limit
    _mangadex_api_limiter.wait_and_consume()

    user_agent = getattr(settings, "SCRAPER_USER_AGENT", "MangaIndexer/0.1 (+https://example.com/contact)")
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.getcode() or 200
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    try:
        data = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        data = {"_parse_error": True, "_raw": raw[:500]}
    return status, data


def fetch_at_home_server(chapter_id: str) -> tuple[int, Any]:
    """GET /at-home/server/:chapterId — returns HTTP status and parsed JSON body."""
    url = f"{MANGADEX_API}/at-home/server/{chapter_id}"
    return _http_json_get(url)


def _filenames_for_quality(chapter: dict, quality: str) -> list[str] | None:
    key = "dataSaver" if quality == "data-saver" else "data"
    names = chapter.get(key)
    return names if isinstance(names, list) else None


def _build_at_home_page_urls(
    base_url: str,
    chapter_hash: str,
    filenames: list[str],
    quality: str,
) -> list[str]:
    """MangaDex page URL shape: baseUrl / (data|data-saver) / hash / filename."""
    base = base_url.rstrip("/")
    q = "data-saver" if quality == "data-saver" else "data"
    return [f"{base}/{q}/{chapter_hash}/{name}" for name in filenames]


def resolve_mangadex_chapter_pages(
    chapter_id: str,
    quality: str,
) -> MangadexChapterPages | MangadexResolveError:
    """
    Call at-home server, validate payload, return ordered page URLs.

    Image hosts require requests without Authorization headers; see MangaDex docs.
    """
    status, meta = fetch_at_home_server(chapter_id)
    if status != 200 or meta.get("result") != "ok":
        return MangadexResolveError(
            body={
                "detail": "MangaDex at-home metadata request failed",
                "upstream_status": status,
                "upstream": meta,
            },
        )

    chapter = meta.get("chapter") or {}
    chapter_hash = chapter.get("hash")
    filenames = _filenames_for_quality(chapter, quality)
    base_url = meta.get("baseUrl")

    if not base_url or not chapter_hash or not filenames:
        return MangadexResolveError(
            body={
                "detail": "Unexpected at-home response shape",
                "upstream": meta,
            },
        )

    page_urls = _build_at_home_page_urls(base_url, chapter_hash, filenames, quality)
    return MangadexChapterPages(page_urls=page_urls, filenames=filenames)


def _should_report_to_network(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        # Do not report if it's on a mangadex.org domain
        return not (host == "mangadex.org" or host.endswith(".mangadex.org"))
    except Exception:
        return False


def _report_to_mangadex_network(
    url: str,
    success: bool,
    cached: bool,
    byte_size: int,
    duration_ms: int,
    user_agent: str,
) -> None:
    """
    POST metadata back to the MangaDex@Home reporting endpoint.
    Failures to report are ignored to avoid disrupting the scrape itself.
    """
    report_payload = {
        "url": url,
        "success": success,
        "cached": cached,
        "bytes": byte_size,
        "duration": duration_ms,
    }
    req = urllib.request.Request(
        "https://api.mangadex.network/report",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
        data=json.dumps(report_payload).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception:
        # Do not fail or block if the statistics report fails
        pass


def _fetch_at_home_image_bytes(url: str, *, timeout: int = 60) -> tuple[int, bytes]:
    """
    GET image bytes from an at-home URL and report statistics to MangaDex@Home network.

    Do not attach Authorization — MangaDex image servers reject authenticated requests.
    """
    user_agent = getattr(settings, "SCRAPER_USER_AGENT", "MangaIndexer/0.1 (+https://example.com/contact)")
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": user_agent,
        },
    )

    success = False
    cached = False
    byte_size = 0
    code = 0
    data = b""
    start_time = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode() or 200
            data = resp.read()
            byte_size = len(data)
            success = (code == 200 and byte_size > 0)
            x_cache = resp.headers.get("X-Cache", "")
            cached = x_cache.lower().startswith("hit")

        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)

        if _should_report_to_network(url):
            _report_to_mangadex_network(
                url=url,
                success=success,
                cached=cached,
                byte_size=byte_size,
                duration_ms=duration_ms,
                user_agent=user_agent,
            )

        return code, data

    except urllib.error.HTTPError as e:
        code = e.code
        try:
            data = e.read()
        except Exception:
            data = b""
        byte_size = len(data)
        success = False
        x_cache = e.headers.get("X-Cache", "")
        cached = x_cache.lower().startswith("hit")

        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)

        if _should_report_to_network(url):
            _report_to_mangadex_network(
                url=url,
                success=success,
                cached=cached,
                byte_size=byte_size,
                duration_ms=duration_ms,
                user_agent=user_agent,
            )

        return code, data

    except Exception as e:
        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)

        if _should_report_to_network(url):
            _report_to_mangadex_network(
                url=url,
                success=False,
                cached=False,
                byte_size=0,
                duration_ms=duration_ms,
                user_agent=user_agent,
            )

        raise e


def _fetch_one_page(
    idx_url: tuple[int, str],
) -> tuple[int, str, int, bytes | None, str | None]:
    idx, page_url = idx_url
    code, data = _fetch_at_home_image_bytes(page_url)
    if code != 200 or not data:
        return idx, page_url, code, None, f"HTTP {code}"
    return idx, page_url, code, data, None


def download_mangadex_at_home_pages(
    page_urls: list[str],
    *,
    max_workers: int = DEFAULT_AT_HOME_DOWNLOAD_WORKERS,
) -> dict[int, tuple[str, int, bytes | None, str | None]]:
    """
    Parallel GET of at-home page URLs.

    Returns map index → (page_url, http_status, body or None, error_message or None).
    """
    if not page_urls:
        return {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_one_page, (i, u)): i
            for i, u in enumerate(page_urls)
        }
        results: dict[int, tuple[str, int, bytes | None, str | None]] = {}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                _i, page_url, code, data, err = fut.result()
            except Exception as e:
                page_url = page_urls[idx]
                results[idx] = (page_url, 0, None, str(e))
                continue
            results[idx] = (page_url, code, data, err)
    return results
