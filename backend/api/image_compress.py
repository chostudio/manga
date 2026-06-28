"""Image compression for the upload / webscrape pipeline."""
from __future__ import annotations

import io
from dataclasses import dataclass

from django.conf import settings
from PIL import Image

try:
    import pillow_avif  # noqa: F401 — registers AVIF codec with Pillow
except ImportError:
    pass

LARGE_IMAGE_BYTES = 500 * 1024


@dataclass(frozen=True)
class CompressedImage:
    data: bytes
    content_type: str
    extension: str


def _load_rgb(image: bytes) -> Image.Image:
    with Image.open(io.BytesIO(image)) as img:
        if img.mode in ("RGBA", "LA", "P"):
            return img.convert("RGBA")
        return img.convert("RGB")


def _maybe_downscale(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _encode_avif(img: Image.Image) -> bytes | None:
    buf = io.BytesIO()
    try:
        img.save(
            buf,
            format="AVIF",
            quality=settings.IMAGE_AVIF_QUALITY,
        )
    except (OSError, ValueError, KeyError):
        return None
    return buf.getvalue()


def _encode_jpeg(img: Image.Image) -> bytes:
    rgb = img.convert("RGB") if img.mode != "RGB" else img
    buf = io.BytesIO()
    rgb.save(
        buf,
        format="JPEG",
        quality=settings.IMAGE_JPEG_QUALITY,
        optimize=True,
    )
    return buf.getvalue()


def compress_image(image: bytes) -> CompressedImage:
    """
    Resize if over IMAGE_MAX_EDGE_PX, then encode as AVIF (preferred) or JPEG.
    """
    img = _load_rgb(image)
    img = _maybe_downscale(img, settings.IMAGE_MAX_EDGE_PX)

    avif_bytes = _encode_avif(img)
    if avif_bytes is not None:
        return CompressedImage(
            data=avif_bytes,
            content_type="image/avif",
            extension="avif",
        )

    jpeg_bytes = _encode_jpeg(img)
    return CompressedImage(
        data=jpeg_bytes,
        content_type="image/jpeg",
        extension="jpg",
    )


def compress_image_if_needed(image: bytes) -> CompressedImage:
    """Compress when over LARGE_IMAGE_BYTES; otherwise pass through with detected format."""
    if len(image) <= LARGE_IMAGE_BYTES:
        with Image.open(io.BytesIO(image)) as img:
            fmt = (img.format or "JPEG").upper()
        if fmt == "AVIF":
            return CompressedImage(data=image, content_type="image/avif", extension="avif")
        if fmt in ("JPEG", "JPG"):
            return CompressedImage(data=image, content_type="image/jpeg", extension="jpg")
        if fmt == "PNG":
            return CompressedImage(data=image, content_type="image/png", extension="png")
        if fmt == "WEBP":
            return CompressedImage(data=image, content_type="image/webp", extension="webp")
        return CompressedImage(data=image, content_type="image/jpeg", extension="jpg")
    return compress_image(image)
