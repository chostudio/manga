"""
Shared panel-indexing pipeline used by both the direct-upload and webscrape
ingest paths (and by the ``reingest`` management command).

For one stored panel it:
  1. Detects sub-elements (face / eyes / hand / person) with the anime detectors.
  2. Booru-tags the whole panel, and separately tags each detected face crop
     (facial expression tags like ``angry`` / ``smile`` read best on faces).
  3. Merges the tags (max score per tag) onto ``StoredPanel.tags`` and writes
     the per-tag ``PanelTag`` rows that power concept search.
  4. Embeds the panel and each sub-element crop with CLIP (vibes fallback).

It is idempotent: existing PanelTag / PanelSubElement rows for the panel are
cleared first, so re-running (re-ingest) replaces rather than duplicates.
"""
from __future__ import annotations

import logging

from api.detectors import detect_sub_elements
from api.embedding import generate_embedding
from api.models import PanelSubElement, PanelTag, StoredPanel
from api.tagging import merge_tags, tag_image

logger = logging.getLogger(__name__)

# Face-crop tags weight (facial expressions are highly reliable on face crops).
_FACE_TAG_WEIGHT = 1.0


def index_panel(stored_panel: StoredPanel, panel_bytes: bytes) -> None:
    """Tag, detect sub-elements, and embed one panel; persist everything.

    ``panel_bytes`` should be the *decodable* panel image (raw PNG/JPEG or AVIF).
    Never raises — failures are logged so a single bad panel can't abort a batch.
    """
    try:
        _index_panel_inner(stored_panel, panel_bytes)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("index_panel failed for panel %s: %s", stored_panel.pk, exc)


def _index_panel_inner(stored_panel: StoredPanel, panel_bytes: bytes) -> None:
    # Clear any prior derived rows for idempotent re-ingest.
    PanelTag.objects.filter(panel=stored_panel).delete()
    PanelSubElement.objects.filter(panel=stored_panel).delete()

    # ---- panel-level CLIP embedding -------------------------------------
    panel_emb = generate_embedding(panel_bytes)
    if panel_emb:
        stored_panel.embedding = panel_emb

    # ---- sub-element detection ------------------------------------------
    detections = detect_sub_elements(panel_bytes)

    # ---- tagging: whole panel + each face crop --------------------------
    panel_tags = tag_image(panel_bytes)
    face_tags: dict[str, float] = {}
    for det in detections:
        if det.label == "face":
            ft = tag_image(det.crop_bytes)
            face_tags = merge_tags(face_tags, ft)

    merged = merge_tags(panel_tags, {t: s * _FACE_TAG_WEIGHT for t, s in face_tags.items()})
    stored_panel.tags = merged or None
    stored_panel.save(update_fields=["embedding", "tags"])

    # ---- persist PanelTag rows ------------------------------------------
    tag_rows = []
    for tag, score in merged.items():
        # Attribute source to whichever pass produced the higher score.
        source = "face" if face_tags.get(tag, 0.0) >= panel_tags.get(tag, 0.0) and tag in face_tags else "panel"
        tag_rows.append(PanelTag(panel=stored_panel, tag=tag, score=score, source=source))
    if tag_rows:
        PanelTag.objects.bulk_create(tag_rows, ignore_conflicts=True)

    # ---- persist sub-elements + their embeddings ------------------------
    sub_rows = []
    for det in detections:
        emb = generate_embedding(det.crop_bytes)
        sub_rows.append(
            PanelSubElement(
                panel=stored_panel,
                label=det.label,
                bbox=det.bbox,
                embedding=emb if emb else None,
            )
        )
    if sub_rows:
        PanelSubElement.objects.bulk_create(sub_rows)
