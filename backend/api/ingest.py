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

# Cap how many crops of each kind we tag per panel, to bound ingest cost on
# busy panels (tag the largest regions first).
_MAX_FACE_CROPS = 5
_MAX_PERSON_CROPS = 5


def _bbox_area(det) -> int:
    return det.bbox["w"] * det.bbox["h"]


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
    faces = sorted((d for d in detections if d.label == "face"), key=_bbox_area, reverse=True)
    persons = sorted((d for d in detections if d.label == "person"), key=_bbox_area, reverse=True)

    # ---- tagging: whole panel + each face + each person region ----------
    # Tagging each detected character region separately captures per-character
    # attributes and expressions (e.g. one angry face in a crowd) that a single
    # whole-panel pass blurs together.
    panel_tags = tag_image(panel_bytes)
    face_tags: dict[str, float] = {}
    for det in faces[:_MAX_FACE_CROPS]:
        face_tags = merge_tags(face_tags, tag_image(det.crop_bytes))
    person_tags: dict[str, float] = {}
    for det in persons[:_MAX_PERSON_CROPS]:
        person_tags = merge_tags(person_tags, tag_image(det.crop_bytes))

    merged = merge_tags(panel_tags, face_tags, person_tags)
    stored_panel.tags = merged or None
    stored_panel.save(update_fields=["embedding", "tags"])

    # ---- persist PanelTag rows ------------------------------------------
    # Source = the region that produced this tag's highest score.
    def _source_for(tag: str) -> str:
        best = max(
            (("face", face_tags.get(tag, 0.0)),
             ("person", person_tags.get(tag, 0.0)),
             ("panel", panel_tags.get(tag, 0.0))),
            key=lambda kv: kv[1],
        )
        return best[0]

    tag_rows = [
        PanelTag(panel=stored_panel, tag=tag, score=score, source=_source_for(tag))
        for tag, score in merged.items()
    ]
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
