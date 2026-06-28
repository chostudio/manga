"""
Object storage for manga panel images (S3 or local filesystem).
"""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class StoredObject:
    """Result of writing one object to storage."""

    key: str
    byte_size: int
    content_type: str
    public_url: str


def build_panel_storage_key(
    chapter_id: str,
    quality: str,
    page_index: int,
    panel_index: int,
    extension: str,
) -> str:
    """
    Object key layout:
      mangadex/{chapter_id}/{quality}/page_{page:04d}/panel_{panel:04d}.{ext}
    """
    ext = extension.lstrip(".")
    return (
        f"mangadex/{chapter_id}/{quality}/"
        f"page_{page_index:04d}/panel_{panel_index:04d}.{ext}"
    )


def public_url_for_key(key: str) -> str:
    base = settings.AWS_S3_PUBLIC_BASE_URL
    if base:
        return f"{base}/{key.lstrip('/')}"
    if settings.STORAGE_BACKEND == "local":
        media_url = settings.MEDIA_URL.rstrip("/")
        return f"{media_url}/{key.lstrip('/')}"
    return ""


def put_object(key: str, data: bytes, content_type: str) -> StoredObject:
    backend = settings.STORAGE_BACKEND
    if backend == "s3":
        return _put_s3(key, data, content_type)
    if backend == "local":
        return _put_local(key, data, content_type)
    raise ValueError(f"Unsupported STORAGE_BACKEND: {backend!r}")


def _put_s3(key: str, data: bytes, content_type: str) -> StoredObject:
    import boto3

    bucket = settings.AWS_STORAGE_BUCKET_NAME
    if not bucket:
        raise ValueError("AWS_STORAGE_BUCKET_NAME is required when STORAGE_BACKEND=s3")

    client_kwargs: dict = {}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_DEFAULT_REGION:
        client_kwargs["region_name"] = settings.AWS_DEFAULT_REGION

    client = boto3.client("s3", **client_kwargs)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return StoredObject(
        key=key,
        byte_size=len(data),
        content_type=content_type,
        public_url=public_url_for_key(key),
    )


def _put_local(key: str, data: bytes, content_type: str) -> StoredObject:
    root = Path(settings.LOCAL_STORAGE_DIR)
    dest = root / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    if not content_type and dest.suffix:
        guessed, _ = mimetypes.guess_type(dest.name)
        content_type = guessed or "application/octet-stream"
    return StoredObject(
        key=key,
        byte_size=len(data),
        content_type=content_type,
        public_url=public_url_for_key(key),
    )
