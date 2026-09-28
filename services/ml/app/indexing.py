"""
Compute-only panel indexing: the ML half of what the old Django
``ingest.index_panel`` did, minus all database writes. It returns a plain dict
that the (Java) ingestion service persists to Postgres.

For one panel image it produces:
  - embedding:    panel-level CLIP vector (list[float]) for the vibes fallback
  - tags:         merged {tag: score} from the whole panel + each face + each
                  person crop (per-character tagging captures per-character
                  expressions a single whole-panel pass blurs together)
  - tag_sources:  {tag: "face"|"person"|"panel"} — which region scored it highest
  - sub_elements: [{label, bbox, score}] detected face/eyes/hand/person regions
"""
from __future__ import annotations

from app.detectors import detect_sub_elements
from app.embedding import generate_embedding
from app.tagging import merge_tags, tag_image

# Cap how many crops of each kind we tag per panel, to bound cost on busy panels.
_MAX_FACE_CROPS = 5
_MAX_PERSON_CROPS = 5


def _bbox_area(det) -> int:
    return det.bbox["w"] * det.bbox["h"]


def index_panel(panel_bytes: bytes) -> dict:
    """Run detection + per-region tagging + embedding on one panel image."""
    detections = detect_sub_elements(panel_bytes)
    faces = sorted((d for d in detections if d.label == "face"), key=_bbox_area, reverse=True)
    persons = sorted((d for d in detections if d.label == "person"), key=_bbox_area, reverse=True)

    panel_tags = tag_image(panel_bytes)
    face_tags: dict[str, float] = {}
    for det in faces[:_MAX_FACE_CROPS]:
        face_tags = merge_tags(face_tags, tag_image(det.crop_bytes))
    person_tags: dict[str, float] = {}
    for det in persons[:_MAX_PERSON_CROPS]:
        person_tags = merge_tags(person_tags, tag_image(det.crop_bytes))

    merged = merge_tags(panel_tags, face_tags, person_tags)

    def _source_for(tag: str) -> str:
        best = max(
            (("face", face_tags.get(tag, 0.0)),
             ("person", person_tags.get(tag, 0.0)),
             ("panel", panel_tags.get(tag, 0.0))),
            key=lambda kv: kv[1],
        )
        return best[0]

    return {
        "embedding": generate_embedding(panel_bytes) or None,
        "tags": merged,
        "tag_sources": {tag: _source_for(tag) for tag in merged},
        "sub_elements": [
            {"label": d.label, "bbox": d.bbox, "score": round(d.score, 4)}
            for d in detections
        ],
    }
