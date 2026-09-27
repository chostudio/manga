"""
Booru-style tagging of manga panels with the WD SwinV2 v3 tagger
(``SmilingWolf/wd-swinv2-tagger-v3`` via ``dghs-imgutils``).

The tagger is trained on Danbooru anime/manga art and emits tags that match the
vocabulary users actually search in (``eye``, ``hand``, ``angry``, ``chibi``,
``smile``, ``clenched_teeth``, ``1girl`` ...).  These tags — not generic CLIP —
carry the accuracy for concept search.

``tag_image`` returns ``{tag: score}`` for general tags above a threshold, with
a small stop-list of universal medium/format tags removed (they describe *every*
manga panel and so carry no discriminative signal for search).
"""
from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

GENERAL_THRESHOLD = 0.35

# Universal manga/medium tags: true of essentially every B&W manga panel, so
# useless for ranking.  Dropped to keep the tag store focused on content.
_STOP_TAGS = frozenset({
    "monochrome", "greyscale", "grayscale", "comic", "traditional_media",
    "border", "black_border", "white_border", "simple_background",
    "white_background", "grey_background", "speech_bubble", "signature",
    "artist_name", "watermark", "manga", "screentone", "halftone", "photo_(medium)",
})


def _to_pil(image_bytes: bytes) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.convert("RGB")
    except Exception as e:
        logger.warning("Failed to open image for tagging: %s", e)
        return None


def tag_image(image_bytes: bytes, threshold: float = GENERAL_THRESHOLD) -> dict[str, float]:
    """
    Return ``{tag: score}`` general booru tags for an image.

    Empty dict on any failure (never raises), so callers can tag best-effort
    without guarding the whole ingest pipeline.
    """
    pil = _to_pil(image_bytes)
    if pil is None:
        return {}
    try:
        from imgutils.tagging.wd14 import get_wd14_tags

        _rating, general, _chars = get_wd14_tags(
            pil,
            general_threshold=threshold,
            drop_overlap=True,
        )
    except Exception as e:
        logger.warning("WD14 tagging failed: %s", e)
        return {}

    return {
        tag: round(float(score), 4)
        for tag, score in general.items()
        if tag not in _STOP_TAGS
    }


def merge_tags(*tag_dicts: dict[str, float]) -> dict[str, float]:
    """Merge several ``{tag: score}`` maps, keeping the max score per tag."""
    merged: dict[str, float] = {}
    for d in tag_dicts:
        for tag, score in d.items():
            if score > merged.get(tag, 0.0):
                merged[tag] = score
    return merged
